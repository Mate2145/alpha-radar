from datetime import datetime
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.database import Base
from app.db.models import EntityType, ExtractedEntity, Message, Source, SourceType
from app.summarization import digest_builder
from app.summarization.digest_builder import (
    build_fallback_digest,
    build_window_digest,
    render_digest,
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

    assert "## Open Positions" in summary.content
    assert "## Raw High-Score Messages" in summary.content
    assert "external_id=42" in summary.content


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
