import json
import shutil
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import EntityType, Message
from app.processing.extract_entities import EVM_CONTRACT_RE, TICKER_RE
from app.summarization.llm_client import LLMClient

SCHEMA_VERSION = "1.0"
GRADING_TASK = "grade_crypto_signals"
RAW_MESSAGE_LIMIT = 80
SIGNAL_LIMIT = 30
CONTENT_LIMIT = 1000
ALLOWED_SIGNAL_TYPES = {"ticker", "contract_address"}
ALLOWED_CHAINS = {"evm", "solana", "unknown"}
ALLOWED_GRADES = {"A", "B", "C", "D", "ignore"}
ALLOWED_PRIORITIES = {"high", "medium", "low", "ignore"}
ALLOWED_ACTIONS = {"review", "watch", "ignore"}


class GradingValidationError(RuntimeError):
    pass


@dataclass(frozen=True)
class SignalGradingResult:
    input_path: Path
    output_path: Path
    latest_output_path: Path


CodexRunner = Callable[[str, str], str]


def window_filename(window_start: datetime, window_end: datetime) -> str:
    return f"{window_start:%Y%m%dT%H%M%S}-{window_end:%Y%m%dT%H%M%S}.json"


def run_signal_grading(
    session: Session,
    window_start: datetime,
    window_end: datetime,
    *,
    base_dir: Path = Path("data") / "signal-grading",
    codex_runner: CodexRunner | None = None,
    pairing_max_distance: int = 120,
) -> SignalGradingResult:
    payload = build_grading_input(
        session,
        window_start,
        window_end,
        pairing_max_distance=pairing_max_distance,
    )
    validate_grading_input(payload)

    input_dir = base_dir / "input"
    output_dir = base_dir / "output"
    invalid_dir = base_dir / "invalid"
    for directory in (input_dir, output_dir, invalid_dir):
        directory.mkdir(parents=True, exist_ok=True)

    filename = window_filename(window_start, window_end)
    input_path = input_dir / filename
    latest_input_path = input_dir / "latest.json"
    output_path = output_dir / filename
    latest_output_path = output_dir / "latest.json"
    invalid_path = invalid_dir / filename.replace(".json", ".invalid.json")

    write_json(input_path, payload)
    write_json(latest_input_path, payload)
    if output_path.exists():
        output_path.unlink()

    runner = codex_runner or default_codex_runner
    runner_output = runner(
        grading_system_prompt(),
        grading_user_prompt(input_path=input_path, output_path=output_path),
    )
    if not runner_output.strip():
        raise GradingValidationError("Codex grading returned no status output")

    if not output_path.exists():
        raise GradingValidationError(f"Codex grading output was not written: {output_path}")

    try:
        output_payload = json.loads(output_path.read_text(encoding="utf-8"))
        validate_grading_output(output_payload)
    except (json.JSONDecodeError, GradingValidationError) as exc:
        shutil.copyfile(output_path, invalid_path)
        raise GradingValidationError(f"Invalid grading output: {exc}") from exc

    shutil.copyfile(output_path, latest_output_path)
    return SignalGradingResult(
        input_path=input_path,
        output_path=output_path,
        latest_output_path=latest_output_path,
    )


def build_grading_input(
    session: Session,
    window_start: datetime,
    window_end: datetime,
    *,
    pairing_max_distance: int,
) -> dict[str, Any]:
    messages = load_grading_messages(session, window_start, window_end)
    previous_counts = load_previous_window_counts(
        session,
        window_start,
        window_end,
        pairing_max_distance=pairing_max_distance,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "task": GRADING_TASK,
        "window": {
            "start": window_start.isoformat(),
            "end": window_end.isoformat(),
        },
        "signals": build_signal_candidates(
            messages,
            window_start=window_start,
            window_end=window_end,
            pairing_max_distance=pairing_max_distance,
            previous_counts=previous_counts,
        ),
        "raw_messages": [raw_message_payload(message) for message in messages[:RAW_MESSAGE_LIMIT]],
    }


def load_grading_messages(
    session: Session,
    window_start: datetime,
    window_end: datetime,
    *,
    limit: int | None = None,
) -> list[Message]:
    statement = (
        select(Message)
        .options(selectinload(Message.source), selectinload(Message.entities))
        .where(Message.created_at >= window_start, Message.created_at < window_end)
        .order_by(Message.score.desc(), Message.created_at.desc(), Message.id.desc())
    )
    if limit is not None:
        statement = statement.limit(limit)
    return list(session.scalars(statement).all())


def build_signal_candidates(
    messages: list[Message],
    *,
    window_start: datetime,
    window_end: datetime,
    pairing_max_distance: int,
    previous_counts: dict[tuple[str, str], int] | None = None,
) -> list[dict[str, Any]]:
    current: dict[tuple[str, str], dict[str, Any]] = {}
    previous_counts = previous_counts or {}

    for message in messages:
        for signal in signals_for_message(message, pairing_max_distance):
            key = (signal["signal_type"], signal["signal_key"])
            candidate = current.setdefault(
                key,
                {
                    "signal_type": signal["signal_type"],
                    "signal_key": signal["signal_key"],
                    "aliases": set(),
                    "chain": signal["chain"],
                    "first_seen": message.created_at,
                    "latest_seen": message.created_at,
                    "mention_count": 0,
                    "source_ids": set(),
                    "source_message_ids": [],
                },
            )
            candidate["aliases"].update(signal["aliases"])
            candidate["first_seen"] = min(candidate["first_seen"], message.created_at)
            candidate["latest_seen"] = max(candidate["latest_seen"], message.created_at)
            candidate["mention_count"] += 1
            candidate["source_ids"].add(message.source_id)
            source_message_id = db_message_id(message)
            if source_message_id not in candidate["source_message_ids"]:
                candidate["source_message_ids"].append(source_message_id)

    rendered = []
    for key, candidate in current.items():
        labels = labels_for_candidate(candidate, previous_counts.get(key, 0), window_start)
        rendered.append(
            {
                "signal_type": candidate["signal_type"],
                "signal_key": candidate["signal_key"],
                "aliases": sorted(candidate["aliases"]),
                "chain": candidate["chain"],
                "labels": labels,
                "first_seen": candidate["first_seen"].isoformat(),
                "latest_seen": candidate["latest_seen"].isoformat(),
                "mention_count": candidate["mention_count"],
                "source_count": len(candidate["source_ids"]),
                "vip_source_count": 0,
                "source_message_ids": candidate["source_message_ids"],
            }
        )
    rendered.sort(key=lambda item: (-item["mention_count"], item["signal_key"]))
    return rendered[:SIGNAL_LIMIT]


def signals_for_message(message: Message, pairing_max_distance: int) -> list[dict[str, Any]]:
    tickers = [
        {"value": entity.value, "match": find_value_match(TICKER_RE, message.content, entity.value)}
        for entity in message.entities
        if entity.entity_type == EntityType.ticker.value
    ]
    contracts = [
        {
            "value": entity.value,
            "match": find_literal_match(message.content, entity.value),
            "chain": chain_for_contract(entity.value),
        }
        for entity in message.entities
        if entity.entity_type == EntityType.contract_address.value
    ]
    used_tickers: set[str] = set()
    signals: list[dict[str, Any]] = []

    pairings = {
        contract["value"]: nearest_ticker(contract, tickers, pairing_max_distance)
        for contract in contracts
    }
    paired_ticker_counts: dict[str, int] = defaultdict(int)
    for ticker in pairings.values():
        if ticker is not None:
            paired_ticker_counts[ticker["value"]] += 1

    for contract in contracts:
        ticker = pairings[contract["value"]]
        aliases = []
        if ticker is not None and paired_ticker_counts[ticker["value"]] == 1:
            aliases.append(ticker["value"])
            used_tickers.add(ticker["value"])
        signals.append(
            {
                "signal_type": "contract_address",
                "signal_key": contract["value"],
                "aliases": aliases,
                "chain": contract["chain"],
            }
        )

    for ticker in tickers:
        if ticker["value"] in used_tickers:
            continue
        signals.append(
            {
                "signal_type": "ticker",
                "signal_key": ticker["value"],
                "aliases": [],
                "chain": "unknown",
            }
        )
    return dedupe_message_signals(signals)


def nearest_ticker(
    contract: dict[str, Any],
    tickers: list[dict[str, Any]],
    pairing_max_distance: int,
) -> dict[str, Any] | None:
    if contract["match"] is None:
        return None
    candidates = []
    for ticker in tickers:
        if ticker["match"] is None:
            continue
        distance = abs(contract["match"].start() - ticker["match"].start())
        if distance <= pairing_max_distance:
            candidates.append((distance, ticker))
    if len(candidates) != 1:
        return None
    return min(candidates, key=lambda item: item[0])[1]


def find_value_match(pattern, content: str, value: str):
    for match in pattern.finditer(content):
        if f"${match.group(1)}" == value:
            return match
    return None


def find_literal_match(content: str, value: str):
    lowered = content.lower()
    index = lowered.find(value.lower())
    if index == -1:
        return None

    class LiteralMatch:
        def start(self) -> int:
            return index

    return LiteralMatch()


def dedupe_message_signals(signals: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    unique = []
    for signal in signals:
        key = (signal["signal_type"], signal["signal_key"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(signal)
    return unique


def load_previous_window_counts(
    session: Session,
    window_start: datetime,
    window_end: datetime,
    *,
    pairing_max_distance: int,
) -> dict[tuple[str, str], int]:
    previous_start = window_start - (window_end - window_start)
    previous_messages = load_grading_messages(session, previous_start, window_start)
    counts: dict[tuple[str, str], int] = defaultdict(int)
    for message in previous_messages:
        for signal in signals_for_message(message, pairing_max_distance):
            counts[(signal["signal_type"], signal["signal_key"])] += 1
    return counts


def labels_for_candidate(
    candidate: dict[str, Any],
    previous_count: int,
    window_start: datetime,
) -> list[str]:
    labels = []
    if candidate["first_seen"] >= window_start:
        labels.append("new")
    if candidate["mention_count"] >= 2:
        labels.append("repeated")
    if len(candidate["source_ids"]) >= 2:
        labels.append("cross-source")
    if previous_count and candidate["mention_count"] > previous_count:
        labels.append("heating up")
    if previous_count and candidate["mention_count"] < previous_count:
        labels.append("cooling down")
    return labels


def raw_message_payload(message: Message) -> dict[str, Any]:
    return {
        "id": db_message_id(message),
        "created_at": message.created_at.isoformat(),
        "source": message.source.name,
        "source_tier": "default",
        "score": message.score,
        "content": message.content[:CONTENT_LIMIT],
    }


def db_message_id(message: Message) -> str:
    return f"db:{message.id}"


def chain_for_contract(value: str) -> str:
    if EVM_CONTRACT_RE.fullmatch(value):
        return "evm"
    return "solana"


def validate_grading_input(payload: dict[str, Any]) -> None:
    require_object(payload, "input")
    require_equal(payload.get("schema_version"), SCHEMA_VERSION, "schema_version")
    require_equal(payload.get("task"), GRADING_TASK, "task")
    validate_window(payload.get("window"))
    for index, signal in enumerate(require_list(payload.get("signals"), "signals")):
        validate_input_signal(signal, index)
    for index, message in enumerate(require_list(payload.get("raw_messages"), "raw_messages")):
        validate_raw_message(message, index)


def validate_grading_output(payload: dict[str, Any]) -> None:
    require_object(payload, "output")
    require_equal(payload.get("schema_version"), SCHEMA_VERSION, "schema_version")
    validate_window(payload.get("window"))
    grades = require_list(payload.get("grades"), "grades")
    for index, grade in enumerate(grades):
        validate_grade(grade, index)


def validate_grade(grade: Any, index: int) -> None:
    require_object(grade, f"grades[{index}]")
    require_allowed(grade.get("signal_type"), ALLOWED_SIGNAL_TYPES, f"grades[{index}].signal_type")
    require_string(grade.get("signal_key"), f"grades[{index}].signal_key")
    require_string_list(grade.get("aliases"), f"grades[{index}].aliases")
    require_allowed(grade.get("chain"), ALLOWED_CHAINS, f"grades[{index}].chain")
    require_string_list(grade.get("source_message_ids"), f"grades[{index}].source_message_ids")
    require_allowed(grade.get("grade"), ALLOWED_GRADES, f"grades[{index}].grade")
    confidence = grade.get("confidence")
    if (
        isinstance(confidence, bool)
        or not isinstance(confidence, int | float)
        or not 0.0 <= float(confidence) <= 1.0
    ):
        raise GradingValidationError(f"grades[{index}].confidence must be between 0.0 and 1.0")
    require_allowed(grade.get("priority"), ALLOWED_PRIORITIES, f"grades[{index}].priority")
    require_string(grade.get("summary"), f"grades[{index}].summary")
    require_string_list(grade.get("reasoning"), f"grades[{index}].reasoning")
    require_string_list(grade.get("risk_flags"), f"grades[{index}].risk_flags")
    require_allowed(
        grade.get("recommended_action"),
        ALLOWED_ACTIONS,
        f"grades[{index}].recommended_action",
    )


def validate_input_signal(signal: Any, index: int) -> None:
    require_object(signal, f"signals[{index}]")
    require_allowed(signal.get("signal_type"), ALLOWED_SIGNAL_TYPES, f"signals[{index}].signal_type")
    require_string(signal.get("signal_key"), f"signals[{index}].signal_key")
    require_string_list(signal.get("aliases"), f"signals[{index}].aliases")
    require_allowed(signal.get("chain"), ALLOWED_CHAINS, f"signals[{index}].chain")
    require_string_list(signal.get("labels"), f"signals[{index}].labels")
    require_string(signal.get("first_seen"), f"signals[{index}].first_seen")
    require_string(signal.get("latest_seen"), f"signals[{index}].latest_seen")
    require_int(signal.get("mention_count"), f"signals[{index}].mention_count")
    require_int(signal.get("source_count"), f"signals[{index}].source_count")
    require_int(signal.get("vip_source_count"), f"signals[{index}].vip_source_count")
    require_string_list(signal.get("source_message_ids"), f"signals[{index}].source_message_ids")


def validate_raw_message(message: Any, index: int) -> None:
    require_object(message, f"raw_messages[{index}]")
    require_string(message.get("id"), f"raw_messages[{index}].id")
    require_string(message.get("created_at"), f"raw_messages[{index}].created_at")
    require_string(message.get("source"), f"raw_messages[{index}].source")
    require_string(message.get("source_tier"), f"raw_messages[{index}].source_tier")
    score = message.get("score")
    if isinstance(score, bool) or not isinstance(score, int | float):
        raise GradingValidationError(f"raw_messages[{index}].score must be numeric")
    require_string(message.get("content"), f"raw_messages[{index}].content")


def validate_window(window: Any) -> None:
    require_object(window, "window")
    require_string(window.get("start"), "window.start")
    require_string(window.get("end"), "window.end")


def require_object(value: Any, name: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GradingValidationError(f"{name} must be an object")
    return value


def require_list(value: Any, name: str) -> list[Any]:
    if not isinstance(value, list):
        raise GradingValidationError(f"{name} must be a list")
    return value


def require_string_list(value: Any, name: str) -> list[str]:
    items = require_list(value, name)
    for index, item in enumerate(items):
        if not isinstance(item, str):
            raise GradingValidationError(f"{name}[{index}] must be a string")
    return items


def require_string(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value:
        raise GradingValidationError(f"{name} must be a non-empty string")
    return value


def require_int(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise GradingValidationError(f"{name} must be an integer")
    return value


def require_allowed(value: Any, allowed: set[str], name: str) -> None:
    if value not in allowed:
        raise GradingValidationError(f"{name} must be one of: {', '.join(sorted(allowed))}")


def require_equal(value: Any, expected: str, name: str) -> None:
    if value != expected:
        raise GradingValidationError(f"{name} must be {expected}")


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def default_codex_runner(system_prompt: str, user_prompt: str) -> str:
    client = LLMClient()
    if client.provider != "codex_cli":
        raise RuntimeError("Signal grading requires LLM_PROVIDER=codex_cli")
    return client.complete(system_prompt, user_prompt)


def grading_system_prompt() -> str:
    return (
        "You grade crypto alpha signals. Read the provided input JSON file and write only "
        "valid JSON matching the requested schema to the exact output file path."
    )


def grading_user_prompt(*, input_path: Path, output_path: Path) -> str:
    return (
        "Read this input JSON file and produce signal grading JSON.\n"
        f"Input file: {input_path}\n"
        f"Output file: {output_path}"
    )
