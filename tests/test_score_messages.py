from datetime import date, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.database import Base
from app.db.models import EntityType, ExtractedEntity, Message, Source, SourceType
from app.processing.score_messages import apply_cross_source_bonus
from app.processing.score_messages import apply_cross_source_bonus_for_window
from app.processing.score_messages import score_content


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with session_factory() as db_session:
        yield db_session


def test_score_content_adds_expected_signals() -> None:
    score = score_content("$TIA airdrop launch https://example.com", source_quality=2.0)
    assert score == 8.0


def test_score_content_allows_plain_message() -> None:
    assert score_content("quiet market note", source_quality=1.5) == 1.5


def test_apply_cross_source_bonus_is_idempotent(session: Session) -> None:
    source_one = Source(
        name="one",
        type=SourceType.telegram.value,
        identifier="@one",
        quality_score=1.0,
    )
    source_two = Source(
        name="two",
        type=SourceType.telegram.value,
        identifier="@two",
        quality_score=1.0,
    )
    session.add_all([source_one, source_two])
    session.commit()

    first = Message(
        source_id=source_one.id,
        content="$TIA launch",
        created_at=datetime(2026, 7, 8, 10),
        content_hash="one",
        score=score_content("$TIA launch", source_one.quality_score),
    )
    first.entities = [
        ExtractedEntity(entity_type=EntityType.ticker.value, value="$TIA"),
        ExtractedEntity(entity_type=EntityType.keyword.value, value="launch"),
    ]
    second = Message(
        source_id=source_two.id,
        content="$TIA quiet",
        created_at=datetime(2026, 7, 8, 11),
        content_hash="two",
        score=score_content("$TIA quiet", source_two.quality_score),
    )
    second.entities = [ExtractedEntity(entity_type=EntityType.ticker.value, value="$TIA")]
    session.add_all([first, second])
    session.commit()

    apply_cross_source_bonus(session, date(2026, 7, 8))
    first_scores = [first.score, second.score]
    apply_cross_source_bonus(session, date(2026, 7, 8))

    assert [first.score, second.score] == first_scores


def test_apply_cross_source_bonus_for_window_uses_only_window_messages(session: Session) -> None:
    source_one = Source(
        name="one",
        type=SourceType.telegram.value,
        identifier="@one-window",
        quality_score=1.0,
    )
    source_two = Source(
        name="two",
        type=SourceType.telegram.value,
        identifier="@two-window",
        quality_score=1.0,
    )
    session.add_all([source_one, source_two])
    session.commit()

    inside_one = Message(
        source_id=source_one.id,
        content="$TIA launch",
        created_at=datetime(2026, 7, 8, 7),
        content_hash="inside-one",
        score=0,
    )
    inside_one.entities = [ExtractedEntity(entity_type=EntityType.ticker.value, value="$TIA")]
    inside_two = Message(
        source_id=source_two.id,
        content="$TIA update",
        created_at=datetime(2026, 7, 8, 8),
        content_hash="inside-two",
        score=0,
    )
    inside_two.entities = [ExtractedEntity(entity_type=EntityType.ticker.value, value="$TIA")]
    outside = Message(
        source_id=source_two.id,
        content="$OLD update",
        created_at=datetime(2026, 7, 8, 13),
        content_hash="outside",
        score=99,
    )
    outside.entities = [ExtractedEntity(entity_type=EntityType.ticker.value, value="$OLD")]
    session.add_all([inside_one, inside_two, outside])
    session.commit()

    apply_cross_source_bonus_for_window(
        session,
        datetime(2026, 7, 8, 6),
        datetime(2026, 7, 8, 12),
    )

    assert inside_one.score == 6.5
    assert inside_two.score == 5.0
    assert outside.score == 99
