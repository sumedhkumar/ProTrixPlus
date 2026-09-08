"""Engine / session factory for the worker process."""

from __future__ import annotations

from protrix_contracts.db import build_engine, build_session_factory
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker

_engine: Engine | None = None
_factory: sessionmaker[Session] | None = None


def init_db(database_url: str) -> None:
    global _engine, _factory
    _engine = build_engine(database_url)
    _factory = build_session_factory(_engine)


def engine() -> Engine:
    if _engine is None:
        raise RuntimeError("init_db() not called")
    return _engine


def session_factory() -> sessionmaker[Session]:
    if _factory is None:
        raise RuntimeError("init_db() not called")
    return _factory
