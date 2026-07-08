from collections import defaultdict
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import EntityType, Message
from app.processing.extract_entities import extract_keywords, extract_tickers, extract_urls


def score_content(content: str, source_quality: float = 1.0) -> float:
    score = float(source_quality)
    tickers = extract_tickers(content)
    keywords = extract_keywords(content)
    urls = extract_urls(content)
    if tickers:
        score += 2.0
    if keywords:
        score += 1.5 * len(keywords)
    if urls:
        score += 1.0
    return score


def apply_cross_source_bonus(session: Session, target_date: date) -> None:
    messages = session.scalars(
        select(Message)
        .options(selectinload(Message.source), selectinload(Message.entities))
        .where(Message.created_at >= target_date)
    ).all()
    same_day = [message for message in messages if message.created_at.date() == target_date]
    apply_cross_source_bonus_to_messages(session, same_day)


def apply_cross_source_bonus_for_window(
    session: Session,
    window_start: datetime,
    window_end: datetime,
) -> None:
    messages = list(
        session.scalars(
            select(Message)
            .options(selectinload(Message.source), selectinload(Message.entities))
            .where(Message.created_at >= window_start, Message.created_at < window_end)
        ).all()
    )
    apply_cross_source_bonus_to_messages(session, messages)


def apply_cross_source_bonus_to_messages(session: Session, messages: list[Message]) -> None:
    entity_sources: dict[tuple[str, str], set[int]] = defaultdict(set)

    for message in messages:
        for entity in message.entities:
            if entity.entity_type in {EntityType.ticker.value, EntityType.keyword.value}:
                entity_sources[(entity.entity_type, entity.value)].add(message.source_id)

    repeated = {key for key, sources in entity_sources.items() if len(sources) > 1}

    for message in messages:
        bonus = 2.0 if any(
            (entity.entity_type, entity.value) in repeated for entity in message.entities
        ) else 0.0
        message.score = score_content(message.content, message.source.quality_score) + bonus
    session.commit()
