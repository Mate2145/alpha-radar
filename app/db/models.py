from datetime import date, datetime
from enum import Enum

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class SourceType(str, Enum):
    rss = "rss"
    telegram = "telegram"
    discord = "discord"


class EntityType(str, Enum):
    ticker = "ticker"
    url = "url"
    keyword = "keyword"
    contract_address = "contract_address"


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (UniqueConstraint("type", "identifier", name="uq_source_type_identifier"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    type: Mapped[SourceType] = mapped_column(String(32))
    identifier: Mapped[str] = mapped_column(String(1024))
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    quality_score: Mapped[float] = mapped_column(Float, default=1.0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    messages: Mapped[list["Message"]] = relationship(back_populates="source")


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (UniqueConstraint("content_hash", name="uq_message_content_hash"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("sources.id"))
    external_id: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    author: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content: Mapped[str] = mapped_column(Text)
    url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime)
    ingested_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    content_hash: Mapped[str] = mapped_column(String(64))
    score: Mapped[float] = mapped_column(Float, default=0.0)

    source: Mapped[Source] = relationship(back_populates="messages")
    entities: Mapped[list["ExtractedEntity"]] = relationship(
        back_populates="message", cascade="all, delete-orphan"
    )


class ExtractedEntity(Base):
    __tablename__ = "extracted_entities"

    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[int] = mapped_column(ForeignKey("messages.id"))
    entity_type: Mapped[EntityType] = mapped_column(String(32))
    value: Mapped[str] = mapped_column(String(2048))

    message: Mapped[Message] = relationship(back_populates="entities")


class DailySummary(Base):
    __tablename__ = "daily_summaries"
    __table_args__ = (UniqueConstraint("summary_date", name="uq_daily_summary_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    summary_date: Mapped[date] = mapped_column(Date)
    content: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class WindowSummary(Base):
    __tablename__ = "window_summaries"
    __table_args__ = (
        UniqueConstraint("window_start", "window_end", name="uq_window_summary_window"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    window_start: Mapped[datetime] = mapped_column(DateTime)
    window_end: Mapped[datetime] = mapped_column(DateTime)
    content: Mapped[str] = mapped_column(Text)
    model: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
