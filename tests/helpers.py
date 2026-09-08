"""Shared helpers for the integration suite."""

from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx

from conftest import API_URL, WEBHOOK_TOKEN


def sample_envelope(signal_id: str | None = None, *, action: str = "BUY") -> dict[str, Any]:
    env: dict[str, Any] = {
        "schema_version": "1.0",
        "strategy_key": "trend-rider",
        "strategy_version": "2025.09",
        "signal_id": signal_id or f"it-{uuid.uuid4().hex[:12]}",
        "event_time_utc": datetime.now(UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "action": action,
        "symbol": "EURUSD",
        "timeframe": "15m",
        "master_lot_info": {"master_lot": "1.00", "note": "informational only"},
    }
    if action == "BUY":
        env["stop_loss"] = "1.07500"
        env["take_profit"] = "1.09000"
    return env


def post_signal(payload: dict[str, Any]) -> httpx.Response:
    return httpx.post(
        f"{API_URL}/webhook/tradingview",
        json=payload,
        headers={"X-Webhook-Token": WEBHOOK_TOKEN},
        timeout=10,
    )


def dev_token(role: str) -> str:
    r = httpx.post(f"{API_URL}/dev/login", json={"role": role}, timeout=10)
    r.raise_for_status()
    return str(r.json()["access_token"])


def api_get(path: str, token: str) -> Any:
    r = httpx.get(f"{API_URL}{path}", headers={"Authorization": f"Bearer {token}"}, timeout=10)
    r.raise_for_status()
    return r.json()


def poll_until(
    predicate: Callable[[], bool], *, timeout: float = 30.0, interval: float = 0.5
) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(interval)
    raise AssertionError(f"condition not met within {timeout}s")


def executions_for_signal(token: str, signal_ref: str) -> list[dict[str, Any]]:
    return [e for e in api_get("/api/v1/executions", token) if e["signal_ref"] == signal_ref]
