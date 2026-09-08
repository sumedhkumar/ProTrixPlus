"""Unit: schema validation accepts valid envelopes and rejects malformed ones."""

from __future__ import annotations

import copy

import pytest

from protrix_contracts.envelope import (
    Action,
    CommandTarget,
    EnvelopeValidationError,
    WebhookEnvelope,
    command_target_for_action,
    validate_envelope,
)
from protrix_contracts.schemas import (
    load_webhook_envelope_schema,
    webhook_envelope_schema_text,
)

VALID_BUY: dict = {
    "schema_version": "1.0",
    "strategy_key": "trend-rider",
    "strategy_version": "2025.09",
    "signal_id": "sig-abc-001",
    "event_time_utc": "2026-09-08T10:15:00Z",
    "action": "BUY",
    "symbol": "EURUSD",
    "timeframe": "15m",
    "stop_loss": "1.07500",
    "take_profit": "1.09000",
    "master_lot_info": {"master_lot": "1.00", "note": "informational only"},
}

VALID_PARTIAL_CLOSE: dict = {
    "schema_version": "1.0",
    "strategy_key": "trend-rider",
    "strategy_version": "2025.09",
    "signal_id": "sig-abc-002",
    "event_time_utc": "2026-09-08T11:00:00Z",
    "action": "PARTIAL_CLOSE",
    "symbol": "EURUSD",
    "timeframe": "15m",
    "position_ref": "master-pos-77",
    "close_fraction": "0.5",
}


def test_accepts_valid_entry() -> None:
    assert validate_envelope(copy.deepcopy(VALID_BUY)) == VALID_BUY
    env = WebhookEnvelope.from_validated(VALID_BUY)
    assert env.action is Action.BUY
    assert env.command_target is CommandTarget.ENTRY


def test_accepts_valid_management_action() -> None:
    validate_envelope(copy.deepcopy(VALID_PARTIAL_CLOSE))
    env = WebhookEnvelope.from_validated(VALID_PARTIAL_CLOSE)
    assert env.command_target is CommandTarget.CLOSE


@pytest.mark.parametrize(
    "mutate",
    [
        pytest.param(lambda p: p.pop("signal_id"), id="missing-signal_id"),
        pytest.param(lambda p: p.update(schema_version="2.0"), id="wrong-schema_version"),
        pytest.param(lambda p: p.update(action="LIQUIDATE"), id="unknown-action"),
        pytest.param(lambda p: p.update(symbol="eur/usd lowercase"), id="bad-symbol"),
        pytest.param(lambda p: p.update(stop_loss=1.075), id="float-not-string"),
        pytest.param(lambda p: p.update(extra_field="nope"), id="additional-property"),
        pytest.param(lambda p: p.update(event_time_utc="not-a-date"), id="bad-timestamp"),
    ],
)
def test_rejects_malformed(mutate) -> None:
    payload = copy.deepcopy(VALID_BUY)
    mutate(payload)
    with pytest.raises(EnvelopeValidationError):
        validate_envelope(payload)


def test_management_action_requires_position_ref() -> None:
    payload = copy.deepcopy(VALID_PARTIAL_CLOSE)
    payload.pop("position_ref")
    with pytest.raises(EnvelopeValidationError):
        validate_envelope(payload)


def test_partial_close_requires_close_fraction() -> None:
    payload = copy.deepcopy(VALID_PARTIAL_CLOSE)
    payload.pop("close_fraction")
    with pytest.raises(EnvelopeValidationError):
        validate_envelope(payload)


def test_command_target_mapping_is_total() -> None:
    for action in Action:
        assert isinstance(command_target_for_action(action), CommandTarget)


def test_packaged_schema_matches_contracts_dir_copy() -> None:
    """The /contracts/schemas copy and the packaged copy must never drift."""
    from pathlib import Path

    repo_copy = Path(__file__).resolve().parents[2] / "schemas" / "webhook_envelope.v1.json"
    assert repo_copy.read_text(encoding="utf-8") == webhook_envelope_schema_text()
    assert load_webhook_envelope_schema()["properties"]["schema_version"]["const"] == "1.0"
