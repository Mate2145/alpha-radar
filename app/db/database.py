from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


def get_engine():
    return create_engine(get_settings().database_url, future=True)


SessionLocal = sessionmaker(bind=get_engine(), autoflush=False, autocommit=False, future=True)


def get_session() -> Generator[Session, None, None]:
    with SessionLocal() as session:
        yield session

