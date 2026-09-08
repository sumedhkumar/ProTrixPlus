"""JSON logging with a hard secret-redaction filter.

The filter runs on every record on the root logger. It replaces any known secret
substring with ``***REDACTED***`` in the rendered message and in stringified
args, so a secret cannot reach stdout even if some call site logs it by mistake.
"""

from __future__ import annotations

import logging
from typing import Any

from pythonjsonlogger import json as jsonlogger

REDACTION = "***REDACTED***"


class SecretRedactionFilter(logging.Filter):
    def __init__(self, secrets: list[str]) -> None:
        super().__init__()
        # Longest first so overlapping secrets redact fully.
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
        except Exception:  # pragma: no cover - never let logging crash the app
            record.msg = "<unrenderable log record redacted>"
            record.args = ()
        for key, val in list(record.__dict__.items()):
            if isinstance(val, str):
                record.__dict__[key] = self._scrub(val)
        return True


def configure_logging(*, level: str, service: str, secrets: list[str]) -> None:
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
    redaction = SecretRedactionFilter(secrets)
    handler.addFilter(redaction)
    root.addHandler(handler)
    root.addFilter(redaction)

    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.LoggerAdapter(logging.getLogger(service), {"service": service})
