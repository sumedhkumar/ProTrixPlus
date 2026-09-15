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


def build_envelope(
    signal_id: str,
    *,
    action: str,
    symbol: str,
    position_ref: str | None = None,
    close_fraction: str | None = None,
    stop_loss: str | None = None,
    take_profit: str | None = None,
) -> dict:
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
    if stop_loss is not None:
        env["stop_loss"] = stop_loss
    if take_profit is not None:
        env["take_profit"] = take_profit
    if position_ref is not None:
        env["position_ref"] = position_ref
    if close_fraction is not None:
        env["close_fraction"] = close_fraction
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
    ap.add_argument(
        "--action",
        default="BUY",
        choices=[
            "BUY",
            "SELL",
            "CLOSE",
            "PARTIAL_CLOSE",
            "MODIFY_SLTP",
            "EMERGENCY_CLOSE",
        ],
    )
    ap.add_argument("--symbol", default="EURUSD")
    ap.add_argument(
        "--position-ref",
        default=None,
        help="server-mapped reference for management actions",
    )
    ap.add_argument(
        "--close-fraction", default=None, help="required for PARTIAL_CLOSE, e.g. 0.50"
    )
    ap.add_argument("--stop-loss", default=None)
    ap.add_argument("--take-profit", default=None)
    args = ap.parse_args()

    if (
        args.action in {"CLOSE", "PARTIAL_CLOSE", "MODIFY_SLTP", "EMERGENCY_CLOSE"}
        and not args.position_ref
    ):
        ap.error("--position-ref is required for management actions")
    if args.action == "PARTIAL_CLOSE" and args.close_fraction is None:
        ap.error("--close-fraction is required for PARTIAL_CLOSE")

    rc = 0
    for i in range(args.count):
        sid = args.signal_id or f"sim-{uuid.uuid4().hex[:12]}"
        status, body = post(
            args.api_url,
            args.token,
            build_envelope(
                sid,
                action=args.action,
                symbol=args.symbol,
                position_ref=args.position_ref,
                close_fraction=args.close_fraction,
                stop_loss=args.stop_loss,
                take_profit=args.take_profit,
            ),
        )
        print(f"[{i + 1}/{args.count}] {status} {json.dumps(body)}")
        if status not in (200, 202):
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
