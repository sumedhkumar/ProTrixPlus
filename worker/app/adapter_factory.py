"""Pick the execution adapter from configuration."""

from __future__ import annotations

from redis import Redis
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.base import ExecutionAdapter
from app.adapters.mock import MockExecutionAdapter
from app.config import WorkerConfig


def build_adapter(
    name: str,
    session_factory: sessionmaker[Session],
    redis: Redis,
    config: WorkerConfig | None = None,
) -> ExecutionAdapter:
    if name == "mock":
        return MockExecutionAdapter(session_factory, redis)
    if name == "mt5":
        if config is None:
            raise ValueError("the mt5 adapter requires worker configuration")
        from app.adapters.mt5 import MetaTrader5ExecutionAdapter

        return MetaTrader5ExecutionAdapter(session_factory, config)
    raise ValueError(f"unknown execution adapter {name!r}; supported adapters are 'mock' and 'mt5'")
