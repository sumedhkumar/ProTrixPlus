"""Unit: the webhook rejects unauthorized / malformed input before any write."""

from __future__ import annotations

import copy

import pytest
from fastapi.testclient import TestClient

VALID: dict = {
    "schema_version": "1.0",
    "strategy_key": "trend-rider",
    "strategy_version": "2025.09",
    "signal_id": "sig-unit-1",
    "event_time_utc": "2026-09-08T10:15:00Z",
    "action": "BUY",
    "symbol": "EURUSD",
    "timeframe": "15m",
}
TOKEN_HEADER = {"X-Webhook-Token": "dev-webhook-token-change-me"}


def test_missing_webhook_token_is_401(client_no_db: TestClient) -> None:
    r = client_no_db.post("/webhook/tradingview", json=VALID)
    assert r.status_code == 401


def test_wrong_webhook_token_is_401(client_no_db: TestClient) -> None:
    r = client_no_db.post("/webhook/tradingview", json=VALID, headers={"X-Webhook-Token": "nope"})
    assert r.status_code == 401


def test_non_json_body_is_400(client_no_db: TestClient) -> None:
    r = client_no_db.post("/webhook/tradingview", content=b"not json", headers=TOKEN_HEADER)
    assert r.status_code == 400


@pytest.mark.parametrize(
    "mutate",
    [
        lambda p: p.pop("signal_id"),
        lambda p: p.update(action="LIQUIDATE"),
        lambda p: p.update(schema_version="9.9"),
        lambda p: p.update(stop_loss=1.075),
        lambda p: p.update(action="CLOSE"),  # management action w/o position_ref
    ],
)
def test_malformed_payload_is_422(client_no_db: TestClient, mutate) -> None:
    payload = copy.deepcopy(VALID)
    mutate(payload)
    r = client_no_db.post("/webhook/tradingview", json=payload, headers=TOKEN_HEADER)
    assert r.status_code == 422
    assert "errors" in r.json()["detail"]
