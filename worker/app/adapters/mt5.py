"""Native Windows MetaTrader 5 execution adapter.

This module is imported only when ``PROTRIX_EXECUTION_ADAPTER=mt5``. The
official ``MetaTrader5`` package communicates with a Windows terminal through
local IPC, so the worker using this adapter must run natively on Windows.

The adapter starts in read-only guard mode unless
``PROTRIX_MT5_TRADING_ENABLED=true`` is explicitly set. Entry orders are
supported first; management actions remain rejected until their per-user
position mapping is implemented.
"""

from __future__ import annotations

import hashlib
import importlib
import logging
from decimal import ROUND_DOWN, Decimal
from pathlib import Path
from typing import Any

from protrix_contracts.db.models import Execution
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.base import BrokerPosition, ExecutionTimeout, OrderIntentDTO, PlaceResult
from app.config import WorkerConfig

log = logging.getLogger("worker.adapter.mt5")


def _comment(client_order_id: str) -> str:
    """Return a broker-safe deterministic token for the stable order id."""
    return "px-" + hashlib.sha256(client_order_id.encode("utf-8")).hexdigest()[:24]


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value))


class MetaTrader5ExecutionAdapter:
    name = "mt5"

    def __init__(self, session_factory: sessionmaker[Session], config: WorkerConfig) -> None:
        self._sf = session_factory
        self._cfg = config
        self._mt5 = self._load_module()

        if not Path(config.mt5_path).is_file():
            raise RuntimeError(f"MT5 terminal not found at {config.mt5_path!r}")
        if config.mt5_login <= 0 or not config.mt5_password or not config.mt5_server:
            raise RuntimeError(
                "mt5 adapter requires explicit PROTRIX_MT5_LOGIN, "
                "PROTRIX_MT5_PASSWORD, and PROTRIX_MT5_SERVER"
            )

        connected = self._mt5.initialize(
            path=config.mt5_path,
            login=config.mt5_login,
            password=config.mt5_password,
            server=config.mt5_server,
            timeout=max(1000, int(config.mt5_timeout_seconds * 1000)),
        )
        if not connected:
            error = self._mt5.last_error()
            self._mt5.shutdown()
            raise RuntimeError(f"MT5 initialize/login failed (code={error[0]!r})")

        account = self._mt5.account_info()
        if account is None:
            error = self._mt5.last_error()
            self._mt5.shutdown()
            raise RuntimeError(f"MT5 account_info failed (code={error[0]!r})")

        terminal = self._mt5.terminal_info()
        if terminal is None:
            error = self._mt5.last_error()
            self._mt5.shutdown()
            raise RuntimeError(f"MT5 terminal_info failed (code={error[0]!r})")
        if config.mt5_trading_enabled and (
            not bool(getattr(terminal, "trade_allowed", False))
            or not bool(getattr(account, "trade_allowed", False))
        ):
            self._mt5.shutdown()
            raise RuntimeError(
                "MT5 trading is not allowed by both the terminal and account; "
                "keep PROTRIX_MT5_TRADING_ENABLED=false until enabled"
            )

        log.warning(
            "MT5 connected server=%s trading_enabled=%s user_scope=%s",
            config.mt5_server,
            config.mt5_trading_enabled,
            config.mt5_user_email,
        )

    @staticmethod
    def _load_module() -> Any:
        try:
            return importlib.import_module("MetaTrader5")
        except ImportError as exc:
            raise RuntimeError(
                "MetaTrader5 is not installed in the native Windows worker environment"
            ) from exc

    def _rejected(self, reason: str, order: OrderIntentDTO) -> PlaceResult:
        return PlaceResult(
            ticket_id="",
            deal_id="",
            status="REJECTED",
            raw={"reason": reason, "account_ref": order.account_ref},
        )

    def _volume(self, symbol_info: Any, requested: Decimal) -> Decimal:
        minimum = _decimal(symbol_info.volume_min)
        maximum = _decimal(symbol_info.volume_max)
        step = _decimal(symbol_info.volume_step)
        if requested < minimum or requested > maximum:
            raise ValueError(f"volume outside broker bounds for {symbol_info.name}")
        units = (requested / step).to_integral_value(rounding=ROUND_DOWN)
        normalized = units * step
        if normalized < minimum or normalized > maximum:
            raise ValueError(f"volume does not fit broker step for {symbol_info.name}")
        return normalized

    def place(self, order: OrderIntentDTO) -> PlaceResult:
        if not self._cfg.mt5_trading_enabled:
            return self._rejected("trading_disabled", order)
        if order.command_target != "ENTRY" or order.action.upper() not in {"BUY", "SELL"}:
            return self._rejected("management_action_not_yet_supported", order)

        symbol_info = self._mt5.symbol_info(order.symbol)
        if symbol_info is None:
            return self._rejected("symbol_not_found", order)
        if not symbol_info.visible and not self._mt5.symbol_select(order.symbol, True):
            return self._rejected("symbol_not_visible", order)

        tick = self._mt5.symbol_info_tick(order.symbol)
        if tick is None:
            return self._rejected("no_live_tick", order)

        try:
            volume = self._volume(symbol_info, order.volume)
        except ValueError as exc:
            return self._rejected(str(exc), order)

        side = order.action.upper()
        order_type = self._mt5.ORDER_TYPE_BUY if side == "BUY" else self._mt5.ORDER_TYPE_SELL
        price = _decimal(tick.ask if side == "BUY" else tick.bid)
        request: dict[str, Any] = {
            "action": self._mt5.TRADE_ACTION_DEAL,
            "symbol": order.symbol,
            "volume": float(volume),
            "type": order_type,
            "price": float(price),
            "deviation": self._cfg.mt5_deviation_points,
            "magic": self._cfg.mt5_magic,
            "comment": _comment(order.client_order_id),
            "type_time": self._mt5.ORDER_TIME_GTC,
            "type_filling": self._mt5.ORDER_FILLING_IOC,
        }
        if order.stop_loss is not None:
            request["sl"] = float(order.stop_loss)
        if order.take_profit is not None:
            request["tp"] = float(order.take_profit)

        try:
            result = self._mt5.order_send(request)
        except Exception as exc:  # noqa: BLE001
            raise ExecutionTimeout("MT5 order response was unavailable") from exc
        if result is None:
            raise ExecutionTimeout("MT5 order response was unavailable")

        retcode = int(getattr(result, "retcode", 0))
        raw = {
            "retcode": str(retcode),
            "comment": str(getattr(result, "comment", "")),
            "request_id": str(getattr(result, "request_id", "")),
            "account_ref": order.account_ref,
        }
        accepted_codes = {
            int(getattr(self._mt5, "TRADE_RETCODE_DONE", 10009)),
            int(getattr(self._mt5, "TRADE_RETCODE_DONE_PARTIAL", 10010)),
            int(getattr(self._mt5, "TRADE_RETCODE_PLACED", 10008)),
        }
        if retcode not in accepted_codes:
            return PlaceResult(ticket_id="", deal_id="", status="REJECTED", raw=raw)

        return PlaceResult(
            ticket_id=str(getattr(result, "order", 0) or ""),
            deal_id=str(getattr(result, "deal", 0) or ""),
            status="ACKNOWLEDGED",
            raw=raw,
        )

    def sync_positions(self, account_ref: str) -> list[BrokerPosition]:  # noqa: ARG002
        positions = self._mt5.positions_get()
        if positions is None:
            error = self._mt5.last_error()
            raise RuntimeError(f"MT5 positions_get failed (code={error[0]!r})")

        with self._sf() as session:
            known = {
                _comment(row.client_order_id): row.client_order_id
                for row in session.scalars(select(Execution)).all()
            }

        buy_type = int(getattr(self._mt5, "POSITION_TYPE_BUY", 0))
        result: list[BrokerPosition] = []
        for position in positions:
            token = str(getattr(position, "comment", ""))
            client_order_id = known.get(token)
            if client_order_id is None:
                continue
            result.append(
                BrokerPosition(
                    client_order_id=client_order_id,
                    ticket_id=str(getattr(position, "ticket", "")),
                    deal_id=str(getattr(position, "identifier", "")),
                    symbol=str(getattr(position, "symbol", "")),
                    volume=_decimal(getattr(position, "volume", "0")),
                    side="BUY" if int(getattr(position, "type", buy_type)) == buy_type else "SELL",
                    status="OPEN",
                )
            )
        return result

    def close(self) -> None:
        self._mt5.shutdown()
