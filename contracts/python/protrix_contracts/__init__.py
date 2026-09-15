"""Protrixplus shared contract package.

Everything in here is a *contract* that both ``api`` and ``worker`` must agree
on at all times:

* :mod:`protrix_contracts.envelope` - the frozen TradingView webhook envelope
  (schema v1.0) plus strict validation and ``command_target`` derivation.
* :mod:`protrix_contracts.hashing` - deterministic canonical payload hashing
  used for the signal idempotency / dedupe key.
* :mod:`protrix_contracts.lifecycle` - the execution lifecycle state machine and
  its transition validator.
* :mod:`protrix_contracts.money` - Decimal helpers with explicit rounding. No
  binary floats anywhere near money, lots, prices or rates.
* :mod:`protrix_contracts.rent` - deterministic rent calculation rules.
* :mod:`protrix_contracts.db` - shared SQLAlchemy models and session helpers.
  PostgreSQL is the source of truth; these models declare the constraints that
  the database enforces.
"""

from protrix_contracts.envelope import (
    SCHEMA_VERSION,
    Action,
    CommandTarget,
    WebhookEnvelope,
    command_target_for_action,
    validate_envelope,
)
from protrix_contracts.hashing import canonical_payload, canonical_payload_hash
from protrix_contracts.lifecycle import (
    ExecutionState,
    InvalidTransitionError,
    assert_transition,
    can_transition,
)
from protrix_contracts.rent import (
    DEFAULT_RENT_RATE,
    calculate_rent_due,
    signed_rent_charge,
    validate_rent_rate,
)

__all__ = [
    "SCHEMA_VERSION",
    "Action",
    "CommandTarget",
    "WebhookEnvelope",
    "command_target_for_action",
    "validate_envelope",
    "canonical_payload",
    "canonical_payload_hash",
    "ExecutionState",
    "InvalidTransitionError",
    "assert_transition",
    "can_transition",
    "DEFAULT_RENT_RATE",
    "calculate_rent_due",
    "signed_rent_charge",
    "validate_rent_rate",
]

__version__ = "1.0.0"
