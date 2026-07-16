import re
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import Message
from app.processing.signal_memory import (
    chain_for_signal,
    db_message_id,
    signal_keys_for_message,
)

_URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
_NON_WORD_RE = re.compile(r"[^\w$]+")
_WHITESPACE_RE = re.compile(r"\s+")
_SNIPPET_LIMIT = 220


@dataclass(frozen=True)
class RepeatedSignal:
    signal_type: str
    signal_key: str
    aliases: tuple[str, ...]
    chain: str
    window_start: datetime
    window_end: datetime
    mention_count: int
    source_count: int
    source_identifiers: tuple[str, ...]
    source_message_ids: tuple[str, ...]
    evidence: tuple[dict[str, str], ...]
    score: int
    labels: tuple[str, ...] = field(default_factory=tuple)


@dataclass
class _SignalAccumulator:
    signal_type: str
    signal_key: str
    aliases: set[str]
    counted_messages: list[Message]
    seen_content_hashes: set[str]
    seen_near_duplicate_keys: set[str]


def build_repeated_signals(
    session: Session,
    window_start: datetime,
    window_end: datetime,
    *,
    include_singletons: bool = False,
) -> list[RepeatedSignal]:
    statement = (
        select(Message)
        .options(selectinload(Message.source), selectinload(Message.entities))
        .where(Message.created_at >= window_start)
        .where(Message.created_at < window_end)
        .order_by(Message.score.desc(), Message.created_at.desc(), Message.id.desc())
    )
    messages = list(session.scalars(statement).all())
    return detect_repeated_signals(
        messages,
        window_start,
        window_end,
        include_singletons=include_singletons,
    )


def detect_repeated_signals(
    messages: list[Message],
    window_start: datetime,
    window_end: datetime,
    *,
    include_singletons: bool = False,
) -> list[RepeatedSignal]:
    accumulators: dict[tuple[str, str], _SignalAccumulator] = {}
    window_messages = [
        message for message in messages if window_start <= message.created_at < window_end
    ]
    for message in sorted(window_messages, key=_message_sort_key, reverse=True):
        for key, aliases in signal_keys_for_message(message).items():
            accumulator = accumulators.setdefault(
                key,
                _SignalAccumulator(
                    signal_type=key[0],
                    signal_key=key[1],
                    aliases=set(),
                    counted_messages=[],
                    seen_content_hashes=set(),
                    seen_near_duplicate_keys=set(),
                ),
            )
            accumulator.aliases.update(aliases)
            if _is_duplicate_for_signal(message, accumulator):
                continue
            accumulator.counted_messages.append(message)
            accumulator.seen_content_hashes.add(message.content_hash)
            accumulator.seen_near_duplicate_keys.add(near_duplicate_key(message.content))

    signals = [
        _render_signal(accumulator, window_start, window_end)
        for accumulator in accumulators.values()
        if include_singletons or _is_repeated(accumulator)
    ]
    signals.sort(
        key=lambda signal: (
            -signal.score,
            -signal.source_count,
            -signal.mention_count,
            signal.signal_key,
        )
    )
    return signals


def near_duplicate_key(content: str) -> str:
    text = _URL_RE.sub(" ", content.lower())
    text = _NON_WORD_RE.sub(" ", text)
    return _WHITESPACE_RE.sub(" ", text).strip()


def _is_duplicate_for_signal(message: Message, accumulator: _SignalAccumulator) -> bool:
    if message.content_hash in accumulator.seen_content_hashes:
        return True
    return near_duplicate_key(message.content) in accumulator.seen_near_duplicate_keys


def _is_repeated(accumulator: _SignalAccumulator) -> bool:
    return len(accumulator.counted_messages) >= 2 or len(_source_ids(accumulator.counted_messages)) >= 2


def _render_signal(
    accumulator: _SignalAccumulator,
    window_start: datetime,
    window_end: datetime,
) -> RepeatedSignal:
    messages = accumulator.counted_messages
    source_identifiers = tuple(sorted({message.source.identifier for message in messages}))
    source_count = len(_source_ids(messages))
    mention_count = len(messages)
    score = source_count * 10 + mention_count
    return RepeatedSignal(
        signal_type=accumulator.signal_type,
        signal_key=accumulator.signal_key,
        aliases=tuple(sorted(accumulator.aliases - {accumulator.signal_key})),
        chain=chain_for_signal(accumulator.signal_type, accumulator.signal_key),
        window_start=window_start,
        window_end=window_end,
        mention_count=mention_count,
        source_count=source_count,
        source_identifiers=source_identifiers,
        source_message_ids=tuple(db_message_id(message) for message in messages),
        evidence=tuple(_evidence_for_message(message) for message in messages),
        score=score,
        labels=_labels(mention_count=mention_count, source_count=source_count),
    )


def _evidence_for_message(message: Message) -> dict[str, str]:
    return {
        "message_id": db_message_id(message),
        "source_identifier": message.source.identifier,
        "snippet": _snippet(message.content),
    }


def _snippet(content: str) -> str:
    snippet = _WHITESPACE_RE.sub(" ", content).strip()
    if len(snippet) <= _SNIPPET_LIMIT:
        return snippet
    return snippet[: _SNIPPET_LIMIT - 3].rstrip() + "..."


def _labels(*, mention_count: int, source_count: int) -> tuple[str, ...]:
    labels = []
    if mention_count >= 2:
        labels.append("repeated")
    if source_count >= 2:
        labels.append("cross-source")
    return tuple(labels)


def _source_ids(messages: list[Message]) -> set[int]:
    return {message.source_id for message in messages}


def _message_sort_key(message: Message) -> tuple[float, datetime, int]:
    return (message.score, message.created_at, message.id)
