from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.database import Base
from app.db.models import EntityType, ExtractedEntity, Message, Source, SourceType
from app.processing.repeated_signals import (
    build_repeated_signals,
    detect_repeated_signals,
)


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
    with session_factory() as db_session:
        yield db_session


def add_source(session: Session, identifier: str, *, quality_score: float = 1.0) -> Source:
    source = Source(
        name=identifier,
        type=SourceType.telegram.value,
        identifier=identifier,
        quality_score=quality_score,
    )
    session.add(source)
    session.commit()
    session.refresh(source)
    return source


def add_message(
    session: Session,
    *,
    source: Source,
    content: str,
    created_at: datetime,
    content_hash: str,
    entities: list[tuple[str, str]],
    score: float = 1.0,
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


def signal_by_key(signals):
    return {(signal.signal_type, signal.signal_key): signal for signal in signals}


def test_groups_same_ticker_across_multiple_messages(session: Session) -> None:
    source = add_source(session, "@alpha")
    first = add_message(
        session,
        source=source,
        content="$abc launch",
        created_at=datetime(2026, 7, 8, 7),
        content_hash="first",
        entities=[(EntityType.ticker.value, "$abc")],
        score=3,
    )
    second = add_message(
        session,
        source=source,
        content="$ABC follow up",
        created_at=datetime(2026, 7, 8, 8),
        content_hash="second",
        entities=[(EntityType.ticker.value, "$ABC")],
        score=5,
    )

    signals = build_repeated_signals(
        session,
        datetime(2026, 7, 8, 6),
        datetime(2026, 7, 8, 12),
    )

    signal = signal_by_key(signals)[(EntityType.ticker.value, "$ABC")]
    assert signal.aliases == ("$abc",)
    assert signal.chain == "unknown"
    assert signal.mention_count == 2
    assert signal.source_count == 1
    assert signal.source_message_ids == (f"db:{second.id}", f"db:{first.id}")
    assert signal.labels == ("repeated",)


def test_groups_contract_addresses_with_chain_normalization(session: Session) -> None:
    source = add_source(session, "@contracts")
    evm = "0x1234567890ABCDEF1234567890ABCDEF12345678"
    solana = "7xKXtg2CW87d97TXJSDpbD5jBkheTqA83TZRuJosgKNS"
    add_message(
        session,
        source=source,
        content=f"EVM {evm} Solana {solana}",
        created_at=datetime(2026, 7, 8, 7),
        content_hash="one",
        entities=[
            (EntityType.contract_address.value, evm),
            (EntityType.contract_address.value, solana),
        ],
    )
    add_message(
        session,
        source=source,
        content=f"again {evm.lower()} and {solana}",
        created_at=datetime(2026, 7, 8, 8),
        content_hash="two",
        entities=[
            (EntityType.contract_address.value, evm.lower()),
            (EntityType.contract_address.value, solana),
        ],
    )

    signals = signal_by_key(
        build_repeated_signals(
            session,
            datetime(2026, 7, 8, 6),
            datetime(2026, 7, 8, 12),
        )
    )

    assert signals[(EntityType.contract_address.value, evm.lower())].chain == "evm"
    assert signals[(EntityType.contract_address.value, evm.lower())].aliases == (evm,)
    assert signals[(EntityType.contract_address.value, solana)].chain == "solana"
    assert signals[(EntityType.contract_address.value, solana)].aliases == ()


def test_distinct_sources_drive_ranking_and_labels(session: Session) -> None:
    source_one = add_source(session, "@one")
    source_two = add_source(session, "@two")
    add_message(
        session,
        source=source_one,
        content="$SAME first",
        created_at=datetime(2026, 7, 8, 7),
        content_hash="same-one",
        entities=[(EntityType.ticker.value, "$SAME")],
    )
    add_message(
        session,
        source=source_one,
        content="$SAME second",
        created_at=datetime(2026, 7, 8, 8),
        content_hash="same-two",
        entities=[(EntityType.ticker.value, "$SAME")],
    )
    add_message(
        session,
        source=source_one,
        content="$CROSS one",
        created_at=datetime(2026, 7, 8, 9),
        content_hash="cross-one",
        entities=[(EntityType.ticker.value, "$CROSS")],
    )
    add_message(
        session,
        source=source_two,
        content="$CROSS two",
        created_at=datetime(2026, 7, 8, 10),
        content_hash="cross-two",
        entities=[(EntityType.ticker.value, "$CROSS")],
    )

    signals = build_repeated_signals(
        session,
        datetime(2026, 7, 8, 6),
        datetime(2026, 7, 8, 12),
    )

    assert [signal.signal_key for signal in signals] == ["$CROSS", "$SAME"]
    assert signals[0].score == 22
    assert signals[0].labels == ("repeated", "cross-source")
    assert signals[0].source_identifiers == ("@one", "@two")


def test_duplicate_entity_rows_do_not_inflate_mention_counts(session: Session) -> None:
    source = add_source(session, "@alpha")
    message = add_message(
        session,
        source=source,
        content="$ABC $ABC",
        created_at=datetime(2026, 7, 8, 7),
        content_hash="dupe-entities",
        entities=[
            (EntityType.ticker.value, "$ABC"),
            (EntityType.ticker.value, "$ABC"),
        ],
    )

    signal = signal_by_key(
        detect_repeated_signals(
            [message],
            datetime(2026, 7, 8, 6),
            datetime(2026, 7, 8, 12),
            include_singletons=True,
        )
    )[(EntityType.ticker.value, "$ABC")]

    assert signal.mention_count == 1
    assert signal.source_count == 1
    assert signal.source_message_ids == (f"db:{message.id}",)


def test_exact_duplicate_content_hash_does_not_inflate_counts(session: Session) -> None:
    source_one = add_source(session, "@one")
    source_two = add_source(session, "@two")
    first = add_message(
        session,
        source=source_one,
        content="$ABC copied call",
        created_at=datetime(2026, 7, 8, 7),
        content_hash="same-hash",
        entities=[(EntityType.ticker.value, "$ABC")],
        score=5,
    )
    duplicate = Message(
        id=99,
        source_id=source_two.id,
        content="$ABC copied call",
        created_at=datetime(2026, 7, 8, 8),
        content_hash="same-hash",
        score=9,
        source=source_two,
        entities=[ExtractedEntity(entity_type=EntityType.ticker.value, value="$ABC")],
    )

    signal = signal_by_key(
        detect_repeated_signals(
            [duplicate, first],
            datetime(2026, 7, 8, 6),
            datetime(2026, 7, 8, 12),
            include_singletons=True,
        )
    )[(EntityType.ticker.value, "$ABC")]

    assert signal.mention_count == 1
    assert signal.source_count == 1
    assert signal.source_identifiers == ("@two",)
    assert signal.source_message_ids == ("db:99",)


def test_near_identical_content_does_not_inflate_counts(session: Session) -> None:
    source_one = add_source(session, "@one")
    source_two = add_source(session, "@two")
    first = add_message(
        session,
        source=source_one,
        content="$ABC is breaking out!!! https://example.test/a",
        created_at=datetime(2026, 7, 8, 7),
        content_hash="near-one",
        entities=[(EntityType.ticker.value, "$ABC")],
        score=4,
    )
    second = add_message(
        session,
        source=source_two,
        content="$ABC is breaking out... http://example.test/b",
        created_at=datetime(2026, 7, 8, 8),
        content_hash="near-two",
        entities=[(EntityType.ticker.value, "$ABC")],
        score=6,
    )

    signal = signal_by_key(
        detect_repeated_signals(
            [first, second],
            datetime(2026, 7, 8, 6),
            datetime(2026, 7, 8, 12),
            include_singletons=True,
        )
    )[(EntityType.ticker.value, "$ABC")]

    assert signal.mention_count == 1
    assert signal.source_count == 1
    assert signal.source_identifiers == ("@two",)
    assert signal.source_message_ids == (f"db:{second.id}",)


def test_audit_ids_source_identifiers_aliases_labels_and_evidence(session: Session) -> None:
    source_one = add_source(session, "@one")
    source_two = add_source(session, "@two")
    first = add_message(
        session,
        source=source_one,
        content="$abc " + ("long " * 80),
        created_at=datetime(2026, 7, 8, 7),
        content_hash="audit-one",
        entities=[(EntityType.ticker.value, "$abc")],
        score=2,
    )
    second = add_message(
        session,
        source=source_two,
        content="$ABC concise evidence",
        created_at=datetime(2026, 7, 8, 8),
        content_hash="audit-two",
        entities=[(EntityType.ticker.value, "$ABC")],
        score=8,
    )

    signal = build_repeated_signals(
        session,
        datetime(2026, 7, 8, 6),
        datetime(2026, 7, 8, 12),
    )[0]

    assert signal.signal_key == "$ABC"
    assert signal.aliases == ("$abc",)
    assert signal.source_identifiers == ("@one", "@two")
    assert signal.source_message_ids == (f"db:{second.id}", f"db:{first.id}")
    assert signal.labels == ("repeated", "cross-source")
    assert signal.evidence[0]["message_id"] == f"db:{second.id}"
    assert signal.evidence[0]["source_identifier"] == "@two"
    assert signal.evidence[0]["snippet"] == "$ABC concise evidence"
    assert len(signal.evidence[1]["snippet"]) <= 220


def test_single_source_single_message_signals_are_omitted_by_default(session: Session) -> None:
    source = add_source(session, "@alpha")
    add_message(
        session,
        source=source,
        content="$ABC single",
        created_at=datetime(2026, 7, 8, 7),
        content_hash="single",
        entities=[(EntityType.ticker.value, "$ABC")],
    )

    assert (
        build_repeated_signals(
            session,
            datetime(2026, 7, 8, 6),
            datetime(2026, 7, 8, 12),
        )
        == []
    )


def test_direct_detection_ignores_messages_outside_window(session: Session) -> None:
    source = add_source(session, "@alpha")
    inside = add_message(
        session,
        source=source,
        content="$ABC inside",
        created_at=datetime(2026, 7, 8, 7),
        content_hash="inside-window",
        entities=[(EntityType.ticker.value, "$ABC")],
    )
    before_window = add_message(
        session,
        source=source,
        content="$ABC before",
        created_at=datetime(2026, 7, 8, 5),
        content_hash="before-window",
        entities=[(EntityType.ticker.value, "$ABC")],
    )
    at_window_end = add_message(
        session,
        source=source,
        content="$ABC end",
        created_at=datetime(2026, 7, 8, 12),
        content_hash="at-window-end",
        entities=[(EntityType.ticker.value, "$ABC")],
    )

    signals = signal_by_key(
        detect_repeated_signals(
            [inside, before_window, at_window_end],
            datetime(2026, 7, 8, 6),
            datetime(2026, 7, 8, 12),
            include_singletons=True,
        )
    )

    signal = signals[(EntityType.ticker.value, "$ABC")]
    assert signal.mention_count == 1
    assert signal.source_message_ids == (f"db:{inside.id}",)
