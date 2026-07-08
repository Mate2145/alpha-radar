from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

import feedparser
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import ExtractedEntity, Message, Source, SourceType
from app.processing.deduplicate import content_hash
from app.processing.extract_entities import extract_entities
from app.processing.score_messages import score_content


def ingest_rss(session: Session) -> int:
    count = 0
    for feed_url in get_settings().rss_feed_urls:
        feed = feedparser.parse(feed_url)
        source = upsert_rss_source(session, feed_url, feed.feed.get("title", feed_url))
        for entry in feed.entries:
            content = entry.get("summary") or entry.get("description") or entry.get("title") or ""
            if not content.strip():
                continue
            message = Message(
                source_id=source.id,
                external_id=entry.get("id") or entry.get("guid") or entry.get("link"),
                author=entry.get("author"),
                content=content,
                url=entry.get("link"),
                created_at=parse_entry_datetime(entry),
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


def upsert_rss_source(session: Session, feed_url: str, name: str) -> Source:
    source = session.scalar(
        select(Source).where(Source.type == SourceType.rss.value, Source.identifier == feed_url)
    )
    if source:
        source.name = name
        source.enabled = True
        session.commit()
        return source

    source = Source(name=name, type=SourceType.rss.value, identifier=feed_url, enabled=True)
    session.add(source)
    session.commit()
    session.refresh(source)
    return source


def parse_entry_datetime(entry) -> datetime:
    value = entry.get("published") or entry.get("updated")
    if value:
        try:
            parsed = parsedate_to_datetime(value)
            if parsed.tzinfo:
                return parsed.astimezone(timezone.utc).replace(tzinfo=None)
            return parsed
        except (TypeError, ValueError):
            pass
    return datetime.utcnow()

