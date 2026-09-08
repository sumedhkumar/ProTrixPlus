"""The frozen TradingView webhook envelope (schema v1.0).

Two layers of validation:

1. :func:`validate_envelope` runs the raw dict through the frozen JSON Schema
   (``webhook_envelope.v1.json``). This is the authoritative wire check - it is
   the same file other languages consume.
2. :class:`WebhookEnvelope` is a typed Pydantic view for ergonomic access in
   Python code. Decimal-ish fields stay as strings here; callers convert with
   :mod:`protrix_contracts.money` where a Decimal is actually needed.

``master_lot_info`` is deliberately kept as an opaque mapping: it is
informational only and must never be read for sizing or risk.
"""

from __future__ import annotations

import enum
from typing import Any

from jsonschema import Draft7Validator, FormatChecker
from pydantic import BaseModel, ConfigDict, Field

from protrix_contracts.schemas import load_webhook_envelope_schema

SCHEMA_VERSION = "1.0"


class Action(str, enum.Enum):
    BUY = "BUY"
    SELL = "SELL"
    CLOSE = "CLOSE"
    PARTIAL_CLOSE = "PARTIAL_CLOSE"
    MODIFY_SLTP = "MODIFY_SLTP"
    EMERGENCY_CLOSE = "EMERGENCY_CLOSE"


class CommandTarget(str, enum.Enum):
    """The coarse target of a command.

    This is the fan-out dimension that keeps intents unique: a single signal can
    only ever produce one intent per user per ``command_target``.
    """

    ENTRY = "ENTRY"
    CLOSE = "CLOSE"
    MODIFY = "MODIFY"
    EMERGENCY = "EMERGENCY"


_ACTION_TO_TARGET: dict[Action, CommandTarget] = {
    Action.BUY: CommandTarget.ENTRY,
    Action.SELL: CommandTarget.ENTRY,
    Action.CLOSE: CommandTarget.CLOSE,
    Action.PARTIAL_CLOSE: CommandTarget.CLOSE,
    Action.MODIFY_SLTP: CommandTarget.MODIFY,
    Action.EMERGENCY_CLOSE: CommandTarget.EMERGENCY,
}

MANAGEMENT_ACTIONS: frozenset[Action] = frozenset(
    {Action.CLOSE, Action.PARTIAL_CLOSE, Action.MODIFY_SLTP, Action.EMERGENCY_CLOSE}
)


def command_target_for_action(action: Action | str) -> CommandTarget:
    return _ACTION_TO_TARGET[Action(action)]


class EnvelopeValidationError(ValueError):
    """Raised when a payload does not satisfy the frozen JSON Schema."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors) or "invalid webhook envelope")


# format_checker enforces "format": "date-time"; the schema also carries an
# explicit regex on event_time_utc so non-Python consumers get the same rule.
_validator = Draft7Validator(load_webhook_envelope_schema(), format_checker=FormatChecker())


def validate_envelope(payload: Any) -> dict[str, Any]:
    """Strictly validate ``payload`` against the frozen schema.

    Returns the payload unchanged on success; raises
    :class:`EnvelopeValidationError` with every schema violation on failure.
    """
    if not isinstance(payload, dict):
        raise EnvelopeValidationError(["payload must be a JSON object"])
    errors = sorted(_validator.iter_errors(payload), key=lambda e: list(e.absolute_path))
    if errors:
        messages = [
            f"{'/'.join(str(p) for p in e.absolute_path) or '<root>'}: {e.message}" for e in errors
        ]
        raise EnvelopeValidationError(messages)
    return payload


class MasterLotInfo(BaseModel):
    model_config = ConfigDict(extra="allow")

    master_lot: str | None = None
    note: str | None = None


class WebhookEnvelope(BaseModel):
    """Typed view of a *already schema-validated* envelope."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: str = Field(pattern=r"^1\.0$")
    strategy_key: str
    strategy_version: str
    signal_id: str
    event_time_utc: str
    action: Action
    symbol: str
    timeframe: str
    position_ref: str | None = None
    close_fraction: str | None = None
    stop_loss: str | None = None
    take_profit: str | None = None
    master_lot_info: MasterLotInfo | None = None

    @property
    def command_target(self) -> CommandTarget:
        return command_target_for_action(self.action)

    @classmethod
    def from_validated(cls, payload: dict[str, Any]) -> WebhookEnvelope:
        """Build from a payload that has already passed :func:`validate_envelope`."""
        return cls.model_validate(payload)
