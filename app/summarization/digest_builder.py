import re
from collections import Counter, defaultdict
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import DailySummary, EntityType, Message, WindowSummary
from app.processing.extract_entities import PositionSignal, extract_position_signals
from app.summarization.llm_client import LLMClient
from app.summarization.prompts import DIGEST_SYSTEM_PROMPT, DIGEST_USER_TEMPLATE

REQUIRED_DIGEST_HEADINGS = [
    "## Executive Summary",
    "## Top Narratives",
    "## Most Mentioned Tokens / Projects",
    "## Repeated Signals Across Sources",
    "## Open Positions",
    "## Links Worth Reviewing",
    "## Raw High-Score Messages",
]


def build_digest(session: Session, summary_date: date) -> DailySummary:
    messages = load_messages_for_date(session, summary_date)
    content, model = render_digest(summary_date.isoformat(), messages)

    existing = session.scalar(select(DailySummary).where(DailySummary.summary_date == summary_date))
    if existing:
        existing.content = content
        existing.model = model
        existing.created_at = datetime.utcnow()
        session.commit()
        session.refresh(existing)
        return existing

    summary = DailySummary(summary_date=summary_date, content=content, model=model)
    session.add(summary)
    session.commit()
    session.refresh(summary)
    return summary


def build_window_digest(
    session: Session,
    window_start: datetime,
    window_end: datetime,
) -> WindowSummary:
    if window_start >= window_end:
        raise RuntimeError("Window start must be before window end")

    messages = load_messages_for_window(session, window_start, window_end)
    label = f"{window_start.isoformat()} to {window_end.isoformat()}"
    content, model = render_digest(label, messages)

    existing = session.scalar(
        select(WindowSummary).where(
            WindowSummary.window_start == window_start,
            WindowSummary.window_end == window_end,
        )
    )
    if existing:
        existing.content = content
        existing.model = model
        existing.created_at = datetime.utcnow()
        session.commit()
        session.refresh(existing)
        return existing

    summary = WindowSummary(
        window_start=window_start,
        window_end=window_end,
        content=content,
        model=model,
    )
    session.add(summary)
    session.commit()
    session.refresh(summary)
    return summary


def render_digest(summary_label: str, messages: list[Message]) -> tuple[str, str]:
    client = LLMClient()
    if client.configured:
        content = client.complete(
            DIGEST_SYSTEM_PROMPT,
            DIGEST_USER_TEMPLATE.format(
                summary_date=summary_label,
                messages=format_messages_for_prompt(messages),
            ),
        )
        validate_digest_contract(content)
        return content, client.model_name
    return build_fallback_digest(summary_label, messages), "fallback-rule-based"


def load_messages_for_date(session: Session, summary_date: date) -> list[Message]:
    rows = session.scalars(
        select(Message)
        .options(selectinload(Message.source), selectinload(Message.entities))
        .where(Message.created_at >= summary_date)
        .order_by(Message.score.desc())
    ).all()
    return [message for message in rows if message.created_at.date() == summary_date]


def load_messages_for_window(
    session: Session,
    window_start: datetime,
    window_end: datetime,
) -> list[Message]:
    return list(
        session.scalars(
            select(Message)
            .options(selectinload(Message.source), selectinload(Message.entities))
            .where(Message.created_at >= window_start, Message.created_at < window_end)
            .order_by(Message.score.desc())
        ).all()
    )


def format_messages_for_prompt(messages: list[Message]) -> str:
    lines = []
    for message in messages[:80]:
        lines.append(
            f"- score={message.score:.1f} source={message.source.name} url={message.url or ''} "
            f"content={message.content[:500]}"
        )
    return "\n".join(lines)


def build_fallback_digest(
    summary_label: str,
    messages: list[Message],
    include_raw_messages: bool = True,
) -> str:
    tickers = Counter(
        entity.value
        for message in messages
        for entity in message.entities
        if entity.entity_type == EntityType.ticker.value
    )
    keywords = Counter(
        entity.value
        for message in messages
        for entity in message.entities
        if entity.entity_type == EntityType.keyword.value
    )
    links = [
        entity.value
        for message in messages
        for entity in message.entities
        if entity.entity_type == EntityType.url.value
    ]
    position_signals = collect_position_signals(messages)
    repeated = repeated_entities(messages)
    top_messages = messages[:10]

    return f"""# Crypto Alpha Digest - {summary_label}

## Executive Summary

Rule-based fallback digest generated from {len(messages)} messages. Configure LLM_PROVIDER for an AI-written summary.

## Top Narratives

{bullet_list(top_narratives(keywords))}

## Most Mentioned Tokens / Projects

{bullet_list([f"{ticker} ({count} mentions)" for ticker, count in tickers.most_common(10)])}

## Repeated Signals Across Sources

{bullet_list(repeated)}

## Open Positions

{bullet_list(open_positions(messages, position_signals))}

## Links Worth Reviewing

{bullet_list(links[:20])}

## Raw High-Score Messages

{raw_message_section(top_messages, include_raw_messages)}
"""


def top_narratives(keywords: Counter[str]) -> list[str]:
    return [
        f"{key} is a recurring narrative with {count} mentions."
        for key, count in keywords.most_common(10)
    ]


def collect_position_signals(messages: list[Message]) -> dict[str, list[PositionSignal]]:
    signals_by_source_id: dict[str, list[PositionSignal]] = {}
    for message in messages:
        source_id = message_source_id(message)
        signals_by_source_id[source_id] = extract_position_signals(
            message.content,
            source_message_id=source_id,
        )
    return signals_by_source_id


def open_positions(
    messages: list[Message],
    position_signals: dict[str, list[PositionSignal]],
) -> list[str]:
    signals: list[str] = []
    for message in messages:
        signals.extend(
            render_position_signal(signal, message)
            for signal in position_signals_for_message(message, position_signals)
        )
    if not signals:
        return ["No directional position signals classified yet."]
    return signals


def position_signals_for_message(
    message: Message,
    position_signals: dict[str, list[PositionSignal]],
) -> list[PositionSignal]:
    return position_signals.get(message_source_id(message), [])


def render_position_signal(signal: PositionSignal, message: Message) -> str:
    marker = "green dot" if signal.direction == "buy" else "red dot"
    direction_label = "buy/open/accumulate" if signal.direction == "buy" else "sell/close/reduce"
    return (
        f"{marker} {signal.token} {direction_label} "
        f"confidence={signal.confidence:.2f} source={message_locator(message)} "
        f"evidence=\"{signal.evidence_text}\""
    )


def validate_digest_contract(content: str) -> None:
    headings = re.findall(r"^## .+$", content, flags=re.MULTILINE)
    if headings != REQUIRED_DIGEST_HEADINGS:
        raise RuntimeError(
            "LLM digest did not follow required section structure: "
            + ", ".join(REQUIRED_DIGEST_HEADINGS)
        )

    top_narratives = content.split("## Top Narratives", 1)[1].split(
        "## Most Mentioned Tokens / Projects", 1
    )[0]
    bullets = [line.strip()[2:].strip() for line in top_narratives.splitlines() if line.startswith("- ")]
    invalid = [bullet for bullet in bullets if not is_single_sentence(bullet)]
    if invalid:
        raise RuntimeError("LLM digest Top Narratives must use brief one-sentence bullets")


def is_single_sentence(text: str) -> bool:
    sentence_endings = re.findall(r"[.!?](?:\s|$)", text)
    return len(text) <= 180 and len(sentence_endings) == 1 and text[-1] in ".!?"


def repeated_entities(messages: list[Message]) -> list[str]:
    sources_by_entity: dict[str, set[str]] = defaultdict(set)
    for message in messages:
        for entity in message.entities:
            if entity.entity_type in {EntityType.ticker.value, EntityType.keyword.value}:
                sources_by_entity[entity.value].add(message.source.name)
    return [
        f"{value} across {len(sources)} sources"
        for value, sources in sources_by_entity.items()
        if len(sources) > 1
    ]


def bullet_list(items: list[str]) -> str:
    if not items:
        return "- None found."
    return "\n".join(f"- {item}" for item in items)


def raw_message_section(messages: list[Message], include_raw_messages: bool) -> str:
    if include_raw_messages:
        return message_list(messages)
    return bullet_list(
        [
            f"{message_locator(message)} raw message hidden from digest."
            for message in messages
        ]
    )


def message_list(messages: list[Message]) -> str:
    if not messages:
        return "- None found."
    return "\n".join(
        f"- {message_locator(message)} score={message.score:.1f}: {message.content[:220]}"
        for message in messages
    )


def message_locator(message: Message) -> str:
    if getattr(message, "url", None):
        return f"[{message.source.name}] {message.url}"
    if getattr(message, "external_id", None):
        return f"[{message.source.name}] external_id={message.external_id}"
    if getattr(message, "id", None):
        return f"[{message.source.name}] message_id={message.id}"
    return f"[{message.source.name}]"


def message_source_id(message: Message) -> str:
    if getattr(message, "external_id", None):
        return str(message.external_id)
    if getattr(message, "id", None):
        return str(message.id)
    if getattr(message, "url", None):
        return str(message.url)
    return message.source.name
