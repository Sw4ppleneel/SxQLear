from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from config import settings


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models in the local memory database."""
    pass


# Local SQLite engine — single-file, no server required.
# This stores all analytical memory: projects, snapshots, decisions, annotations.
engine = create_engine(
    f"sqlite:///{settings.memory_db_path}",
    connect_args={"check_same_thread": False},
    echo=settings.debug,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """FastAPI dependency that yields a database session and ensures cleanup."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables. Called on application startup."""
    from db import orm_models  # noqa: F401 — registers models with Base
    Base.metadata.create_all(bind=engine)
