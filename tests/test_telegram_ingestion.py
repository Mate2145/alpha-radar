from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import select
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.database import Base
from app.db.models import ExtractedEntity, Message, Source, SourceType, WindowSummary
from app.ingest import telegram_ingest
from app.ingest.telegram_ingest import TelegramSmokeMessage, ingest_telegram
from app.summarization.digest_builder import build_digest, build_window_digest, load_messages_for_window


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with session_factory() as db_session:
        yield db_session


def async_loader(messages: list[TelegramSmokeMessage]):
    async def load(channels: list[str], since: datetime) -> list[TelegramSmokeMessage]:
        return messages

    return load


def test_ingest_telegram_persists_messages_entities_and_source(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
) -> None:
    monkeypatch.setattr(
        telegram_ingest,
        "get_settings",
        lambda: SimpleNamespace(
            telegram_source_channel_list=["@alpha_one", "@alpha_two"],
            telegram_api_id=123,
            telegram_api_hash="hash",
            telegram_ingest_lookback_hours=24,
        ),
    )
    monkeypatch.setattr(
        telegram_ingest,
        "load_recent_telegram_messages",
        async_loader([
            TelegramSmokeMessage(
                channel="@alpha_one",
                content="Robinhood lists $CASHCHAT https://example.com",
                created_at=datetime(2026, 7, 8, 10, tzinfo=timezone.utc),
                url="https://t.me/alpha_one/1",
                external_id="1",
            )
        ]),
    )

    count = ingest_telegram(session)

    assert count == 1
    source = session.scalar(select(Source).where(Source.type == SourceType.telegram.value))
    assert source is not None
    assert source.identifier == "@alpha_one"
    message = session.scalar(select(Message))
    assert message is not None
    assert message.source_id == source.id
    assert message.external_id == "1"
    assert message.url == "https://t.me/alpha_one/1"
    assert message.created_at == datetime(2026, 7, 8, 10)
    entities = {
        (entity.entity_type, entity.value)
        for entity in session.scalars(select(ExtractedEntity)).all()
    }
    assert ("ticker", "$CASHCHAT") in entities
    assert ("url", "https://example.com") in entities


def test_ingest_telegram_returns_zero_when_unconfigured(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
) -> None:
    monkeypatch.setattr(
        telegram_ingest,
        "get_settings",
        lambda: SimpleNamespace(
            telegram_source_channel_list=[],
            telegram_api_id=None,
            telegram_api_hash=None,
            telegram_ingest_lookback_hours=24,
        ),
    )

    assert ingest_telegram(session) == 0
    assert session.scalars(select(Message)).all() == []


def test_ingest_telegram_skips_duplicate_content(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
) -> None:
    raw_message = TelegramSmokeMessage(
        channel="@alpha_one",
        content="Same $CASHCHAT message",
        created_at=datetime(2026, 7, 8, 10, tzinfo=timezone.utc),
        external_id="1",
    )
    monkeypatch.setattr(
        telegram_ingest,
        "get_settings",
        lambda: SimpleNamespace(
            telegram_source_channel_list=["@alpha_one"],
            telegram_api_id=123,
            telegram_api_hash="hash",
            telegram_ingest_lookback_hours=24,
        ),
    )
    monkeypatch.setattr(
        telegram_ingest,
        "load_recent_telegram_messages",
        async_loader([raw_message]),
    )

    assert ingest_telegram(session) == 1
    assert ingest_telegram(session) == 0
    assert len(session.scalars(select(Message)).all()) == 1


def test_build_digest_includes_ingested_telegram_message(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "fallback")
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setattr(
        telegram_ingest,
        "get_settings",
        lambda: SimpleNamespace(
            telegram_source_channel_list=["@alpha_one"],
            telegram_api_id=123,
            telegram_api_hash="hash",
            telegram_ingest_lookback_hours=24,
        ),
    )
    monkeypatch.setattr(
        telegram_ingest,
        "load_recent_telegram_messages",
        async_loader([
            TelegramSmokeMessage(
                channel="@alpha_one",
                content="$CASHCHAT airdrop on Robinhood",
                created_at=datetime(2026, 7, 8, 10, tzinfo=timezone.utc),
                external_id="1",
            )
        ]),
    )

    ingest_telegram(session)
    summary = build_digest(session, date(2026, 7, 8))

    assert "$CASHCHAT" in summary.content
    assert "Robinhood" in summary.content
    assert "fallback-rule-based" == summary.model


def test_build_window_digest_selects_exact_window_and_stores_separate_summaries(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "fallback")
    from app.config import get_settings

    get_settings.cache_clear()
    source = Source(name="@alpha", type=SourceType.telegram.value, identifier="@alpha")
    session.add(source)
    session.commit()
    messages = [
        Message(
            source_id=source.id,
            content="$OLD before window",
            created_at=datetime(2026, 7, 8, 5, 59),
            content_hash="old",
            score=10,
        ),
        Message(
            source_id=source.id,
            content="$IN inside window",
            created_at=datetime(2026, 7, 8, 6, 0),
            content_hash="in",
            score=9,
        ),
        Message(
            source_id=source.id,
            content="$OUT at exclusive end",
            created_at=datetime(2026, 7, 8, 12, 0),
            content_hash="out",
            score=8,
        ),
    ]
    session.add_all(messages)
    session.commit()

    selected = load_messages_for_window(
        session,
        datetime(2026, 7, 8, 6),
        datetime(2026, 7, 8, 12),
    )
    assert [message.content for message in selected] == ["$IN inside window"]

    first = build_window_digest(
        session,
        datetime(2026, 7, 8, 6),
        datetime(2026, 7, 8, 12),
    )
    second = build_window_digest(
        session,
        datetime(2026, 7, 8, 12),
        datetime(2026, 7, 8, 18),
    )

    assert first.id != second.id
    assert "$IN inside window" in first.content
    assert first.window_start == datetime(2026, 7, 8, 6)
    assert first.window_end == datetime(2026, 7, 8, 12)
    assert len(session.scalars(select(WindowSummary)).all()) == 2


def test_build_window_digest_updates_existing_matching_window(
    monkeypatch: pytest.MonkeyPatch,
    session: Session,
) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "fallback")
    from app.config import get_settings

    get_settings.cache_clear()

    first = build_window_digest(
        session,
        datetime(2026, 7, 8, 6),
        datetime(2026, 7, 8, 12),
    )
    second = build_window_digest(
        session,
        datetime(2026, 7, 8, 6),
        datetime(2026, 7, 8, 12),
    )

    summaries = session.scalars(select(WindowSummary)).all()
    assert first.id == second.id
    assert len(summaries) == 1
