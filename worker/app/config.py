"""Worker configuration (plain env, no secrets needed for the mock)."""

from __future__ import annotations

import os
import socket
from dataclasses import dataclass


def _get(name: str, default: str) -> str:
    return os.environ.get(name, default)


@dataclass(frozen=True)
class WorkerConfig:
    database_url: str
    redis_url: str
    signal_stream: str
    consumer_group: str
    consumer_name: str
    log_level: str
    service_name: str
    health_port: int
    execution_adapter: str
    relay_poll_seconds: float
    relay_batch: int
    reclaim_idle_ms: int
    catch_up_on_start: bool

    @classmethod
    def from_env(cls) -> WorkerConfig:
        return cls(
            database_url=_get(
                "PROTRIX_DATABASE_URL",
                "postgresql+psycopg://protrix:protrix@localhost:5432/protrix",
            ),
            redis_url=_get("PROTRIX_REDIS_URL", "redis://localhost:6379/0"),
            signal_stream=_get("PROTRIX_SIGNAL_STREAM", "protrix.signals.v1"),
            consumer_group=_get("PROTRIX_SIGNAL_CONSUMER_GROUP", "protrix-workers"),
            consumer_name=_get("PROTRIX_WORKER_NAME", f"worker-{socket.gethostname()}"),
            log_level=_get("PROTRIX_LOG_LEVEL", "INFO"),
            service_name=_get("PROTRIX_SERVICE_NAME", "worker"),
            health_port=int(_get("PROTRIX_WORKER_HEALTH_PORT", "8000")),
            execution_adapter=_get("PROTRIX_EXECUTION_ADAPTER", "mock"),
            relay_poll_seconds=float(_get("PROTRIX_RELAY_POLL_SECONDS", "0.5")),
            relay_batch=int(_get("PROTRIX_RELAY_BATCH", "50")),
            reclaim_idle_ms=int(_get("PROTRIX_RECLAIM_IDLE_MS", "30000")),
            catch_up_on_start=_get("PROTRIX_CATCH_UP_ON_START", "true").lower() == "true",
        )
