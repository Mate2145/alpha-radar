from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.database import Base
from app.db.models import EntityType, ExtractedEntity, Message, Source, SourceType
from app.processing.signal_memory import (
    build_signal_memory,
    build_signal_memory_for_window,
    labels_for_window_memory,
)


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with session_factory() as db_session:
        yield db_session


def add_source(session: Session, identifier: str) -> Source:
    source = Source(name=identifier, type=SourceType.telegram.value, identifier=identifier)
    session.add(source)
    session.commit()
    session.refresh(source)
    return source


def add_message(
    session: Session,
    *,
    source: Source,
    created_at: datetime,
    content_hash: str,
    entities: list[tuple[str, str]],
) -> Message:
    message = Message(
        source_id=source.id,
        content=" ".join(value for _, value in entities) or "no signal",
        created_at=created_at,
        content_hash=content_hash,
        score=1.0,
    )
    message.entities = [
        ExtractedEntity(entity_type=entity_type, value=value)
        for entity_type, value in entities
    ]
    session.add(message)
    session.commit()
    session.refresh(message)
    return message


def memory_by_key(memories):
    return {(memory.signal_type, memory.signal_key): memory for memory in memories}


def test_build_signal_memory_tracks_history_and_audit_ids(session: Session) -> None:
    source_one = add_source(session, "@one")
    source_two = add_source(session, "@two")
    first = add_message(
        session,
        source=source_one,
        created_at=datetime(2026, 7, 8, 7),
        content_hash="first",
        entities=[(EntityType.ticker.value, "$abc")],
    )
    latest = add_message(
        session,
        source=source_two,
        created_at=datetime(2026, 7, 8, 9),
        content_hash="latest",
        entities=[(EntityType.ticker.value, "$ABC")],
    )

    memories = memory_by_key(build_signal_memory(session))
    memory = memories[(EntityType.ticker.value, "$ABC")]

    assert memory.first_seen == first.created_at
    assert memory.latest_seen == latest.created_at
    assert memory.mention_count == 2
    assert memory.source_count == 2
    assert memory.source_identifiers == ("@one", "@two")
    assert memory.source_message_ids == (f"db:{first.id}", f"db:{latest.id}")
    assert memory.aliases == ("$abc",)
    assert memory.labels == ()


def test_build_signal_memory_dedupes_duplicate_entities_per_message(session: Session) -> None:
    source = add_source(session, "@alpha")
    message = add_message(
        session,
        source=source,
        created_at=datetime(2026, 7, 8, 7),
        content_hash="dupes",
        entities=[
            (EntityType.ticker.value, "$ABC"),
            (EntityType.ticker.value, "$ABC"),
        ],
    )

    memory = memory_by_key(build_signal_memory(session))[(EntityType.ticker.value, "$ABC")]

    assert memory.mention_count == 1
    assert memory.source_count == 1
    assert memory.source_message_ids == (f"db:{message.id}",)


def test_build_signal_memory_supports_contract_chains(session: Session) -> None:
    source = add_source(session, "@alpha")
    evm = "0x1234567890ABCDEF1234567890ABCDEF12345678"
    solana = "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgKNS"
    add_message(
        session,
        source=source,
        created_at=datetime(2026, 7, 8, 7),
        content_hash="contracts",
        entities=[
            (EntityType.contract_address.value, evm),
            (EntityType.contract_address.value, solana),
        ],
    )

    memories = memory_by_key(build_signal_memory(session))

    assert memories[(EntityType.contract_address.value, evm.lower())].chain == "evm"
    assert memories[(EntityType.contract_address.value, evm.lower())].aliases == (evm,)
    assert memories[(EntityType.contract_address.value, solana)].chain == "solana"
    assert memories[(EntityType.contract_address.value, solana)].aliases == ()


def test_build_signal_memory_respects_before_cutoff(session: Session) -> None:
    source = add_source(session, "@alpha")
    add_message(
        session,
        source=source,
        created_at=datetime(2026, 7, 8, 7),
        content_hash="inside",
        entities=[(EntityType.ticker.value, "$ABC")],
    )
    add_message(
        session,
        source=source,
        created_at=datetime(2026, 7, 8, 10),
        content_hash="outside",
        entities=[(EntityType.ticker.value, "$LATE")],
    )

    memories = memory_by_key(build_signal_memory(session, before=datetime(2026, 7, 8, 9)))

    assert (EntityType.ticker.value, "$ABC") in memories
    assert (EntityType.ticker.value, "$LATE") not in memories


def test_build_signal_memory_for_window_adds_current_window_labels(session: Session) -> None:
    source_one = add_source(session, "@one")
    source_two = add_source(session, "@two")
    add_message(
        session,
        source=source_one,
        created_at=datetime(2026, 7, 8, 6),
        content_hash="prior",
        entities=[(EntityType.ticker.value, "$OLD")],
    )
    old_current = add_message(
        session,
        source=source_one,
        created_at=datetime(2026, 7, 8, 13),
        content_hash="old-current",
        entities=[(EntityType.ticker.value, "$OLD")],
    )
    new_first = add_message(
        session,
        source=source_one,
        created_at=datetime(2026, 7, 8, 14),
        content_hash="new-first",
        entities=[(EntityType.ticker.value, "$NEW")],
    )
    new_second = add_message(
        session,
        source=source_two,
        created_at=datetime(2026, 7, 8, 15),
        content_hash="new-second",
        entities=[(EntityType.ticker.value, "$NEW")],
    )

    memories = memory_by_key(
        build_signal_memory_for_window(
            session,
            datetime(2026, 7, 8, 12),
            datetime(2026, 7, 8, 18),
        )
    )

    old_memory = memories[(EntityType.ticker.value, "$OLD")]
    new_memory = memories[(EntityType.ticker.value, "$NEW")]
    assert old_memory.first_seen == datetime(2026, 7, 8, 6)
    assert old_memory.current_mention_count == 1
    assert old_memory.source_message_ids[-1] == f"db:{old_current.id}"
    assert labels_for_window_memory(old_memory) == ()
    assert new_memory.first_seen == new_first.created_at
    assert new_memory.latest_seen == new_second.created_at
    assert new_memory.current_mention_count == 2
    assert new_memory.current_source_count == 2
    assert new_memory.source_message_ids == (f"db:{new_first.id}", f"db:{new_second.id}")
    assert labels_for_window_memory(new_memory) == ("new", "repeated", "cross-source")
