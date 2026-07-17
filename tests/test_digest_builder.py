import json
import logging
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.database import Base
from app.db.models import EntityType, ExtractedEntity, Message, Source, SourceType
from app.summarization import digest_builder
from app.summarization.digest_builder import (
    build_fallback_digest,
    build_digest,
    build_window_digest,
    load_matching_grading_output,
    render_digest,
    render_window_digest,
)
from app.summarization.prompts import DIGEST_SYSTEM_PROMPT, DIGEST_USER_TEMPLATE


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with session_factory() as db_session:
        yield db_session


def _message(
    content: str,
    score: float,
    source: str,
    entities: list[tuple[EntityType, str]],
    url: str | None = None,
    external_id: str | None = None,
    message_id: int | None = None,
):
    return SimpleNamespace(
        id=message_id,
        content=content,
        score=score,
        source=SimpleNamespace(name=source),
        external_id=external_id,
        entities=[
            SimpleNamespace(entity_type=entity_type.value, value=value)
            for entity_type, value in entities
        ],
        url=url,
    )


def test_fallback_digest_uses_operator_readability_sections_in_order() -> None:
    digest = build_fallback_digest(
        "2026-07-08T06:00:00 to 2026-07-08T12:00:00",
        [
            _message(
                "$CASHCHAT listing and airdrop watch",
                9.0,
                "cashchat",
                [
                    (EntityType.ticker, "$CASHCHAT"),
                    (EntityType.keyword, "listing"),
                    (EntityType.keyword, "airdrop"),
                    (EntityType.url, "https://example.com/cashchat"),
                ],
                "https://example.com/cashchat",
            ),
            _message(
                "$CASHCHAT listing repeated elsewhere",
                8.0,
                "other",
                [
                    (EntityType.ticker, "$CASHCHAT"),
                    (EntityType.keyword, "listing"),
                ],
            ),
        ],
    )

    expected_headings = [
        "## Executive Summary",
        "## Top Narratives",
        "## Most Mentioned Tokens / Projects",
        "## Repeated Signals Across Sources",
        "## Open Positions",
        "## Links Worth Reviewing",
        "## Raw High-Score Messages",
    ]
    positions = [digest.index(heading) for heading in expected_headings]

    assert positions == sorted(positions)
    assert "## Potential Opportunities" not in digest
    assert "## Risks / Warnings" not in digest
    assert "- listing is a recurring narrative with 2 mentions." in digest
    assert "- No directional position signals classified yet." in digest
    assert "Raw High-Score Messages" in digest
    assert "https://example.com/cashchat" in digest
    assert "$CASHCHAT listing and airdrop watch" in digest


def test_fallback_top_narratives_are_single_sentence_bullets() -> None:
    digest = build_fallback_digest(
        "window",
        [
            _message(
                "airdrop launch",
                5.0,
                "source",
                [(EntityType.keyword, "airdrop"), (EntityType.keyword, "launch")],
            )
        ],
    )

    section = digest.split("## Top Narratives", 1)[1].split(
        "## Most Mentioned Tokens / Projects", 1
    )[0]
    bullets = [line for line in section.splitlines() if line.startswith("- ")]

    assert bullets
    assert all(line.count(".") == 1 for line in bullets)
    assert all(len(line) <= 90 for line in bullets)


def test_prompt_requests_operator_readability_sections() -> None:
    prompt = DIGEST_USER_TEMPLATE.format(summary_date="window", messages="- message")

    assert "## Potential Opportunities" not in prompt
    assert "## Risks / Warnings" not in prompt
    assert "## Open Positions" in prompt
    assert "Use brief one-sentence bullets for Top Narratives." in prompt
    assert "positive language means long/buy/open/accumulate" not in prompt
    assert "negative language means short/sell/close/reduce" not in prompt


def test_system_prompt_requests_sentiment_based_positions() -> None:
    assert "market alpha research digests" in DIGEST_SYSTEM_PROMPT
    assert "crypto, token, equity, macro" in DIGEST_SYSTEM_PROMPT
    assert "positive language means long/buy/open/accumulate" in DIGEST_SYSTEM_PROMPT
    assert "negative language means short/sell/close/reduce" in DIGEST_SYSTEM_PROMPT


def test_configured_llm_output_must_match_digest_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BadLLMClient:
        configured = True
        model_name = "codex-cli:default"

        def complete(self, system_prompt: str, user_prompt: str) -> str:
            _ = system_prompt, user_prompt
            return "# Digest\n\n## Executive Summary\n\nMissing required sections."

    monkeypatch.setattr(digest_builder, "LLMClient", BadLLMClient)

    with pytest.raises(RuntimeError, match="required section structure"):
        render_digest("window", [])


def test_configured_llm_output_accepts_required_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class GoodLLMClient:
        configured = True
        model_name = "codex-cli:default"

        def complete(self, system_prompt: str, user_prompt: str) -> str:
            _ = system_prompt, user_prompt
            return """# Crypto Alpha Digest - window

## Executive Summary

Summary.

## Top Narratives

- Listing interest is recurring.

## Most Mentioned Tokens / Projects

- $CASHCHAT

## Repeated Signals Across Sources

- $CASHCHAT across 2 sources

## Open Positions

- No directional position signals classified yet.

## Links Worth Reviewing

- https://example.com

## Raw High-Score Messages

- [source] https://example.com score=9.0: raw
"""

    monkeypatch.setattr(digest_builder, "LLMClient", GoodLLMClient)

    content, model = render_digest("window", [])

    assert model == "codex-cli:default"
    assert "## Open Positions" in content


def test_raw_hidden_mode_preserves_audit_references_without_raw_content() -> None:
    digest = build_fallback_digest(
        "window",
        [
            _message(
                "sensitive raw body that should be hidden",
                8.0,
                "telegram",
                [],
                url="https://t.me/source/42",
            )
        ],
        include_raw_messages=False,
    )

    raw_section = digest.split("## Raw High-Score Messages", 1)[1]

    assert "https://t.me/source/42 raw message hidden from digest." in raw_section
    assert "sensitive raw body that should be hidden" not in raw_section


def test_window_digest_stores_operator_readable_format(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "fallback")
    from app.config import get_settings

    get_settings.cache_clear()
    source = Source(name="@alpha", type=SourceType.telegram.value, identifier="@alpha")
    session.add(source)
    session.commit()
    message = Message(
        source_id=source.id,
        external_id="42",
        content="$CASHCHAT listing repeated",
        created_at=datetime(2026, 7, 8, 6, 30),
        content_hash="cashchat",
        score=9,
    )
    message.entities.append(
        ExtractedEntity(entity_type=EntityType.ticker.value, value="$CASHCHAT")
    )
    message.entities.append(
        ExtractedEntity(entity_type=EntityType.keyword.value, value="listing")
    )
    session.add(message)
    session.commit()

    summary = build_window_digest(
        session,
        datetime(2026, 7, 8, 6),
        datetime(2026, 7, 8, 12),
    )

    assert [line for line in summary.content.splitlines() if line.startswith("## ")] == [
        "## Open Signals",
        "## Raw High-Score Messages",
    ]
    assert "## Raw High-Score Messages" in summary.content
    assert "## Open Positions" not in summary.content
    assert "- @alpha: $CASHCHAT listing repeated" in summary.content
    assert "external_id=42" not in summary.content


def _grading_payload(
    window_start: datetime,
    window_end: datetime,
    *,
    schema_version: str = "1.1",
) -> dict:
    return {
        "schema_version": schema_version,
        "window": {
            "start": window_start.isoformat(),
            "end": window_end.isoformat(),
        },
        "grades": [
            {
                "signal_type": "ticker",
                "signal_key": "$CASHCHAT",
                "aliases": ["$CASH"],
                "chain": "unknown",
                "labels": ["new", "repeated", "cross-source", "heating up", "cooling down"],
                "first_seen": "2026-07-07T08:00:00",
                "latest_seen": "2026-07-08T11:30:00",
                "mention_count": 4,
                "source_count": 2,
                "vip_source_count": 0,
                "source_message_ids": ["db:1", "db:2"],
                "grade": "A",
                "confidence": 0.86,
                "priority": "high",
                "summary": "Repeated cross-source listing signal.",
                "reasoning": ["Two independent sources repeated the listing angle."],
                "risk_flags": ["thin liquidity", "single-source"],
                "recommended_action": "review",
            }
        ],
    }


def _grade(
    signal_key: str,
    *,
    grade: str,
    priority: str,
    confidence: float,
    recommended_action: str = "review",
) -> dict:
    return {
        "signal_type": "ticker",
        "signal_key": signal_key,
        "aliases": [],
        "chain": "unknown",
        "labels": ["new"],
        "first_seen": "2026-07-08T06:00:00",
        "latest_seen": "2026-07-08T07:00:00",
        "mention_count": 1,
        "source_count": 1,
        "vip_source_count": 0,
        "source_message_ids": ["db:1"],
        "grade": grade,
        "confidence": confidence,
        "priority": priority,
        "summary": f"{signal_key} compact signal.",
        "reasoning": ["Fixture signal."],
        "risk_flags": ["single-source"],
        "recommended_action": recommended_action,
    }


def test_window_renderer_uses_compact_contract_with_graded_signals() -> None:
    window_start = datetime(2026, 7, 8, 6)
    window_end = datetime(2026, 7, 8, 12)
    messages = [
        _message("$CASHCHAT listing repeated", 9, "@alpha", [(EntityType.ticker, "$CASHCHAT")])
    ]

    content, model = render_window_digest(
        f"{window_start.isoformat()} to {window_end.isoformat()}",
        messages,
        grading_output=_grading_payload(window_start, window_end),
    )

    assert model == "fallback-rule-based"
    assert [line for line in content.splitlines() if line.startswith("## ")] == [
        "## Open Signals",
        "## Raw High-Score Messages",
    ]
    assert "## Executive Summary" not in content
    assert "## Repeated Signals Across Sources" not in content
    assert (
        "- $CASHCHAT — 🟢 LONG/WATCH — Grade A / high / 0.86 — "
        "Repeated cross-source listing signal. Flags: 🆕, 🔁, 🔗, 🔥, 🧊, "
        "⚠️ thin liquidity, single-source."
    ) in content
    assert "- @alpha: $CASHCHAT listing repeated" in content


def test_window_renderer_sorts_and_caps_top_eight_graded_signals() -> None:
    payload = _grading_payload(datetime(2026, 7, 8, 6), datetime(2026, 7, 8, 12))
    payload["grades"] = [
        _grade("$LOW", grade="A", priority="low", confidence=0.99),
        _grade("$BETA", grade="B", priority="high", confidence=0.70),
        _grade("$ALPHA", grade="B", priority="high", confidence=0.90),
        *[
            _grade(f"$MED{i}", grade="C", priority="medium", confidence=0.8 - (i / 100))
            for i in range(8)
        ],
    ]

    content, _model = render_window_digest("window", [], grading_output=payload)
    open_signals = content.split("## Open Signals", 1)[1].split(
        "## Raw High-Score Messages", 1
    )[0]
    bullets = [line for line in open_signals.splitlines() if line.startswith("- ")]

    assert len(bullets) == 8
    assert bullets[0].startswith("- $ALPHA")
    assert bullets[1].startswith("- $BETA")
    assert "$LOW" not in open_signals


@pytest.mark.parametrize(
    ("grade", "priority", "recommended_action", "expected"),
    [
        ("B", "medium", "review", "🟢 LONG/WATCH"),
        ("C", "high", "review", "🟢 LONG/WATCH"),
        ("A", "low", "watch", "🟡 WATCH"),
        ("A", "high", "none", "🟢 LONG/WATCH"),
        ("B", "medium", "none", "🟢 LONG/WATCH"),
        ("D", "high", "review", "🔴 SELL/IGNORE"),
        ("ignore", "ignore", "ignore", "🔴 SELL/IGNORE"),
    ],
)
def test_compact_signal_action_mapping(
    grade: str,
    priority: str,
    recommended_action: str,
    expected: str,
) -> None:
    payload = _grading_payload(datetime(2026, 7, 8, 6), datetime(2026, 7, 8, 12))
    payload["grades"] = [
        _grade(
            "$MAP",
            grade=grade,
            priority=priority,
            confidence=0.5,
            recommended_action=recommended_action,
        )
    ]

    content, _model = render_window_digest("window", [], grading_output=payload)

    assert f"- $MAP — {expected} — Grade {grade} / {priority} / 0.50" in content


def test_compact_signal_renders_unknown_labels_as_plain_text() -> None:
    payload = _grading_payload(datetime(2026, 7, 8, 6), datetime(2026, 7, 8, 12))
    payload["grades"][0]["labels"] = ["new", "exchange-flow"]
    payload["grades"][0]["risk_flags"] = []

    content, _model = render_window_digest("window", [], grading_output=payload)

    assert "Flags: 🆕, exchange-flow." in content


def test_window_raw_messages_are_compact_one_line_bullets_and_capped() -> None:
    messages = [
        _message(
            f"$TOKEN{i} high score message with url",
            10 - i,
            f"source{i}",
            [(EntityType.ticker, f"$TOKEN{i}")],
            url=f"https://example.com/{i}",
            external_id=str(i),
        )
        for i in range(10)
    ]

    content, _model = render_window_digest("window", messages)
    raw_section = content.split("## Raw High-Score Messages", 1)[1]
    bullets = [line for line in raw_section.splitlines() if line.startswith("- ")]

    assert len(bullets) == 8
    assert bullets[0] == "- @source0: $TOKEN0 high score message with url"
    assert all("score=" not in line for line in bullets)
    assert all("external_id=" not in line for line in bullets)
    assert all("https://example.com" not in line for line in bullets)


def test_window_missing_grading_output_uses_compact_position_fallback() -> None:
    content, _model = render_window_digest(
        "window",
        [
            _message(
                "Fund is bullish on $SOL after mainnet momentum",
                9,
                "alpha",
                [(EntityType.ticker, "$SOL")],
            ),
            _message(
                "Trader is bearish on $ETH into unlock",
                8,
                "beta",
                [(EntityType.ticker, "$ETH")],
            ),
        ],
    )

    assert "## Open Signals" in content
    assert "- $SOL — 🟢 LONG/WATCH — Fund is bullish on $SOL after mainnet momentum" in content
    assert "- $ETH — 🔴 SELL/IGNORE — Trader is bearish on $ETH into unlock" in content


def test_window_empty_grading_output_uses_compact_position_fallback() -> None:
    payload = _grading_payload(datetime(2026, 7, 8, 6), datetime(2026, 7, 8, 12))
    payload["grades"] = []

    content, _model = render_window_digest(
        "window",
        [
            _message(
                "Fund is bullish on $SOL after mainnet momentum",
                9,
                "alpha",
                [(EntityType.ticker, "$SOL")],
            )
        ],
        grading_output=payload,
    )

    assert "- $SOL — 🟢 LONG/WATCH — Fund is bullish on $SOL after mainnet momentum" in content


def test_configured_llm_window_path_keeps_compact_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"count": 0}

    class OldContractLLMClient:
        configured = True
        model_name = "codex-cli:default"

        def complete(self, system_prompt: str, user_prompt: str) -> str:
            _ = system_prompt, user_prompt
            calls["count"] += 1
            return """# Crypto Alpha Digest - window

## Executive Summary

Old long output.
"""

    monkeypatch.setattr(digest_builder, "LLMClient", OldContractLLMClient)

    content, model = render_window_digest("window", [])

    assert calls["count"] == 1
    assert model == "fallback-rule-based"
    assert [line for line in content.splitlines() if line.startswith("## ")] == [
        "## Open Signals",
        "## Raw High-Score Messages",
    ]
    assert "## Executive Summary" not in content


def test_configured_llm_window_path_accepts_compact_contract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"count": 0}

    class CompactLLMClient:
        configured = True
        model_name = "codex-cli:default"

        def complete(self, system_prompt: str, user_prompt: str) -> str:
            _ = system_prompt
            calls["count"] += 1
            assert "## Open Signals" in user_prompt
            return """# Crypto Alpha Digest - window

## Open Signals

- 🟢 $SOL — LONG/WATCH — Grade B / high / 0.80 — Compact LLM signal.

## Raw High-Score Messages

- @alpha: compact raw
"""

    monkeypatch.setattr(digest_builder, "LLMClient", CompactLLMClient)

    content, model = render_window_digest("window", [])

    assert calls["count"] == 1
    assert model == "codex-cli:default"
    assert "Compact LLM signal" in content


def test_configured_llm_receives_validated_grading_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = {}

    class GoodLLMClient:
        configured = True
        model_name = "codex-cli:default"

        def complete(self, system_prompt: str, user_prompt: str) -> str:
            captured["system_prompt"] = system_prompt
            captured["user_prompt"] = user_prompt
            return """# Crypto Alpha Digest - window

## Executive Summary

Summary.

## Top Narratives

- Listing interest is recurring.

## Most Mentioned Tokens / Projects

- $CASHCHAT

## Repeated Signals Across Sources

- $CASHCHAT Grade A context.

## Open Positions

- No directional position signals classified yet.

## Links Worth Reviewing

- https://example.com

## Raw High-Score Messages

- [source] https://example.com score=9.0: raw
"""

    monkeypatch.setattr(digest_builder, "LLMClient", GoodLLMClient)
    window_start = datetime(2026, 7, 8, 6)
    window_end = datetime(2026, 7, 8, 12)

    content, model = render_digest(
        "window",
        [],
        grading_output=_grading_payload(window_start, window_end),
    )

    assert model == "codex-cli:default"
    assert "Validated Codex-graded signal context:" in captured["user_prompt"]
    assert "$CASHCHAT - Grade A / high priority / 0.86 confidence" in captured["user_prompt"]
    assert "Repeated cross-source listing signal. Action: review." in captured["user_prompt"]
    assert "Labels: new, repeated, cross-source, heating up, cooling down." in captured["user_prompt"]
    assert "First seen: 2026-07-07T08:00:00; latest seen: 2026-07-08T11:30:00." in captured["user_prompt"]
    assert "Sources: 2 sources; 4 mentions; messages db:1, db:2." in captured["user_prompt"]
    assert "Risks: thin liquidity, single-source." in captured["user_prompt"]
    assert "## Repeated Signals Across Sources" in content
    assert "- $CASHCHAT - Grade A / high priority / 0.86 confidence" in content
    assert "Repeated cross-source listing signal. Action: review." in content
    assert "Labels: new, repeated, cross-source, heating up, cooling down." in content
    assert "- $CASHCHAT Grade A context." in content


def test_exact_window_grading_output_is_rendered_and_preserves_raw_audit(
    tmp_path,
) -> None:
    window_start = datetime(2026, 7, 8, 6)
    window_end = datetime(2026, 7, 8, 12)
    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True)
    (output_dir / "20260708T060000-20260708T120000.json").write_text(
        json.dumps(_grading_payload(window_start, window_end)),
        encoding="utf-8",
    )
    messages = [
        _message(
            "$CASHCHAT listing repeated",
            9,
            "alpha",
            [(EntityType.ticker, "$CASHCHAT")],
            external_id="42",
            message_id=1,
        )
    ]

    grading_output = load_matching_grading_output(
        window_start,
        window_end,
        base_dir=tmp_path,
    )
    digest = build_fallback_digest("window", messages, grading_output=grading_output)

    assert "- $CASHCHAT - Grade A / high priority / 0.86 confidence" in digest
    assert "Repeated cross-source listing signal. Action: review." in digest
    assert "Labels: new, repeated, cross-source, heating up, cooling down." in digest
    assert "First seen: 2026-07-07T08:00:00; latest seen: 2026-07-08T11:30:00." in digest
    assert "Sources: 2 sources; 4 mentions; messages db:1, db:2." in digest
    assert "Risks: thin liquidity, single-source." in digest
    assert "$CASHCHAT listing repeated" in digest


def test_latest_grading_output_is_ignored_when_window_does_not_match(tmp_path, caplog) -> None:
    requested_start = datetime(2026, 7, 8, 6)
    requested_end = datetime(2026, 7, 8, 12)
    stale_start = datetime(2026, 7, 7, 6)
    stale_end = datetime(2026, 7, 7, 12)
    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True)
    (output_dir / "latest.json").write_text(
        json.dumps(_grading_payload(stale_start, stale_end)),
        encoding="utf-8",
    )

    with caplog.at_level(logging.INFO):
        assert load_matching_grading_output(requested_start, requested_end, base_dir=tmp_path) is None

    assert "Skipping graded signal output" in caplog.text
    assert "2026-07-07T06:00:00 to 2026-07-07T12:00:00" in caplog.text
    assert "building digest without graded enrichment" in caplog.text


def test_matching_grading_output_logs_used_file_and_grade_count(tmp_path, caplog) -> None:
    window_start = datetime(2026, 7, 8, 6)
    window_end = datetime(2026, 7, 8, 12)
    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True)
    output_path = output_dir / "latest.json"
    output_path.write_text(
        json.dumps(_grading_payload(window_start, window_end)),
        encoding="utf-8",
    )

    with caplog.at_level(logging.INFO):
        payload = load_matching_grading_output(window_start, window_end, base_dir=tmp_path)

    assert payload is not None
    assert f"Using graded signal output from {output_path}" in caplog.text
    assert "2026-07-08T06:00:00 to 2026-07-08T12:00:00 with 1 grades" in caplog.text


@pytest.mark.parametrize(
    "content",
    [
        "{not json",
        json.dumps(_grading_payload(datetime(2026, 7, 8, 6), datetime(2026, 7, 8, 12), schema_version="1.0")),
    ],
)
def test_invalid_or_legacy_grading_output_falls_back(tmp_path, content: str) -> None:
    window_start = datetime(2026, 7, 8, 6)
    window_end = datetime(2026, 7, 8, 12)
    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True)
    (output_dir / "latest.json").write_text(content, encoding="utf-8")

    assert load_matching_grading_output(window_start, window_end, base_dir=tmp_path) is None


def test_valid_schema_1_1_grading_output_with_invalid_grade_falls_back(tmp_path) -> None:
    window_start = datetime(2026, 7, 8, 6)
    window_end = datetime(2026, 7, 8, 12)
    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True)
    payload = _grading_payload(window_start, window_end)
    del payload["grades"][0]["grade"]
    (output_dir / "latest.json").write_text(json.dumps(payload), encoding="utf-8")

    assert load_matching_grading_output(window_start, window_end, base_dir=tmp_path) is None


def test_missing_grading_output_falls_back_without_enrichment(tmp_path) -> None:
    digest = build_fallback_digest(
        "window",
        [
            _message(
                "$CASHCHAT listing repeated",
                9,
                "alpha",
                [(EntityType.ticker, "$CASHCHAT")],
            )
        ],
        grading_output=load_matching_grading_output(
            datetime(2026, 7, 8, 6),
            datetime(2026, 7, 8, 12),
            base_dir=tmp_path,
        ),
    )

    assert "Grade A" not in digest
    assert "$CASHCHAT (1 mentions)" in digest


def test_daily_digest_uses_matching_daily_grading_output(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
    tmp_path,
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "fallback")
    from app.config import get_settings

    get_settings.cache_clear()
    source = Source(name="@alpha", type=SourceType.telegram.value, identifier="@alpha")
    session.add(source)
    session.commit()
    message = Message(
        source_id=source.id,
        external_id="42",
        content="$CASHCHAT listing repeated",
        created_at=datetime(2026, 7, 8, 6, 30),
        content_hash="cashchat-daily",
        score=9,
    )
    message.entities.append(
        ExtractedEntity(entity_type=EntityType.ticker.value, value="$CASHCHAT")
    )
    session.add(message)
    session.commit()
    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True)
    window_start = datetime.combine(date(2026, 7, 8), datetime.min.time())
    window_end = window_start + timedelta(days=1)
    (output_dir / "latest.json").write_text(
        json.dumps(_grading_payload(window_start, window_end)),
        encoding="utf-8",
    )

    summary = build_digest(session, date(2026, 7, 8), grading_base_dir=tmp_path)

    assert "## Repeated Signals Across Sources" in summary.content
    assert "Grade A / high priority / 0.86 confidence" in summary.content


def test_window_digest_uses_matching_grading_output(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
    tmp_path,
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "fallback")
    from app.config import get_settings

    get_settings.cache_clear()
    source = Source(name="@alpha", type=SourceType.telegram.value, identifier="@alpha")
    session.add(source)
    session.commit()
    message = Message(
        source_id=source.id,
        external_id="42",
        content="$CASHCHAT listing repeated",
        created_at=datetime(2026, 7, 8, 6, 30),
        content_hash="cashchat-window",
        score=9,
    )
    message.entities.append(
        ExtractedEntity(entity_type=EntityType.ticker.value, value="$CASHCHAT")
    )
    session.add(message)
    session.commit()
    output_dir = tmp_path / "output"
    output_dir.mkdir(parents=True)
    window_start = datetime(2026, 7, 8, 6)
    window_end = datetime(2026, 7, 8, 12)
    (output_dir / "latest.json").write_text(
        json.dumps(_grading_payload(window_start, window_end)),
        encoding="utf-8",
    )

    summary = build_window_digest(
        session,
        window_start,
        window_end,
        grading_base_dir=tmp_path,
    )

    assert "## Open Signals" in summary.content
    assert "## Repeated Signals Across Sources" not in summary.content
    assert "$CASHCHAT — 🟢 LONG/WATCH — Grade A / high / 0.86" in summary.content


@pytest.mark.parametrize("phrase", ["bullish on", "positive on", "supporting"])
def test_open_positions_render_green_direction_markers(phrase: str) -> None:
    digest = build_fallback_digest(
        "window",
        [
            _message(
                f"Fund is {phrase} $SOL after mainnet momentum",
                9.0,
                "alpha",
                [(EntityType.ticker, "$SOL")],
                external_id="buy-1",
            ),
        ],
    )
    open_positions = digest.split("## Open Positions", 1)[1].split(
        "## Links Worth Reviewing", 1
    )[0]

    assert "green dot $SOL buy/open/accumulate confidence=0.75" in open_positions
    assert "external_id=buy-1" in open_positions
    assert "$SOL" in open_positions


@pytest.mark.parametrize("phrase", ["bearish on", "negative on", "dumping"])
def test_open_positions_render_red_direction_markers(phrase: str) -> None:
    digest = build_fallback_digest(
        "window",
        [
            _message(
                f"Trader is {phrase} $ETH into strength",
                8.0,
                "alpha",
                [(EntityType.ticker, "$ETH")],
                external_id="sell-1",
            ),
        ],
    )
    open_positions = digest.split("## Open Positions", 1)[1].split(
        "## Links Worth Reviewing", 1
    )[0]

    assert "red dot $ETH sell/close/reduce confidence=0.75" in open_positions
    assert "external_id=sell-1" in open_positions
    assert "$ETH" in open_positions


def test_open_positions_ignores_ambiguous_directional_messages() -> None:
    digest = build_fallback_digest(
        "window",
        [
            _message(
                "Maybe bullish on $SOL, unconfirmed rumor",
                9.0,
                "alpha",
                [(EntityType.ticker, "$SOL")],
                external_id="ambiguous-1",
            )
        ],
    )
    open_positions = digest.split("## Open Positions", 1)[1].split(
        "## Links Worth Reviewing", 1
    )[0]

    assert "- No directional position signals classified yet." in open_positions
    assert "Maybe bullish on $SOL" not in open_positions


def test_open_positions_allows_unrelated_not_phrase() -> None:
    digest = build_fallback_digest(
        "window",
        [
            _message(
                "Fund is bullish on $SOL, not financial advice",
                9.0,
                "alpha",
                [(EntityType.ticker, "$SOL")],
                external_id="buy-1",
            )
        ],
    )
    open_positions = digest.split("## Open Positions", 1)[1].split(
        "## Links Worth Reviewing", 1
    )[0]

    assert "green dot $SOL buy/open/accumulate confidence=0.75" in open_positions
