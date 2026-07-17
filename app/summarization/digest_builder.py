import re
import json
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import DailySummary, EntityType, Message, WindowSummary
from app.processing.extract_entities import PositionSignal, extract_position_signals
from app.processing.signal_grading import (
    GradingValidationError,
    validate_grading_output,
    window_filename,
)
from app.summarization.llm_client import LLMClient
from app.summarization.prompts import DIGEST_SYSTEM_PROMPT, DIGEST_USER_TEMPLATE
from app.utils.logging import get_logger

logger = get_logger(__name__)

REQUIRED_DIGEST_HEADINGS = [
    "## Executive Summary",
    "## Top Narratives",
    "## Most Mentioned Tokens / Projects",
    "## Repeated Signals Across Sources",
    "## Open Positions",
    "## Links Worth Reviewing",
    "## Raw High-Score Messages",
]

REQUIRED_WINDOW_DIGEST_HEADINGS = [
    "## Open Signals",
    "## Raw High-Score Messages",
]

WINDOW_SIGNAL_LIMIT = 8
WINDOW_RAW_MESSAGE_LIMIT = 8
LABEL_EMOJIS = {
    "new": "🆕",
    "repeated": "🔁",
    "heating up": "🔥",
    "cooling down": "🧊",
    "cross-source": "🔗",
}


DEFAULT_GRADING_BASE_DIR = Path("data") / "signal-grading"
GRADE_ORDER = {"A": 0, "B": 1, "C": 2, "D": 3, "ignore": 4}
PRIORITY_ORDER = {"high": 0, "medium": 1, "low": 2, "ignore": 3}


def build_digest(
    session: Session,
    summary_date: date,
    *,
    grading_base_dir: Path = DEFAULT_GRADING_BASE_DIR,
) -> DailySummary:
    messages = load_messages_for_date(session, summary_date)
    window_start = datetime.combine(summary_date, time.min)
    window_end = window_start + timedelta(days=1)
    grading_output = load_matching_grading_output(
        window_start,
        window_end,
        base_dir=grading_base_dir,
    )
    content, model = render_digest(
        summary_date.isoformat(),
        messages,
        grading_output=grading_output,
    )

    existing = session.scalar(select(DailySummary).where(DailySummary.summary_date == summary_date))
    if existing:
        existing.content = content
        existing.model = model
        existing.created_at = datetime.utcnow()
        session.commit()
        session.refresh(existing)
        return existing

    summary = DailySummary(summary_date=summary_date, content=content, model=model)
    session.add(summary)
    session.commit()
    session.refresh(summary)
    return summary


def build_window_digest(
    session: Session,
    window_start: datetime,
    window_end: datetime,
    *,
    grading_base_dir: Path = DEFAULT_GRADING_BASE_DIR,
) -> WindowSummary:
    if window_start >= window_end:
        raise RuntimeError("Window start must be before window end")

    messages = load_messages_for_window(session, window_start, window_end)
    label = f"{window_start.isoformat()} to {window_end.isoformat()}"
    grading_output = load_matching_grading_output(
        window_start,
        window_end,
        base_dir=grading_base_dir,
    )
    content, model = render_window_digest(label, messages, grading_output=grading_output)

    existing = session.scalar(
        select(WindowSummary).where(
            WindowSummary.window_start == window_start,
            WindowSummary.window_end == window_end,
        )
    )
    if existing:
        existing.content = content
        existing.model = model
        existing.created_at = datetime.utcnow()
        session.commit()
        session.refresh(existing)
        return existing

    summary = WindowSummary(
        window_start=window_start,
        window_end=window_end,
        content=content,
        model=model,
    )
    session.add(summary)
    session.commit()
    session.refresh(summary)
    return summary


def render_digest(
    summary_label: str,
    messages: list[Message],
    *,
    grading_output: dict[str, Any] | None = None,
) -> tuple[str, str]:
    client = LLMClient()
    if client.configured:
        prompt_messages = format_messages_for_prompt(messages)
        if grading_output:
            prompt_messages = (
                f"{prompt_messages}\n\nValidated Codex-graded signal context:\n"
                f"{format_grading_context_for_prompt(grading_output)}"
            )
        content = client.complete(
            DIGEST_SYSTEM_PROMPT,
            DIGEST_USER_TEMPLATE.format(
                summary_date=summary_label,
                messages=prompt_messages,
            ),
        )
        validate_digest_contract(content)
        content = inject_graded_signal_context(content, grading_output)
        return content, client.model_name
    return (
        build_fallback_digest(
            summary_label,
            messages,
            grading_output=grading_output,
        ),
        "fallback-rule-based",
    )


def render_window_digest(
    summary_label: str,
    messages: list[Message],
    *,
    grading_output: dict[str, Any] | None = None,
) -> tuple[str, str]:
    client = LLMClient()
    if client.configured:
        prompt_messages = format_messages_for_prompt(messages)
        if grading_output:
            prompt_messages = (
                f"{prompt_messages}\n\nValidated Codex-graded signal context:\n"
                f"{format_grading_context_for_prompt(grading_output)}"
            )
        content = client.complete(
            DIGEST_SYSTEM_PROMPT,
            compact_window_user_prompt(summary_label, prompt_messages),
        )
        try:
            validate_window_digest_contract(content)
        except RuntimeError:
            content = build_compact_window_digest(
                summary_label,
                messages,
                grading_output=grading_output,
            )
            validate_window_digest_contract(content)
            return content, "fallback-rule-based"
        return content, client.model_name

    content = build_compact_window_digest(
        summary_label,
        messages,
        grading_output=grading_output,
    )
    validate_window_digest_contract(content)
    return content, "fallback-rule-based"


def compact_window_user_prompt(summary_label: str, messages: str) -> str:
    return f"""Build a compact crypto alpha digest for {summary_label}.

Use exactly this Markdown contract and no other second-level headings:

## Open Signals

- One-line actionable bullets only.

## Raw High-Score Messages

- @Source: short message

Messages:
{messages}
"""


def build_compact_window_digest(
    summary_label: str,
    messages: list[Message],
    *,
    grading_output: dict[str, Any] | None = None,
) -> str:
    return f"""# Crypto Alpha Digest - {summary_label}

## Open Signals

{compact_open_signals(messages, grading_output=grading_output)}

## Raw High-Score Messages

{compact_raw_message_section(messages)}
"""


def validate_window_digest_contract(content: str) -> None:
    headings = re.findall(r"^## .+$", content, flags=re.MULTILINE)
    if headings != REQUIRED_WINDOW_DIGEST_HEADINGS:
        raise RuntimeError(
            "Window digest did not follow required section structure: "
            + ", ".join(REQUIRED_WINDOW_DIGEST_HEADINGS)
        )


def load_matching_grading_output(
    window_start: datetime,
    window_end: datetime,
    *,
    base_dir: Path = DEFAULT_GRADING_BASE_DIR,
) -> dict[str, Any] | None:
    output_dir = base_dir / "output"
    candidates = [
        output_dir / window_filename(window_start, window_end),
        output_dir / "latest.json",
    ]
    logger.info(
        "Looking for graded signal output for window %s to %s in %s",
        window_start.isoformat(),
        window_end.isoformat(),
        output_dir,
    )
    seen: set[Path] = set()
    for path in candidates:
        if path in seen:
            continue
        seen.add(path)
        payload = load_valid_grading_payload(path)
        if payload is None:
            logger.info("No valid graded signal output at %s", path)
            continue
        window = payload["window"]
        if window["start"] == window_start.isoformat() and window["end"] == window_end.isoformat():
            logger.info(
                "Using graded signal output from %s for window %s to %s with %d grades",
                path,
                window["start"],
                window["end"],
                len(payload.get("grades", [])),
            )
            return payload
        logger.info(
            "Skipping graded signal output from %s because window is %s to %s",
            path,
            window["start"],
            window["end"],
        )
    logger.info(
        "No matching graded signal output found for window %s to %s; building digest without graded enrichment",
        window_start.isoformat(),
        window_end.isoformat(),
    )
    return None


def load_valid_grading_payload(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        validate_grading_output(payload)
    except (OSError, json.JSONDecodeError, GradingValidationError):
        return None
    return payload


def load_messages_for_date(session: Session, summary_date: date) -> list[Message]:
    rows = session.scalars(
        select(Message)
        .options(selectinload(Message.source), selectinload(Message.entities))
        .where(Message.created_at >= summary_date)
        .order_by(Message.score.desc())
    ).all()
    return [message for message in rows if message.created_at.date() == summary_date]


def load_messages_for_window(
    session: Session,
    window_start: datetime,
    window_end: datetime,
) -> list[Message]:
    return list(
        session.scalars(
            select(Message)
            .options(selectinload(Message.source), selectinload(Message.entities))
            .where(Message.created_at >= window_start, Message.created_at < window_end)
            .order_by(Message.score.desc())
        ).all()
    )


def format_messages_for_prompt(messages: list[Message]) -> str:
    lines = []
    for message in messages[:80]:
        lines.append(
            f"- score={message.score:.1f} source={message.source.name} url={message.url or ''} "
            f"content={message.content[:500]}"
        )
    return "\n".join(lines)


def build_fallback_digest(
    summary_label: str,
    messages: list[Message],
    include_raw_messages: bool = True,
    grading_output: dict[str, Any] | None = None,
) -> str:
    tickers = Counter(
        entity.value
        for message in messages
        for entity in message.entities
        if entity.entity_type == EntityType.ticker.value
    )
    keywords = Counter(
        entity.value
        for message in messages
        for entity in message.entities
        if entity.entity_type == EntityType.keyword.value
    )
    links = [
        entity.value
        for message in messages
        for entity in message.entities
        if entity.entity_type == EntityType.url.value
    ]
    position_signals = collect_position_signals(messages)
    repeated = graded_signal_context(grading_output) or repeated_entities(messages)
    top_messages = messages[:10]

    return f"""# Crypto Alpha Digest - {summary_label}

## Executive Summary

Rule-based fallback digest generated from {len(messages)} messages. Configure LLM_PROVIDER for an AI-written summary.

## Top Narratives

{bullet_list(top_narratives(keywords))}

## Most Mentioned Tokens / Projects

{bullet_list([f"{ticker} ({count} mentions)" for ticker, count in tickers.most_common(10)])}

## Repeated Signals Across Sources

{bullet_list(repeated)}

## Open Positions

{bullet_list(open_positions(messages, position_signals))}

## Links Worth Reviewing

{bullet_list(links[:20])}

## Raw High-Score Messages

{raw_message_section(top_messages, include_raw_messages)}
"""


def top_narratives(keywords: Counter[str]) -> list[str]:
    return [
        f"{key} is a recurring narrative with {count} mentions."
        for key, count in keywords.most_common(10)
    ]


def collect_position_signals(messages: list[Message]) -> dict[str, list[PositionSignal]]:
    signals_by_source_id: dict[str, list[PositionSignal]] = {}
    for message in messages:
        source_id = message_source_id(message)
        signals_by_source_id[source_id] = extract_position_signals(
            message.content,
            source_message_id=source_id,
        )
    return signals_by_source_id


def open_positions(
    messages: list[Message],
    position_signals: dict[str, list[PositionSignal]],
) -> list[str]:
    signals: list[str] = []
    for message in messages:
        signals.extend(
            render_position_signal(signal, message)
            for signal in position_signals_for_message(message, position_signals)
        )
    if not signals:
        return ["No directional position signals classified yet."]
    return signals


def position_signals_for_message(
    message: Message,
    position_signals: dict[str, list[PositionSignal]],
) -> list[PositionSignal]:
    return position_signals.get(message_source_id(message), [])


def render_position_signal(signal: PositionSignal, message: Message) -> str:
    marker = "green dot" if signal.direction == "buy" else "red dot"
    direction_label = "buy/open/accumulate" if signal.direction == "buy" else "sell/close/reduce"
    return (
        f"{marker} {signal.token} {direction_label} "
        f"confidence={signal.confidence:.2f} source={message_locator(message)} "
        f"evidence=\"{signal.evidence_text}\""
    )


def validate_digest_contract(content: str) -> None:
    headings = re.findall(r"^## .+$", content, flags=re.MULTILINE)
    if headings != REQUIRED_DIGEST_HEADINGS:
        raise RuntimeError(
            "LLM digest did not follow required section structure: "
            + ", ".join(REQUIRED_DIGEST_HEADINGS)
        )

    top_narratives = content.split("## Top Narratives", 1)[1].split(
        "## Most Mentioned Tokens / Projects", 1
    )[0]
    bullets = [line.strip()[2:].strip() for line in top_narratives.splitlines() if line.startswith("- ")]
    invalid = [bullet for bullet in bullets if not is_single_sentence(bullet)]
    if invalid:
        raise RuntimeError("LLM digest Top Narratives must use brief one-sentence bullets")


def is_single_sentence(text: str) -> bool:
    sentence_endings = re.findall(r"[.!?](?:\s|$)", text)
    return len(text) <= 180 and len(sentence_endings) == 1 and text[-1] in ".!?"


def repeated_entities(messages: list[Message]) -> list[str]:
    sources_by_entity: dict[str, set[str]] = defaultdict(set)
    for message in messages:
        for entity in message.entities:
            if entity.entity_type in {EntityType.ticker.value, EntityType.keyword.value}:
                sources_by_entity[entity.value].add(message.source.name)
    return [
        f"{value} across {len(sources)} sources"
        for value, sources in sources_by_entity.items()
        if len(sources) > 1
    ]


def graded_signal_context(grading_output: dict[str, Any] | None) -> list[str]:
    if not grading_output:
        return []
    grades = list(grading_output.get("grades", []))
    grades.sort(key=grade_sort_key)
    return [render_graded_signal(grade) for grade in grades]


def compact_open_signals(
    messages: list[Message],
    *,
    grading_output: dict[str, Any] | None = None,
) -> str:
    if grading_output and grading_output.get("grades"):
        grades = list(grading_output.get("grades", []))
        grades.sort(key=grade_sort_key)
        return bullet_list(
            [render_compact_graded_signal(grade) for grade in grades[:WINDOW_SIGNAL_LIMIT]]
        )

    signals: list[str] = []
    position_signals = collect_position_signals(messages)
    for message in messages:
        for signal in position_signals_for_message(message, position_signals):
            marker = "🟢 LONG/WATCH" if signal.direction == "buy" else "🔴 SELL/IGNORE"
            signals.append(
                f"{signal.token} — {marker} — {short_text(signal.evidence_text, 120)}"
            )
            if len(signals) >= WINDOW_SIGNAL_LIMIT:
                return bullet_list(signals)
    return bullet_list(signals)


def render_compact_graded_signal(grade: dict[str, Any]) -> str:
    confidence = float(grade["confidence"])
    flags = compact_flags(grade)
    suffix = f" Flags: {flags}." if flags else ""
    return (
        f"{grade['signal_key']} — {compact_action_label(grade)} — "
        f"Grade {grade['grade']} / {grade['priority']} / {confidence:.2f} — "
        f"{short_text(str(grade['summary']), 140)}{suffix}"
    )


def compact_action_label(grade: dict[str, Any]) -> str:
    action = str(grade.get("recommended_action", "")).lower()
    grade_value = str(grade.get("grade", "")).lower()
    priority = str(grade.get("priority", "")).lower()
    if action == "ignore" or grade_value in {"d", "ignore"}:
        return "🔴 SELL/IGNORE"
    if action == "review" or (grade_value in {"a", "b"} and priority in {"high", "medium"}):
        return "🟢 LONG/WATCH"
    if action == "watch" or grade_value == "c":
        return "🟡 WATCH"
    return "🟡 WATCH"


def compact_flags(grade: dict[str, Any]) -> str:
    parts = [LABEL_EMOJIS.get(label, str(label)) for label in grade.get("labels", [])]
    risk_flags = grade.get("risk_flags", [])
    if risk_flags:
        parts.append(f"⚠️ {', '.join(str(flag) for flag in risk_flags)}")
    return ", ".join(parts)


def inject_graded_signal_context(content: str, grading_output: dict[str, Any] | None) -> str:
    graded_lines = graded_signal_context(grading_output)
    if not graded_lines:
        return content

    before, heading, after = content.partition("## Repeated Signals Across Sources")
    if not heading:
        return content
    section_body, next_heading, rest = after.partition("## Open Positions")
    existing_lines = [line for line in section_body.strip().splitlines() if line.strip()]
    injected_lines = [f"- {line}" for line in graded_lines]
    return (
        f"{before}{heading}\n\n"
        + "\n".join(injected_lines + existing_lines)
        + f"\n\n{next_heading}{rest}"
    )


def format_grading_context_for_prompt(grading_output: dict[str, Any]) -> str:
    return "\n".join(f"- {item}" for item in graded_signal_context(grading_output))


def grade_sort_key(grade: dict[str, Any]) -> tuple[int, int, float, str]:
    return (
        PRIORITY_ORDER.get(str(grade.get("priority")), 99),
        GRADE_ORDER.get(str(grade.get("grade")), 99),
        -float(grade.get("confidence", 0)),
        str(grade.get("signal_key", "")),
    )


def render_graded_signal(grade: dict[str, Any]) -> str:
    confidence = float(grade["confidence"])
    parts = [
        (
            f"{grade['signal_key']} - Grade {grade['grade']} / {grade['priority']} priority / "
            f"{confidence:.2f} confidence: {grade['summary']} "
            f"Action: {grade['recommended_action']}."
        )
    ]
    labels = grade.get("labels", [])
    if labels:
        parts.append(f"Labels: {', '.join(labels)}.")
    parts.append(render_seen_context(grade))
    parts.append(render_source_context(grade))
    risk_flags = grade.get("risk_flags", [])
    if risk_flags:
        parts.append(f"Risks: {', '.join(risk_flags)}.")
    return " ".join(part for part in parts if part)


def render_seen_context(grade: dict[str, Any]) -> str:
    first_seen = grade.get("first_seen")
    latest_seen = grade.get("latest_seen")
    if first_seen and latest_seen and first_seen != latest_seen:
        return f"First seen: {first_seen}; latest seen: {latest_seen}."
    if latest_seen:
        return f"Latest seen: {latest_seen}."
    return ""


def render_source_context(grade: dict[str, Any]) -> str:
    source_count = grade.get("source_count")
    mention_count = grade.get("mention_count")
    message_ids = grade.get("source_message_ids", [])
    segments = []
    if source_count:
        noun = "source" if source_count == 1 else "sources"
        segments.append(f"{source_count} {noun}")
    if mention_count:
        noun = "mention" if mention_count == 1 else "mentions"
        segments.append(f"{mention_count} {noun}")
    if message_ids:
        segments.append(f"messages {', '.join(message_ids[:5])}")
    if not segments:
        return ""
    return f"Sources: {'; '.join(segments)}."


def bullet_list(items: list[str]) -> str:
    if not items:
        return "- None found."
    return "\n".join(f"- {item}" for item in items)


def raw_message_section(messages: list[Message], include_raw_messages: bool) -> str:
    if include_raw_messages:
        return message_list(messages)
    return bullet_list(
        [
            f"{message_locator(message)} raw message hidden from digest."
            for message in messages
        ]
    )


def compact_raw_message_section(messages: list[Message]) -> str:
    if not messages:
        return "- None found."
    return "\n".join(
        f"- @{source_handle(message)}: {short_text(message.content, 140)}"
        for message in messages[:WINDOW_RAW_MESSAGE_LIMIT]
    )


def source_handle(message: Message) -> str:
    return str(message.source.name).lstrip("@")


def short_text(text: str, limit: int) -> str:
    normalized = " ".join(str(text).split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"


def message_list(messages: list[Message]) -> str:
    if not messages:
        return "- None found."
    return "\n".join(
        f"- {message_locator(message)} score={message.score:.1f}: {message.content[:220]}"
        for message in messages
    )


def message_locator(message: Message) -> str:
    if getattr(message, "url", None):
        return f"[{message.source.name}] {message.url}"
    if getattr(message, "external_id", None):
        return f"[{message.source.name}] external_id={message.external_id}"
    if getattr(message, "id", None):
        return f"[{message.source.name}] message_id={message.id}"
    return f"[{message.source.name}]"


def message_source_id(message: Message) -> str:
    if getattr(message, "external_id", None):
        return str(message.external_id)
    if getattr(message, "id", None):
        return str(message.id)
    if getattr(message, "url", None):
        return str(message.url)
    return message.source.name
