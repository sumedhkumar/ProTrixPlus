"""Read-only Windows MT5 connectivity check.

Credentials are read from environment variables (or the ignored
``infra/.env`` file) and are never printed. This script never calls
``order_send``.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


_PROFILE_KEYS = frozenset(
    {
        "PROTRIX_MT5_USER_EMAIL",
        "PROTRIX_MT5_PATH",
        "PROTRIX_MT5_LOGIN",
        "PROTRIX_MT5_PASSWORD",
        "PROTRIX_MT5_SERVER",
        "PROTRIX_MT5_SYMBOL",
        "PROTRIX_MT5_TRADING_ENABLED",
        "PROTRIX_MT5_MAGIC",
        "PROTRIX_MT5_DEVIATION_POINTS",
        "PROTRIX_MT5_TIMEOUT_SECONDS",
        # Accepted so this read-only preflight can consume the exact same
        # per-account profile as ``run-local.ps1 mt5-worker``.
        "PROTRIX_WORKER_NAME",
        "PROTRIX_WORKER_HEALTH_PORT",
        "PROTRIX_SIGNAL_CONSUMER_GROUP",
        "PROTRIX_CATCH_UP_ON_START",
    }
)


def _load_env_file(env_file: Path, *, override: bool, allowed: frozenset[str] | None = None) -> None:
    if not env_file.is_file():
        return
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if allowed is not None and key not in allowed:
            raise ValueError(f"unsupported setting in MT5 profile: {key}")
        if override:
            os.environ[key] = value.strip().strip("'\"")
        else:
            os.environ.setdefault(key, value.strip().strip("'\""))


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only local MT5 readiness check")
    parser.add_argument(
        "--profile-file",
        type=Path,
        help="ignored account-specific local profile; overrides only MT5 settings",
    )
    args = parser.parse_args()

    _load_env_file(Path(__file__).resolve().parents[1] / ".env", override=False)
    if args.profile_file is not None:
        try:
            _load_env_file(args.profile_file, override=True, allowed=_PROFILE_KEYS)
        except ValueError as exc:
            print(f"ERROR: {exc}")
            return 1
    try:
        import MetaTrader5 as mt5
    except ImportError:
        print("ERROR: MetaTrader5 is not installed in this Python environment")
        return 1

    path = os.environ.get(
        "PROTRIX_MT5_PATH", r"C:\Program Files\MetaTrader 5\terminal64.exe"
    )
    login_text = os.environ.get("PROTRIX_MT5_LOGIN", "")
    password = os.environ.get("PROTRIX_MT5_PASSWORD", "")
    server = os.environ.get("PROTRIX_MT5_SERVER", "")
    symbol = os.environ.get("PROTRIX_MT5_SYMBOL", "XAUUSD")
    if not login_text or not password or not server:
        print(
            "ERROR: set PROTRIX_MT5_LOGIN, PROTRIX_MT5_PASSWORD, and PROTRIX_MT5_SERVER"
        )
        return 1
    try:
        login = int(login_text)
    except ValueError:
        print("ERROR: PROTRIX_MT5_LOGIN must be numeric")
        return 1

    if not Path(path).is_file():
        print(f"ERROR: MT5 terminal not found: {path}")
        return 1

    try:
        if not mt5.initialize(path=path, login=login, password=password, server=server):
            error = mt5.last_error()
            if error[0] == -6:
                print(
                    "ERROR: MT5 authorization failed. Verify the exact account "
                    "login, master password, and broker server in infra/.env. "
                    f"MT5 detail: {error[1]}"
                )
            else:
                print(f"ERROR: MT5 initialize/login failed (code={error[0]!r})")
            return 1

        terminal = mt5.terminal_info()
        account = mt5.account_info()
        info = mt5.symbol_info(symbol)
        tick = mt5.symbol_info_tick(symbol) if info is not None else None
        if terminal is None or account is None:
            error = mt5.last_error()
            print(f"ERROR: MT5 status read failed (code={error[0]!r})")
            return 1

        terminal_trade_allowed = bool(getattr(terminal, "trade_allowed", False))
        account_trade_allowed = bool(getattr(account, "trade_allowed", False))
        symbol_found = info is not None
        live_tick = tick is not None
        print("MT5 connection: OK")
        print(f"terminal_version: {mt5.version()}")
        print(f"terminal_trade_allowed: {terminal_trade_allowed}")
        print(f"account_trade_allowed: {account_trade_allowed}")
        print(f"symbol: {symbol}")
        print(f"symbol_found: {symbol_found}")
        print(f"live_tick: {live_tick}")
        ready = (
            terminal_trade_allowed
            and account_trade_allowed
            and symbol_found
            and live_tick
        )
        if not terminal_trade_allowed:
            print(
                "BLOCKED: enable MT5 Algo Trading and uncheck "
                "'Disable automated trading via external Python API'."
            )
        if not symbol_found or not live_tick:
            print(
                f"BLOCKED: {symbol} is not receiving a live quote; show the exact "
                "broker symbol in Market Watch and verify the market is open."
            )
        print("MT5 readiness: " + ("READY" if ready else "BLOCKED"))
        return 0 if ready else 1
    finally:
        mt5.shutdown()


if __name__ == "__main__":
    sys.exit(main())
