"""JSON logging + secret redaction for the worker.

Kept deliberately in sync with ``api/app/logging_config.py``. The worker has no
real secrets in S0, but the redaction filter still runs so a future credential
never leaks through a stray log call.
"""

from __future__ import annotations

import logging
from typing import Any

from pythonjsonlogger import json as jsonlogger

REDACTION = "***REDACTED***"


class SecretRedactionFilter(logging.Filter):
    def __init__(self, secrets: list[str]) -> None:
        super().__init__()
        self._secrets = sorted({s for s in secrets if s}, key=len, reverse=True)

    def _scrub(self, value: Any) -> Any:
        if isinstance(value, str):
            out = value
            for secret in self._secrets:
                if secret in out:
                    out = out.replace(secret, REDACTION)
            return out
        return value

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = self._scrub(record.getMessage())
            record.args = ()
        except Exception:  # pragma: no cover
            record.msg = "<unrenderable log record redacted>"
            record.args = ()
        for key, val in list(record.__dict__.items()):
            if isinstance(val, str):
                record.__dict__[key] = self._scrub(val)
        return True


def configure_logging(*, level: str, service: str, secrets: list[str] | None = None) -> None:
    root = logging.getLogger()
    root.setLevel(level.upper())
    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler()
    handler.setFormatter(
        jsonlogger.JsonFormatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s",
            rename_fields={"levelname": "level", "asctime": "ts", "name": "logger"},
        )
    )
    redaction = SecretRedactionFilter(secrets or [])
    handler.addFilter(redaction)
    root.addHandler(handler)
    root.addFilter(redaction)
    logging.getLogger(service).info("logging configured")
