"""Native Windows MetaTrader 5 execution adapter.

This module is imported only when ``PROTRIX_EXECUTION_ADAPTER=mt5``. The
official ``MetaTrader5`` package communicates with a Windows terminal through
local IPC, so the worker using this adapter must run natively on Windows.

The adapter starts in read-only guard mode unless
``PROTRIX_MT5_TRADING_ENABLED=true`` is explicitly set. Management commands
are accepted only for a server-recorded, user-scoped managed position; a ticket
from a webhook is never used directly.
"""

from __future__ import annotations

import hashlib
import importlib
import logging
from datetime import UTC, datetime
from decimal import ROUND_DOWN, Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

from protrix_contracts.db.models import (
    EnrollmentAccount,
    Execution,
    ManagedPosition,
    ManagedPositionStatus,
    OrderIntent,
    StrategyEnrollment,
    User,
)
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.base import (
    BrokerClosedDeal,
    BrokerPosition,
    ExecutionTimeout,
    OrderIntentDTO,
    PlaceResult,
)
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

        self._routed_enrollment_id: UUID | None = None
        self._expected_broker_login: str | None = None
        with self._sf() as session:
            if config.mt5_enrollment_id:
                try:
                    enrollment_id = UUID(config.mt5_enrollment_id)
                except ValueError as exc:
                    raise RuntimeError("PROTRIX_MT5_ENROLLMENT_ID must be a UUID") from exc
                route = session.execute(
                    select(EnrollmentAccount, StrategyEnrollment, User)
                    .join(
                        StrategyEnrollment, EnrollmentAccount.enrollment_id == StrategyEnrollment.id
                    )
                    .join(User, StrategyEnrollment.user_id == User.id)
                    .where(EnrollmentAccount.enrollment_id == enrollment_id)
                ).first()
                if route is None:
                    raise RuntimeError("no enrollment account exists for PROTRIX_MT5_ENROLLMENT_ID")
                enrollment_account, enrollment, routed_user = route
                if not routed_user.is_active or enrollment_account.status != "ACTIVE":
                    raise RuntimeError("configured enrollment account is inactive")
                if enrollment_account.transport != "NATIVE_MT5":
                    raise RuntimeError("configured enrollment account is not a native MT5 route")
                if not enrollment_account.broker_login:
                    raise RuntimeError(
                        "configured enrollment account is missing its broker login identity"
                    )
                if (
                    enrollment_account.server_identifier
                    and enrollment_account.server_identifier != config.mt5_server
                ):
                    raise RuntimeError(
                        "MT5 server does not match the configured enrollment account"
                    )
                self._routed_user_id = routed_user.id
                self._routed_enrollment_id = enrollment.id
                self._account_ref = (
                    enrollment_account.external_account_ref or f"enrollment-{enrollment.id}"
                )
                self._expected_broker_login = enrollment_account.broker_login
            else:
                routed_user = session.scalar(
                    select(User).where(User.email == config.mt5_user_email)
                )
                if routed_user is None:
                    raise RuntimeError(
                        f"no ProTrix user exists for MT5 route {config.mt5_user_email!r}"
                    )
                if not routed_user.is_active:
                    raise RuntimeError(
                        f"ProTrix user for MT5 route {config.mt5_user_email!r} is inactive"
                    )
                self._routed_user_id = routed_user.id
                self._account_ref = f"acct-{routed_user.id}"

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

        actual_login = getattr(account, "login", None)
        actual_server = str(getattr(account, "server", "") or "")
        if actual_login is not None and int(actual_login) != config.mt5_login:
            self._mt5.shutdown()
            raise RuntimeError(
                "MT5 login mismatch: terminal account does not match PROTRIX_MT5_LOGIN"
            )
        if (
            self._expected_broker_login is not None
            and str(actual_login) != self._expected_broker_login
        ):
            self._mt5.shutdown()
            raise RuntimeError(
                "MT5 login mismatch: terminal account does not match the enrollment account"
            )
        if actual_server and actual_server != config.mt5_server:
            self._mt5.shutdown()
            raise RuntimeError(
                "MT5 server mismatch: terminal account does not match PROTRIX_MT5_SERVER"
            )

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

    def _send(
        self, request: dict[str, Any], order: OrderIntentDTO, *, ticket_id: str = ""
    ) -> PlaceResult:
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
            ticket_id=ticket_id or str(getattr(result, "order", 0) or ""),
            deal_id=str(getattr(result, "deal", 0) or ""),
            status="ACKNOWLEDGED",
            raw=raw,
        )

    def _managed_live_position(self, order: OrderIntentDTO) -> tuple[Any, Execution] | None:
        """Resolve an open terminal position belonging to this worker route."""
        if not order.broker_position_ref:
            return None
        with self._sf() as session:
            row = session.execute(
                select(ManagedPosition, Execution)
                .join(Execution, ManagedPosition.entry_execution_id == Execution.id)
                .where(
                    ManagedPosition.user_id == self._routed_user_id,
                    ManagedPosition.broker_position_ref == order.broker_position_ref,
                    ManagedPosition.status == ManagedPositionStatus.OPEN.value,
                )
            ).first()
        if row is None:
            return None
        try:
            ticket = int(order.broker_position_ref)
        except ValueError:
            return None
        positions = self._mt5.positions_get(ticket=ticket)
        if not positions:
            return None
        position = positions[0]
        entry_execution = row[1]
        if str(getattr(position, "comment", "")) != _comment(entry_execution.client_order_id):
            log.error("MT5 position comment did not match managed entry ticket=%s", ticket)
            return None
        return position, entry_execution

    def place(self, order: OrderIntentDTO) -> PlaceResult:
        if order.account_ref != self._account_ref:
            return self._rejected("account_route_mismatch", order)
        if not self._cfg.mt5_trading_enabled:
            return self._rejected("trading_disabled", order)
        if order.command_target != "ENTRY":
            return self._place_management(order)
        if order.action.upper() not in {"BUY", "SELL"}:
            return self._rejected("unsupported_entry_action", order)

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

        placed = self._send(request, order)
        if placed.status != "ACKNOWLEDGED":
            return placed
        # For management we need the *position* ticket, which can differ from
        # the order/deal ticket returned by MT5 on netting accounts.
        positions = self._mt5.positions_get(symbol=order.symbol) or ()
        for position in positions:
            if str(getattr(position, "comment", "")) == _comment(order.client_order_id):
                return PlaceResult(
                    ticket_id=str(getattr(position, "ticket", "")) or placed.ticket_id,
                    deal_id=placed.deal_id,
                    status=placed.status,
                    raw=placed.raw,
                )
        return placed

    def _place_management(self, order: OrderIntentDTO) -> PlaceResult:
        action = order.action.upper()
        if action not in {"CLOSE", "PARTIAL_CLOSE", "MODIFY_SLTP", "EMERGENCY_CLOSE"}:
            return self._rejected("unsupported_management_action", order)
        resolved = self._managed_live_position(order)
        if resolved is None:
            return self._rejected("managed_position_not_open_or_not_owned", order)
        position, _entry_execution = resolved
        if str(getattr(position, "symbol", "")) != order.symbol:
            return self._rejected("managed_position_symbol_mismatch", order)
        symbol_info = self._mt5.symbol_info(order.symbol)
        tick = self._mt5.symbol_info_tick(order.symbol)
        if symbol_info is None or tick is None:
            return self._rejected("symbol_not_ready", order)
        ticket = str(getattr(position, "ticket", ""))

        if action == "MODIFY_SLTP":
            if order.stop_loss is None and order.take_profit is None:
                return self._rejected("modify_requires_stop_loss_or_take_profit", order)
            request: dict[str, Any] = {
                "action": self._mt5.TRADE_ACTION_SLTP,
                "position": int(ticket),
                "symbol": order.symbol,
                "sl": float(
                    order.stop_loss
                    if order.stop_loss is not None
                    else getattr(position, "sl", Decimal("0"))
                ),
                "tp": float(
                    order.take_profit
                    if order.take_profit is not None
                    else getattr(position, "tp", Decimal("0"))
                ),
            }
            return self._send(request, order, ticket_id=ticket)

        position_volume = _decimal(getattr(position, "volume", "0"))
        requested = position_volume
        if action == "PARTIAL_CLOSE":
            if order.close_fraction is None or not Decimal("0") < order.close_fraction < Decimal(
                "1"
            ):
                return self._rejected("partial_close_requires_fraction_between_zero_and_one", order)
            requested = position_volume * order.close_fraction
        try:
            volume = self._volume(symbol_info, requested)
        except ValueError as exc:
            return self._rejected(str(exc), order)
        buy_type = int(getattr(self._mt5, "POSITION_TYPE_BUY", 0))
        is_buy = int(getattr(position, "type", buy_type)) == buy_type
        request = {
            "action": self._mt5.TRADE_ACTION_DEAL,
            "position": int(ticket),
            "symbol": order.symbol,
            "volume": float(volume),
            "type": self._mt5.ORDER_TYPE_SELL if is_buy else self._mt5.ORDER_TYPE_BUY,
            "price": float(_decimal(tick.bid if is_buy else tick.ask)),
            "deviation": self._cfg.mt5_deviation_points,
            "magic": self._cfg.mt5_magic,
            "comment": _comment(order.client_order_id),
            "type_time": self._mt5.ORDER_TIME_GTC,
            "type_filling": self._mt5.ORDER_FILLING_IOC,
        }
        return self._send(request, order, ticket_id=ticket)

    def sync_positions(self, account_ref: str) -> list[BrokerPosition]:
        if account_ref != self._account_ref:
            log.warning(
                "ignoring reconciliation for account_ref=%s on route=%s",
                account_ref,
                self._account_ref,
            )
            return []

        positions = self._mt5.positions_get()
        if positions is None:
            error = self._mt5.last_error()
            raise RuntimeError(f"MT5 positions_get failed (code={error[0]!r})")

        with self._sf() as session:
            stmt = (
                select(Execution)
                .join(OrderIntent, Execution.order_intent_id == OrderIntent.id)
                .where(OrderIntent.user_id == self._routed_user_id)
            )
            if self._routed_enrollment_id is not None:
                stmt = stmt.where(OrderIntent.enrollment_id == self._routed_enrollment_id)
            known = {
                _comment(row.client_order_id): row.client_order_id
                for row in session.scalars(stmt).all()
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

    def sync_closed_deals(self, account_ref: str, since: datetime) -> list[BrokerClosedDeal]:
        if account_ref != self._account_ref:
            return []
        with self._sf() as session:
            stmt = select(ManagedPosition.broker_position_ref).where(
                ManagedPosition.user_id == self._routed_user_id
            )
            if self._routed_enrollment_id is not None:
                stmt = (
                    stmt.join(Execution, ManagedPosition.entry_execution_id == Execution.id)
                    .join(OrderIntent, Execution.order_intent_id == OrderIntent.id)
                    .where(OrderIntent.enrollment_id == self._routed_enrollment_id)
                )
            managed_position_refs = set(session.scalars(stmt))
        deals = self._mt5.history_deals_get(since.astimezone(UTC), datetime.now(UTC))
        if deals is None:
            error = self._mt5.last_error()
            raise RuntimeError(f"MT5 history_deals_get failed (code={error[0]!r})")
        exit_entries = {
            int(getattr(self._mt5, "DEAL_ENTRY_OUT", 1)),
            int(getattr(self._mt5, "DEAL_ENTRY_OUT_BY", 3)),
        }
        attributed: list[BrokerClosedDeal] = []
        for deal in deals:
            if int(getattr(deal, "entry", -1)) not in exit_entries:
                continue
            position_ref = str(getattr(deal, "position_id", "") or "")
            if not position_ref or position_ref not in managed_position_refs:
                continue
            deal_id = str(getattr(deal, "ticket", "") or "")
            if not deal_id:
                continue
            closed_at = datetime.fromtimestamp(int(getattr(deal, "time", 0)), UTC)
            net_pnl = sum(
                (
                    _decimal(getattr(deal, field, 0))
                    for field in ("profit", "commission", "swap", "fee")
                ),
                Decimal("0"),
            )
            attributed.append(
                BrokerClosedDeal(
                    deal_id=deal_id,
                    position_ref=position_ref,
                    closed_at=closed_at,
                    net_realized_pnl=net_pnl,
                )
            )
        return attributed

    def close(self) -> None:
        self._mt5.shutdown()
