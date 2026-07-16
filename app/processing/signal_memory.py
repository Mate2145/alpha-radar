from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import EntityType, Message
from app.processing.extract_entities import EVM_CONTRACT_RE


@dataclass(frozen=True)
class SignalMemory:
    signal_type: str
    signal_key: str
    aliases: tuple[str, ...]
    chain: str
    first_seen: datetime
    latest_seen: datetime
    mention_count: int
    source_count: int
    source_identifiers: tuple[str, ...]
    source_message_ids: tuple[str, ...]
    labels: tuple[str, ...] = field(default_factory=tuple)
    current_mention_count: int = 0
    current_source_count: int = 0


@dataclass
class _MemoryAccumulator:
    signal_type: str
    signal_key: str
    chain: str
    first_seen: datetime
    latest_seen: datetime
    aliases: set[str]
    message_refs: list[tuple[datetime, int, str]]
    source_ids: set[int]
    source_identifiers: set[str]
    current_message_ids: set[int]
    current_source_ids: set[int]


def build_signal_memory(session: Session, *, before: datetime | None = None) -> list[SignalMemory]:
    messages = load_memory_messages(session, before=before)
    return aggregate_signal_memory(messages)


def build_signal_memory_for_window(
    session: Session,
    window_start: datetime,
    window_end: datetime,
) -> list[SignalMemory]:
    messages = load_memory_messages(session, before=window_end)
    current_signal_keys = {
        signal_key
        for message in messages
        if window_start <= message.created_at < window_end
        for signal_key in signal_keys_for_message(message)
    }
    return aggregate_signal_memory(
        messages,
        current_window=(window_start, window_end),
        include_keys=current_signal_keys,
    )


def load_memory_messages(session: Session, *, before: datetime | None) -> list[Message]:
    statement = (
        select(Message)
        .options(selectinload(Message.source), selectinload(Message.entities))
        .order_by(Message.created_at.asc(), Message.id.asc())
    )
    if before is not None:
        statement = statement.where(Message.created_at < before)
    return list(session.scalars(statement).all())


def aggregate_signal_memory(
    messages: list[Message],
    *,
    current_window: tuple[datetime, datetime] | None = None,
    include_keys: set[tuple[str, str]] | None = None,
) -> list[SignalMemory]:
    accumulators: dict[tuple[str, str], _MemoryAccumulator] = {}

    for message in messages:
        message_signal_keys = signal_keys_for_message(message)
        for key, aliases in message_signal_keys.items():
            if include_keys is not None and key not in include_keys:
                continue
            signal_type, signal_key = key
            accumulator = accumulators.setdefault(
                key,
                _MemoryAccumulator(
                    signal_type=signal_type,
                    signal_key=signal_key,
                    chain=chain_for_signal(signal_type, signal_key),
                    first_seen=message.created_at,
                    latest_seen=message.created_at,
                    aliases=set(),
                    message_refs=[],
                    source_ids=set(),
                    source_identifiers=set(),
                    current_message_ids=set(),
                    current_source_ids=set(),
                ),
            )
            accumulator.first_seen = min(accumulator.first_seen, message.created_at)
            accumulator.latest_seen = max(accumulator.latest_seen, message.created_at)
            accumulator.aliases.update(aliases)
            accumulator.message_refs.append((message.created_at, message.id, db_message_id(message)))
            accumulator.source_ids.add(message.source_id)
            accumulator.source_identifiers.add(message.source.identifier)
            if current_window and current_window[0] <= message.created_at < current_window[1]:
                accumulator.current_message_ids.add(message.id)
                accumulator.current_source_ids.add(message.source_id)

    memories = [render_memory(accumulator) for accumulator in accumulators.values()]
    memories.sort(key=lambda memory: (memory.signal_type, memory.signal_key))
    return memories


def signal_keys_for_message(message: Message) -> dict[tuple[str, str], set[str]]:
    keys: dict[tuple[str, str], set[str]] = {}
    for entity in message.entities:
        if entity.entity_type == EntityType.ticker.value:
            key = (EntityType.ticker.value, normalize_ticker(entity.value))
            keys.setdefault(key, set()).add(entity.value.strip())
        elif entity.entity_type == EntityType.contract_address.value:
            key = (EntityType.contract_address.value, normalize_contract(entity.value))
            keys.setdefault(key, set()).add(entity.value.strip())
    return keys


def render_memory(accumulator: _MemoryAccumulator) -> SignalMemory:
    message_ids = tuple(
        message_id
        for _, _, message_id in sorted(
            set(accumulator.message_refs),
            key=lambda item: (item[0], item[1]),
        )
    )
    current_mention_count = len(accumulator.current_message_ids)
    current_source_count = len(accumulator.current_source_ids)
    labels = labels_for_counts(
        mention_count=len(message_ids),
        current_mention_count=current_mention_count,
        current_source_count=current_source_count,
    )
    return SignalMemory(
        signal_type=accumulator.signal_type,
        signal_key=accumulator.signal_key,
        aliases=tuple(sorted(accumulator.aliases - {accumulator.signal_key})),
        chain=accumulator.chain,
        first_seen=accumulator.first_seen,
        latest_seen=accumulator.latest_seen,
        mention_count=len(message_ids),
        source_count=len(accumulator.source_ids),
        source_identifiers=tuple(sorted(accumulator.source_identifiers)),
        source_message_ids=message_ids,
        labels=labels,
        current_mention_count=current_mention_count,
        current_source_count=current_source_count,
    )


def labels_for_window_memory(memory: SignalMemory) -> tuple[str, ...]:
    return labels_for_counts(
        mention_count=memory.mention_count,
        current_mention_count=memory.current_mention_count,
        current_source_count=memory.current_source_count,
    )


def labels_for_counts(
    *,
    mention_count: int,
    current_mention_count: int,
    current_source_count: int,
) -> tuple[str, ...]:
    if current_mention_count == 0:
        return ()

    labels = []
    if mention_count == current_mention_count:
        labels.append("new")
    if current_mention_count >= 2:
        labels.append("repeated")
    if current_source_count >= 2:
        labels.append("cross-source")
    return tuple(labels)


def normalize_ticker(value: str) -> str:
    stripped = value.strip()
    if not stripped.startswith("$"):
        stripped = f"${stripped}"
    return stripped.upper()


def normalize_contract(value: str) -> str:
    stripped = value.strip()
    if EVM_CONTRACT_RE.fullmatch(stripped):
        return stripped.lower()
    return stripped


def chain_for_signal(signal_type: str, signal_key: str) -> str:
    if signal_type != EntityType.contract_address.value:
        return "unknown"
    if EVM_CONTRACT_RE.fullmatch(signal_key):
        return "evm"
    return "solana"


def db_message_id(message: Message) -> str:
    return f"db:{message.id}"
