"""Engine / session factory helpers.

Sync SQLAlchemy on psycopg 3. The transactional outbox relay needs
``SELECT ... FOR UPDATE SKIP LOCKED`` semantics that are simplest to reason about
synchronously; both api and worker use threads, not a shared event loop.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from decimal import Decimal
from typing import Any

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def _json_default(value: Any) -> str:
    # JSONB columns must never carry a binary float. Decimals (e.g. from
    # json.loads(..., parse_float=Decimal)) are stored as their exact string form.
    if isinstance(value, Decimal):
        return format(value, "f")
    raise TypeError(f"not JSON-serializable for JSONB: {type(value).__name__}")


def _json_serializer(obj: Any) -> str:
    return json.dumps(obj, default=_json_default, separators=(",", ":"))


def normalize_database_url(url: str) -> str:
    """Force the psycopg (v3) driver regardless of how the URL is written."""
    if url.startswith("postgresql+psycopg://"):
        return url
    if url.startswith("postgresql+psycopg2://"):
        return "postgresql+psycopg://" + url.split("://", 1)[1]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url.split("://", 1)[1]
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url.split("://", 1)[1]
    return url


def build_engine(database_url: str, *, echo: bool = False) -> Engine:
    return create_engine(
        normalize_database_url(database_url),
        echo=echo,
        pool_pre_ping=True,
        future=True,
        json_serializer=_json_serializer,
    )


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


@contextmanager
def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    """Transactional scope: commit on success, roll back on any exception."""
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
