"""Worker configuration.

The default remains the deterministic mock adapter. The MT5 settings are read
only when the native Windows worker is explicitly switched to ``mt5``.
"""

from __future__ import annotations

import os
import socket
from dataclasses import dataclass


def _get(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _bool(name: str, default: bool) -> bool:
    return _get(name, str(default).lower()).lower() in {"1", "true", "yes", "on"}


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
    mt5_user_email: str
    mt5_path: str
    mt5_login: int
    mt5_password: str
    mt5_server: str
    mt5_trading_enabled: bool
    mt5_magic: int
    mt5_deviation_points: int
    mt5_timeout_seconds: float
    metaapi_token: str
    metaapi_trading_enabled: bool
    metaapi_magic: int
    metaapi_timeout_seconds: float
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
            mt5_user_email=_get("PROTRIX_MT5_USER_EMAIL", "alice@example.test"),
            mt5_path=_get(
                "PROTRIX_MT5_PATH",
                r"C:\Program Files\MetaTrader 5\terminal64.exe",
            ),
            mt5_login=int(_get("PROTRIX_MT5_LOGIN", "0")),
            mt5_password=_get("PROTRIX_MT5_PASSWORD", ""),
            mt5_server=_get("PROTRIX_MT5_SERVER", ""),
            mt5_trading_enabled=_bool("PROTRIX_MT5_TRADING_ENABLED", False),
            mt5_magic=int(_get("PROTRIX_MT5_MAGIC", "260909")),
            mt5_deviation_points=int(_get("PROTRIX_MT5_DEVIATION_POINTS", "20")),
            mt5_timeout_seconds=float(_get("PROTRIX_MT5_TIMEOUT_SECONDS", "30")),
            metaapi_token=_get("PROTRIX_METAAPI_TOKEN", ""),
            metaapi_trading_enabled=_bool("PROTRIX_METAAPI_TRADING_ENABLED", False),
            metaapi_magic=int(_get("PROTRIX_METAAPI_MAGIC", "260910")),
            metaapi_timeout_seconds=float(_get("PROTRIX_METAAPI_TIMEOUT_SECONDS", "30")),
            relay_poll_seconds=float(_get("PROTRIX_RELAY_POLL_SECONDS", "0.5")),
            relay_batch=int(_get("PROTRIX_RELAY_BATCH", "50")),
            reclaim_idle_ms=int(_get("PROTRIX_RECLAIM_IDLE_MS", "30000")),
            catch_up_on_start=_get("PROTRIX_CATCH_UP_ON_START", "true").lower() == "true",
        )
