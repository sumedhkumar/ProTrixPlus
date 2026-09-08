#!/usr/bin/env python3
"""Signal simulator: POST a versioned sample webhook envelope to the api.

Usage:
    python infra/scripts/simulate_signal.py                # one BUY signal
    python infra/scripts/simulate_signal.py --count 3
    python infra/scripts/simulate_signal.py --signal-id fixed-1   # replay-safe
    python infra/scripts/simulate_signal.py --arm-timeout          # via API only if wired

No third-party deps: uses urllib so it runs anywhere Python 3 does.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def build_envelope(signal_id: str, *, action: str, symbol: str) -> dict:
    env = {
        "schema_version": "1.0",
        "strategy_key": "trend-rider",
        "strategy_version": "2025.09",
        "signal_id": signal_id,
        "event_time_utc": _now_iso(),
        "action": action,
        "symbol": symbol,
        "timeframe": "15m",
        "master_lot_info": {
            "master_lot": "1.00",
            "note": "informational only - not authoritative",
        },
    }
    if action == "BUY":
        env["stop_loss"] = "1.07500"
        env["take_profit"] = "1.09000"
    return env


def post(api_url: str, token: str, payload: dict) -> tuple[int, dict]:
    req = urllib.request.Request(
        f"{api_url}/webhook/tradingview",
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "X-Webhook-Token": token},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read() or b"{}")
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--api-url", default=os.environ.get("PROTRIX_API_URL", "http://localhost:8000")
    )
    ap.add_argument(
        "--token",
        default=os.environ.get(
            "PROTRIX_WEBHOOK_SHARED_SECRET", "dev-webhook-token-change-me"
        ),
    )
    ap.add_argument("--count", type=int, default=1)
    ap.add_argument("--signal-id", default=None, help="fixed id (to test idempotency)")
    ap.add_argument("--action", default="BUY", choices=["BUY", "SELL"])
    ap.add_argument("--symbol", default="EURUSD")
    args = ap.parse_args()

    rc = 0
    for i in range(args.count):
        sid = args.signal_id or f"sim-{uuid.uuid4().hex[:12]}"
        status, body = post(
            args.api_url,
            args.token,
            build_envelope(sid, action=args.action, symbol=args.symbol),
        )
        print(f"[{i + 1}/{args.count}] {status} {json.dumps(body)}")
        if status not in (200, 202):
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
