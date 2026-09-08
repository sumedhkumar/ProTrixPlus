"""Pick the execution adapter from config. Only ``mock`` exists in S0."""

from __future__ import annotations

from redis import Redis
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.base import ExecutionAdapter
from app.adapters.mock import MockExecutionAdapter


def build_adapter(
    name: str, session_factory: sessionmaker[Session], redis: Redis
) -> ExecutionAdapter:
    if name == "mock":
        return MockExecutionAdapter(session_factory, redis)
    raise ValueError(
        f"unknown execution adapter {name!r}; S0 only ships 'mock' "
        "(MetaApiExecutionAdapter arrives in a later step - see docs/adr/ADR-001)"
    )
