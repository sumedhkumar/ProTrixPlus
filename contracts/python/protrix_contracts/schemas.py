"""Access to the frozen JSON Schema files shipped inside this package."""

from __future__ import annotations

import json
from functools import cache
from importlib import resources
from typing import Any, cast

WEBHOOK_ENVELOPE_SCHEMA_FILE = "webhook_envelope.v1.json"
_DATA_PACKAGE = "protrix_contracts.data"


@cache
def load_webhook_envelope_schema() -> dict[str, Any]:
    """Return the parsed frozen webhook envelope JSON Schema (v1.0)."""
    text = (
        resources.files(_DATA_PACKAGE)
        .joinpath(WEBHOOK_ENVELOPE_SCHEMA_FILE)
        .read_text(encoding="utf-8")
    )
    return cast("dict[str, Any]", json.loads(text))


def webhook_envelope_schema_text() -> str:
    """Return the raw text of the frozen schema (used by drift tests)."""
    return (
        resources.files(_DATA_PACKAGE)
        .joinpath(WEBHOOK_ENVELOPE_SCHEMA_FILE)
        .read_text(encoding="utf-8")
    )
