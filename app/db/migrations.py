from app.db.database import Base, get_engine
from app.db import models  # noqa: F401


def init_db() -> None:
    Base.metadata.create_all(bind=get_engine())

