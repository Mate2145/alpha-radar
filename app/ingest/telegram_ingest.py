import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import ExtractedEntity, Message, Source, SourceType
from app.processing.deduplicate import content_hash
from app.processing.extract_entities import extract_entities, extract_tickers
from app.processing.score_messages import score_content


def ingest_telegram(session: Session) -> int:
    settings = get_settings()
    channels = settings.telegram_source_channel_list
    if not channels or not settings.telegram_api_id or not settings.telegram_api_hash:
        return 0

    since = datetime.now(timezone.utc) - timedelta(hours=settings.telegram_ingest_lookback_hours)
    messages = asyncio.run(load_recent_telegram_messages(channels, since))
    return persist_telegram_messages(session, messages)


@dataclass(frozen=True)
class TelegramSmokeMessage:
    channel: str
    content: str
    created_at: datetime
    url: str | None = None
    external_id: str | None = None


@dataclass(frozen=True)
class TelegramSignalMatch:
    channel: str
    created_at: datetime
    content: str
    url: str | None = None


@dataclass(frozen=True)
class TelegramSignalSmokeResult:
    found: bool
    expected_signal: str
    inspected_channels: int
    inspected_messages: int
    matches: list[TelegramSignalMatch]


def run_telegram_signal_smoke_test(
    lookback_hours: int = 24,
    expected_signal: str = "$cashchat",
) -> TelegramSignalSmokeResult:
    settings = get_settings()
    channels = settings.telegram_source_channel_list
    if len(channels) != 2:
        raise RuntimeError("TELEGRAM_SOURCE_CHANNELS must contain exactly two channels")
    if not settings.telegram_api_id or not settings.telegram_api_hash:
        raise RuntimeError("TELEGRAM_API_ID and TELEGRAM_API_HASH must be configured")

    since = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    messages = asyncio.run(load_recent_telegram_messages(channels, since))
    return evaluate_telegram_signal_smoke(messages, expected_signal, inspected_channels=len(channels))


async def load_recent_telegram_messages(
    channels: list[str],
    since: datetime,
) -> list[TelegramSmokeMessage]:
    settings = get_settings()
    if not settings.telegram_api_id or not settings.telegram_api_hash:
        raise RuntimeError("TELEGRAM_API_ID and TELEGRAM_API_HASH must be configured")

    try:
        from telethon import TelegramClient
    except ImportError as exc:
        raise RuntimeError("Telethon is required for Telegram history smoke tests") from exc

    messages: list[TelegramSmokeMessage] = []
    async with TelegramClient(
        settings.telegram_session_name,
        settings.telegram_api_id,
        settings.telegram_api_hash,
    ) as client:
        for channel in channels:
            async for raw_message in client.iter_messages(channel):
                created_at = normalize_datetime(raw_message.date)
                if created_at < since:
                    break
                content = raw_message.message or ""
                if not content.strip():
                    continue
                messages.append(
                    TelegramSmokeMessage(
                        channel=channel,
                        content=content,
                        created_at=created_at,
                        url=build_message_url(channel, raw_message.id),
                        external_id=str(raw_message.id),
                    )
                )
    return messages


def persist_telegram_messages(session: Session, messages: list[TelegramSmokeMessage]) -> int:
    count = 0
    sources_by_channel: dict[str, Source] = {}
    for raw_message in messages:
        source = sources_by_channel.get(raw_message.channel)
        if source is None:
            source = upsert_telegram_source(session, raw_message.channel)
            sources_by_channel[raw_message.channel] = source

        content = raw_message.content.strip()
        if not content:
            continue

        message = Message(
            source_id=source.id,
            external_id=raw_message.external_id,
            author=None,
            content=content,
            url=raw_message.url,
            created_at=to_db_datetime(raw_message.created_at),
            content_hash=content_hash(content),
            score=score_content(content, source.quality_score),
        )
        message.entities = [
            ExtractedEntity(entity_type=entity_type, value=value)
            for entity_type, value in extract_entities(content)
        ]
        session.add(message)
        try:
            session.commit()
            count += 1
        except IntegrityError:
            session.rollback()
    return count


def upsert_telegram_source(session: Session, channel: str) -> Source:
    source = session.scalar(
        select(Source).where(Source.type == SourceType.telegram.value, Source.identifier == channel)
    )
    if source:
        source.name = channel
        source.enabled = True
        session.commit()
        return source

    source = Source(name=channel, type=SourceType.telegram.value, identifier=channel, enabled=True)
    session.add(source)
    session.commit()
    session.refresh(source)
    return source


def evaluate_telegram_signal_smoke(
    messages: list[TelegramSmokeMessage],
    expected_signal: str,
    inspected_channels: int,
) -> TelegramSignalSmokeResult:
    normalized_signal = expected_signal.lower()
    matches = [
        TelegramSignalMatch(
            channel=message.channel,
            created_at=message.created_at,
            content=message.content,
            url=message.url,
        )
        for message in messages
        if "robinhood" in message.content.lower()
        and (
            normalized_signal in message.content.lower()
            or normalized_signal in {ticker.lower() for ticker in extract_tickers(message.content)}
        )
    ]
    return TelegramSignalSmokeResult(
        found=bool(matches),
        expected_signal=expected_signal,
        inspected_channels=inspected_channels,
        inspected_messages=len(messages),
        matches=matches,
    )


def normalize_datetime(value: datetime) -> datetime:
    if value.tzinfo:
        return value.astimezone(timezone.utc)
    return value.replace(tzinfo=timezone.utc)


def to_db_datetime(value: datetime) -> datetime:
    return normalize_datetime(value).replace(tzinfo=None)


def build_message_url(channel: str, message_id: int) -> str | None:
    public_channel = channel.strip().lstrip("@")
    if not public_channel or public_channel.startswith("-"):
        return None
    return f"https://t.me/{public_channel}/{message_id}"
