import json
from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.database import Base
from app.db.models import EntityType, ExtractedEntity, Message, Source, SourceType
from app.processing.signal_grading import (
    GradingValidationError,
    build_grading_input,
    build_signal_candidates,
    default_codex_runner,
    run_signal_grading,
    validate_grading_input,
    validate_grading_output,
    window_filename,
)


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with session_factory() as db_session:
        yield db_session


def add_message(
    session: Session,
    *,
    source: Source,
    content: str,
    created_at: datetime,
    score: float,
    content_hash: str,
    entities: list[tuple[str, str]],
) -> Message:
    message = Message(
        source_id=source.id,
        content=content,
        created_at=created_at,
        content_hash=content_hash,
        score=score,
    )
    message.entities = [
        ExtractedEntity(entity_type=entity_type, value=value)
        for entity_type, value in entities
    ]
    session.add(message)
    session.commit()
    session.refresh(message)
    return message


def test_window_filename_is_stable() -> None:
    assert window_filename(datetime(2026, 7, 8, 6), datetime(2026, 7, 8, 12)) == (
        "20260708T060000-20260708T120000.json"
    )


def test_build_signal_candidates_pairs_near_ticker_and_contract(session: Session) -> None:
    source = Source(name="@alpha", type=SourceType.telegram.value, identifier="@alpha")
    session.add(source)
    session.commit()
    evm = "0x1234567890abcdef1234567890abcdef12345678"
    message = add_message(
        session,
        source=source,
        content=f"Buying $ABC CA: {evm}",
        created_at=datetime(2026, 7, 8, 7),
        score=9.0,
        content_hash="pair",
        entities=[
            (EntityType.ticker.value, "$ABC"),
            (EntityType.contract_address.value, evm),
        ],
    )

    candidates = build_signal_candidates(
        [message],
        window_start=datetime(2026, 7, 8, 6),
        window_end=datetime(2026, 7, 8, 12),
        pairing_max_distance=120,
    )

    assert len(candidates) == 1
    assert candidates[0]["signal_type"] == "contract_address"
    assert candidates[0]["signal_key"] == evm
    assert candidates[0]["aliases"] == ["$ABC"]
    assert candidates[0]["chain"] == "evm"
    assert candidates[0]["source_message_ids"] == [f"db:{message.id}"]


def test_build_signal_candidates_keeps_distant_ticker_and_contract_separate(session: Session) -> None:
    source = Source(name="@alpha", type=SourceType.telegram.value, identifier="@alpha")
    session.add(source)
    session.commit()
    evm = "0x1234567890abcdef1234567890abcdef12345678"
    message = add_message(
        session,
        source=source,
        content="$ABC " + ("x " * 100) + evm,
        created_at=datetime(2026, 7, 8, 7),
        score=9.0,
        content_hash="separate",
        entities=[
            (EntityType.ticker.value, "$ABC"),
            (EntityType.contract_address.value, evm),
        ],
    )

    candidates = build_signal_candidates(
        [message],
        window_start=datetime(2026, 7, 8, 6),
        window_end=datetime(2026, 7, 8, 12),
        pairing_max_distance=10,
    )

    assert {candidate["signal_type"] for candidate in candidates} == {
        "ticker",
        "contract_address",
    }


def test_build_grading_input_contains_raw_messages_and_signals(session: Session) -> None:
    source = Source(name="@alpha", type=SourceType.telegram.value, identifier="@alpha")
    session.add(source)
    session.commit()
    message = add_message(
        session,
        source=source,
        content="$ABC launch",
        created_at=datetime(2026, 7, 8, 7),
        score=8.0,
        content_hash="input",
        entities=[(EntityType.ticker.value, "$ABC")],
    )

    payload = build_grading_input(
        session,
        datetime(2026, 7, 8, 6),
        datetime(2026, 7, 8, 12),
        pairing_max_distance=120,
    )

    validate_grading_input(payload)
    assert payload["task"] == "grade_crypto_signals"
    assert payload["signals"][0]["signal_key"] == "$ABC"
    assert payload["raw_messages"][0]["id"] == f"db:{message.id}"


def test_validate_grading_output_rejects_bad_confidence() -> None:
    payload = {
        "schema_version": "1.0",
        "window": {"start": "2026-07-08T06:00:00", "end": "2026-07-08T12:00:00"},
        "grades": [
            {
                "signal_type": "ticker",
                "signal_key": "$ABC",
                "aliases": [],
                "chain": "unknown",
                "source_message_ids": ["db:1"],
                "grade": "A",
                "confidence": 1.5,
                "priority": "high",
                "summary": "Bad confidence.",
                "reasoning": [],
                "risk_flags": [],
                "recommended_action": "review",
            }
        ],
    }

    with pytest.raises(GradingValidationError, match="confidence"):
        validate_grading_output(payload)


def test_validate_grading_output_rejects_bool_confidence() -> None:
    payload = valid_output_payload()
    payload["grades"][0]["confidence"] = True

    with pytest.raises(GradingValidationError, match="confidence"):
        validate_grading_output(payload)


def test_validate_grading_output_rejects_non_string_list_items() -> None:
    payload = valid_output_payload()
    payload["grades"][0]["source_message_ids"] = [{"bad": "id"}]

    with pytest.raises(GradingValidationError, match="source_message_ids"):
        validate_grading_output(payload)


def test_validate_grading_input_rejects_malformed_signal() -> None:
    payload = {
        "schema_version": "1.0",
        "task": "grade_crypto_signals",
        "window": {"start": "2026-07-08T06:00:00", "end": "2026-07-08T12:00:00"},
        "signals": [{"signal_type": "ticker"}],
        "raw_messages": [],
    }

    with pytest.raises(GradingValidationError, match="signal_key"):
        validate_grading_input(payload)


def test_run_signal_grading_preserves_latest_when_output_invalid(
    session: Session,
    tmp_path,
) -> None:
    source = Source(name="@alpha", type=SourceType.telegram.value, identifier="@alpha")
    session.add(source)
    session.commit()
    add_message(
        session,
        source=source,
        content="$ABC launch",
        created_at=datetime(2026, 7, 8, 7),
        score=8.0,
        content_hash="invalid-output",
        entities=[(EntityType.ticker.value, "$ABC")],
    )
    latest = tmp_path / "signal-grading" / "output" / "latest.json"
    latest.parent.mkdir(parents=True)
    latest.write_text('{"previous": true}', encoding="utf-8")

    def bad_runner(system_prompt: str, user_prompt: str) -> str:
        _ = system_prompt
        output_path = user_prompt.rsplit("Output file:", 1)[1].strip()
        with open(output_path, "w", encoding="utf-8") as file:
            json.dump({"schema_version": "1.0", "window": {}, "grades": "bad"}, file)
        return "done"

    with pytest.raises(GradingValidationError):
        run_signal_grading(
            session,
            datetime(2026, 7, 8, 6),
            datetime(2026, 7, 8, 12),
            base_dir=tmp_path / "signal-grading",
            codex_runner=bad_runner,
            pairing_max_distance=120,
        )

    assert latest.read_text(encoding="utf-8") == '{"previous": true}'
    assert list((tmp_path / "signal-grading" / "invalid").glob("*.invalid.json"))


def test_run_signal_grading_removes_stale_window_output_before_codex(
    session: Session,
    tmp_path,
) -> None:
    source = Source(name="@alpha", type=SourceType.telegram.value, identifier="@alpha")
    session.add(source)
    session.commit()
    add_message(
        session,
        source=source,
        content="$ABC launch",
        created_at=datetime(2026, 7, 8, 7),
        score=8.0,
        content_hash="stale-output",
        entities=[(EntityType.ticker.value, "$ABC")],
    )
    output = (
        tmp_path
        / "signal-grading"
        / "output"
        / "20260708T060000-20260708T120000.json"
    )
    output.parent.mkdir(parents=True)
    output.write_text(json.dumps(valid_output_payload()), encoding="utf-8")

    def no_file_runner(system_prompt: str, user_prompt: str) -> str:
        _ = system_prompt, user_prompt
        return "done"

    with pytest.raises(GradingValidationError, match="was not written"):
        run_signal_grading(
            session,
            datetime(2026, 7, 8, 6),
            datetime(2026, 7, 8, 12),
            base_dir=tmp_path / "signal-grading",
            codex_runner=no_file_runner,
            pairing_max_distance=120,
        )


def test_run_signal_grading_updates_latest_for_valid_output(session: Session, tmp_path) -> None:
    source = Source(name="@alpha", type=SourceType.telegram.value, identifier="@alpha")
    session.add(source)
    session.commit()
    message = add_message(
        session,
        source=source,
        content="$ABC launch",
        created_at=datetime(2026, 7, 8, 7),
        score=8.0,
        content_hash="valid-output",
        entities=[(EntityType.ticker.value, "$ABC")],
    )

    def good_runner(system_prompt: str, user_prompt: str) -> str:
        _ = system_prompt
        output_path = user_prompt.rsplit("Output file:", 1)[1].strip()
        with open(output_path, "w", encoding="utf-8") as file:
            json.dump(
                {
                    "schema_version": "1.0",
                    "window": {
                        "start": "2026-07-08T06:00:00",
                        "end": "2026-07-08T12:00:00",
                    },
                    "grades": [
                        {
                            "signal_type": "ticker",
                            "signal_key": "$ABC",
                            "aliases": [],
                            "chain": "unknown",
                            "source_message_ids": [f"db:{message.id}"],
                            "grade": "A",
                            "confidence": 0.8,
                            "priority": "high",
                            "summary": "Strong signal.",
                            "reasoning": ["High score."],
                            "risk_flags": [],
                            "recommended_action": "review",
                        }
                    ],
                },
                file,
            )
        return "done"

    result = run_signal_grading(
        session,
        datetime(2026, 7, 8, 6),
        datetime(2026, 7, 8, 12),
        base_dir=tmp_path / "signal-grading",
        codex_runner=good_runner,
        pairing_max_distance=120,
    )

    assert result.input_path.exists()
    assert result.output_path.exists()
    latest = tmp_path / "signal-grading" / "output" / "latest.json"
    assert json.loads(latest.read_text(encoding="utf-8"))["grades"][0]["signal_key"] == "$ABC"


def test_run_signal_grading_rejects_empty_runner_output(session: Session, tmp_path) -> None:
    source = Source(name="@alpha", type=SourceType.telegram.value, identifier="@alpha")
    session.add(source)
    session.commit()
    add_message(
        session,
        source=source,
        content="$ABC launch",
        created_at=datetime(2026, 7, 8, 7),
        score=8.0,
        content_hash="empty-runner",
        entities=[(EntityType.ticker.value, "$ABC")],
    )

    def empty_runner(system_prompt: str, user_prompt: str) -> str:
        _ = system_prompt, user_prompt
        return " "

    with pytest.raises(GradingValidationError, match="returned no status"):
        run_signal_grading(
            session,
            datetime(2026, 7, 8, 6),
            datetime(2026, 7, 8, 12),
            base_dir=tmp_path / "signal-grading",
            codex_runner=empty_runner,
            pairing_max_distance=120,
        )


def test_build_grading_input_uses_previous_window_for_heating_label(session: Session) -> None:
    source = Source(name="@alpha", type=SourceType.telegram.value, identifier="@alpha")
    session.add(source)
    session.commit()
    add_message(
        session,
        source=source,
        content="$ABC earlier",
        created_at=datetime(2026, 7, 8, 1),
        score=4.0,
        content_hash="previous",
        entities=[(EntityType.ticker.value, "$ABC")],
    )
    add_message(
        session,
        source=source,
        content="$ABC current one",
        created_at=datetime(2026, 7, 8, 7),
        score=8.0,
        content_hash="current-one",
        entities=[(EntityType.ticker.value, "$ABC")],
    )
    add_message(
        session,
        source=source,
        content="$ABC current two",
        created_at=datetime(2026, 7, 8, 8),
        score=7.0,
        content_hash="current-two",
        entities=[(EntityType.ticker.value, "$ABC")],
    )

    payload = build_grading_input(
        session,
        datetime(2026, 7, 8, 6),
        datetime(2026, 7, 8, 12),
        pairing_max_distance=120,
    )

    assert "heating up" in payload["signals"][0]["labels"]


def test_ambiguous_one_ticker_two_contracts_does_not_pair_alias(session: Session) -> None:
    source = Source(name="@alpha", type=SourceType.telegram.value, identifier="@alpha")
    session.add(source)
    session.commit()
    first = "0x1234567890abcdef1234567890abcdef12345678"
    second = "0xabcdefabcdefabcdefabcdefabcdefabcdefabcd"
    message = add_message(
        session,
        source=source,
        content=f"$ABC CA {first} and {second}",
        created_at=datetime(2026, 7, 8, 7),
        score=8.0,
        content_hash="ambiguous",
        entities=[
            (EntityType.ticker.value, "$ABC"),
            (EntityType.contract_address.value, first),
            (EntityType.contract_address.value, second),
        ],
    )

    candidates = build_signal_candidates(
        [message],
        window_start=datetime(2026, 7, 8, 6),
        window_end=datetime(2026, 7, 8, 12),
        pairing_max_distance=120,
    )

    contracts = [candidate for candidate in candidates if candidate["signal_type"] == "contract_address"]
    assert len(contracts) == 2
    assert all(candidate["aliases"] == [] for candidate in contracts)
    assert any(candidate["signal_type"] == "ticker" for candidate in candidates)


def test_default_codex_runner_requires_codex_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeClient:
        provider = "openai"

        def complete(self, system_prompt: str, user_prompt: str) -> str:
            _ = system_prompt, user_prompt
            return "should not run"

    monkeypatch.setattr("app.processing.signal_grading.LLMClient", FakeClient)

    with pytest.raises(RuntimeError, match="LLM_PROVIDER=codex_cli"):
        default_codex_runner("system", "user")


def test_validate_grading_output_accepts_minimal_valid_payload() -> None:
    validate_grading_output(
        {
            "schema_version": "1.0",
            "window": {
                "start": "2026-07-08T06:00:00",
                "end": "2026-07-08T12:00:00",
            },
            "grades": [],
        }
    )


def valid_output_payload() -> dict:
    return {
        "schema_version": "1.0",
        "window": {
            "start": "2026-07-08T06:00:00",
            "end": "2026-07-08T12:00:00",
        },
        "grades": [
            {
                "signal_type": "ticker",
                "signal_key": "$ABC",
                "aliases": [],
                "chain": "unknown",
                "source_message_ids": ["db:1"],
                "grade": "A",
                "confidence": 0.8,
                "priority": "high",
                "summary": "Strong signal.",
                "reasoning": ["High score."],
                "risk_flags": [],
                "recommended_action": "review",
            }
        ],
    }
