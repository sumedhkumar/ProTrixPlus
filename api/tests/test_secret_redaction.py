"""Invariant: no secret appears in any log line.

The root-logger redaction filter must scrub known secret substrings from the
message, args, and extra string fields of every record.
"""

from __future__ import annotations

import json
import logging

import pytest

from app.config import Settings
from app.logging_config import REDACTION, configure_logging


def test_known_secrets_are_redacted(capsys: pytest.CaptureFixture[str]) -> None:
    settings = Settings(
        dev_jwt_secret="super-secret-jwt-value",
        webhook_shared_secret="super-secret-webhook-value",
        database_url="postgresql+psycopg://u:pgpassword123@db:5432/x",
    )
    configure_logging(level="INFO", service="api-test", secrets=settings.secret_values())
    log = logging.getLogger("api-test.redaction")

    log.info("token=%s hook=%s", "super-secret-jwt-value", "super-secret-webhook-value")
    log.info("dsn has pgpassword123 in it")
    log.warning("nested", extra={"detail": "leak super-secret-jwt-value here"})
    for handler in logging.getLogger().handlers:
        handler.flush()

    captured = capsys.readouterr()
    blob = captured.err + captured.out

    assert "super-secret-jwt-value" not in blob
    assert "super-secret-webhook-value" not in blob
    assert "pgpassword123" not in blob
    assert REDACTION in blob

    for line in blob.strip().splitlines():
        json.loads(line)  # still structured JSON
