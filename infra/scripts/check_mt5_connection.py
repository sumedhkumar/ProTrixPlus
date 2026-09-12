"""Read-only Windows MT5 connectivity check.

Credentials are read from environment variables (or the ignored
``infra/.env`` file) and are never printed. This script never calls
``order_send``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _load_local_env() -> None:
    env_file = Path(__file__).resolve().parents[1] / ".env"
    if not env_file.is_file():
        return
    for raw_line in env_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def main() -> int:
    _load_local_env()
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
