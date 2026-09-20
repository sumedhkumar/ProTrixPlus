"""MetaApi.cloud execution adapter (ADR-001).

Unlike the native ``mt5`` adapter, this needs no local Windows terminal -
MetaApi already has a cloud-hosted connection to each client's MT5 account,
reached over plain HTTPS. This is the adapter that actually runs in the
Docker worker.

``account_ref`` encodes both values MetaApi's regional REST API needs -
``"<region>:<metaapi_account_id>"`` (see ``execution.py``'s account
resolution, which builds this from a client's ``Mt5Connection`` row). The
``ExecutionAdapter`` Protocol only carries a single ``account_ref`` string,
shared with ``mock``/``mt5``, so this adapter parses it out itself rather
than widening a Protocol only one adapter needs.

Starts in a read-only guard mode unless ``PROTRIX_METAAPI_TRADING_ENABLED=true``
is explicitly set - same safety pattern as the native adapter. Entry orders
(BUY/SELL) only for now; management actions are rejected until their
position_ref -> MetaApi positionId mapping is implemented (also matches the
native adapter, and the TradingView ingestion decision to treat every alert
as a fresh entry for now).
"""

from __future__ import annotations

import hashlib
import logging
import string
from decimal import Decimal
from typing import Any

import httpx
from protrix_contracts.db.models import Execution, OrderIntent
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from app.adapters.base import BrokerPosition, ExecutionTimeout, OrderIntentDTO, PlaceResult, Side
from app.config import WorkerConfig

log = logging.getLogger("worker.adapter.metaapi")

_ACCEPTED_RETCODES = {
    "TRADE_RETCODE_DONE",
    "TRADE_RETCODE_DONE_PARTIAL",
    "TRADE_RETCODE_PLACED",
}
_ACTION_TYPE = {"BUY": "ORDER_TYPE_BUY", "SELL": "ORDER_TYPE_SELL"}


def _position_side(metaapi_type: str) -> Side:
    return "SELL" if metaapi_type == "POSITION_TYPE_SELL" else "BUY"


_BASE62 = string.ascii_letters + string.digits


def _client_id(symbol: str, client_order_id: str) -> str:
    """MetaApi's clientId has a real, undocumented validation pattern beyond
    "alphanumeric, ~30 chars" - confirmed live twice: both our raw UUID
    order id (36 chars, hyphenated) and a 24-char lowercase-hex digest were
    rejected ("Invalid value. Value must match required pattern."). MetaApi's
    own docs give two real accepted examples - "RF_EURUSD_GjCy5lk" and
    "TE_GBPUSD_7hyINWqAl" - both `<2-letter prefix>_<SYMBOL>_<mixed-case
    alnum suffix>`. This mirrors that exact shape. Deterministic (from
    client_order_id) so ``sync_positions`` can reverse-look-up the real id
    the same way the native ``mt5`` adapter's own ``_comment()`` helper does.
    """
    digest = hashlib.sha256(client_order_id.encode("utf-8")).digest()
    suffix = "".join(_BASE62[b % len(_BASE62)] for b in digest[:10])
    return f"PX_{symbol}_{suffix}"


class MetaApiAccountRefError(ValueError):
    """account_ref wasn't the "<region>:<account_id>" shape this adapter needs."""


def _parse_account_ref(account_ref: str) -> tuple[str, str]:
    region, sep, account_id = account_ref.partition(":")
    if not sep or not region or not account_id:
        raise MetaApiAccountRefError(
            f"expected '<region>:<metaapi_account_id>', got {account_ref!r}"
        )
    return region, account_id


class MetaApiExecutionAdapter:
    name = "metaapi"

    def __init__(self, session_factory: sessionmaker[Session], config: WorkerConfig) -> None:
        if not config.metaapi_token:
            raise RuntimeError("the metaapi adapter requires PROTRIX_METAAPI_TOKEN")
        self._sf = session_factory
        self._cfg = config
        self._client = httpx.Client(
            headers={"auth-token": config.metaapi_token, "Accept": "application/json"},
            timeout=httpx.Timeout(
                connect=10.0,
                read=config.metaapi_timeout_seconds,
                write=10.0,
                pool=10.0,
            ),
        )

    def close(self) -> None:
        self._client.close()

    @staticmethod
    def _host(region: str) -> str:
        return f"https://mt-client-api-v1.{region}.agiliumtrade.ai"

    def _rejected(self, reason: str, order: OrderIntentDTO) -> PlaceResult:
        return PlaceResult(ticket_id="", deal_id="", status="REJECTED", raw={"reason": reason})

    def place(self, order: OrderIntentDTO) -> PlaceResult:
        if not self._cfg.metaapi_trading_enabled:
            return self._rejected("trading_disabled", order)
        if order.command_target != "ENTRY" or order.action.upper() not in _ACTION_TYPE:
            return self._rejected("management_action_not_yet_supported", order)

        try:
            region, account_id = _parse_account_ref(order.account_ref)
        except MetaApiAccountRefError as exc:
            log.error("place %s: %s", order.client_order_id, exc)
            return self._rejected("no_metaapi_account_configured", order)

        body: dict[str, Any] = {
            "actionType": _ACTION_TYPE[order.side],
            "symbol": order.symbol,
            "volume": float(order.volume),
            "clientId": _client_id(order.symbol, order.client_order_id),
            "magic": self._cfg.metaapi_magic,
        }
        if order.stop_loss is not None:
            body["stopLoss"] = float(order.stop_loss)
        if order.take_profit is not None:
            body["takeProfit"] = float(order.take_profit)

        url = f"{self._host(region)}/users/current/accounts/{account_id}/trade"
        try:
            response = self._client.post(url, json=body)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise ExecutionTimeout(
                f"MetaApi trade request for {order.client_order_id} did not complete"
            ) from exc

        if response.status_code >= 500:
            # MetaApi's own gateway/broker-side error with no clear answer -
            # never assume rejected, let reconciliation find out what really
            # happened.
            raise ExecutionTimeout(
                f"MetaApi returned {response.status_code} for {order.client_order_id}"
            )

        try:
            payload = response.json()
        except ValueError:
            payload = {"raw": response.text}

        if response.status_code >= 400:
            # A definitive synchronous error from MetaApi (bad params, unknown
            # account, etc.) - this is a real answer, not a lost response.
            return PlaceResult(
                ticket_id="",
                deal_id="",
                status="REJECTED",
                raw={"http_status": str(response.status_code), **_stringify(payload)},
            )

        string_code = str(payload.get("stringCode", ""))
        raw = {"stringCode": string_code, **_stringify(payload)}
        if string_code not in _ACCEPTED_RETCODES:
            return PlaceResult(ticket_id="", deal_id="", status="REJECTED", raw=raw)

        order_id = str(payload.get("orderId") or "")
        position_id = str(payload.get("positionId") or "")
        return PlaceResult(
            ticket_id=order_id or position_id,
            deal_id=position_id or order_id,
            status="ACKNOWLEDGED",
            raw=raw,
        )

    def sync_positions(self, account_ref: str) -> list[BrokerPosition]:
        region, account_id = _parse_account_ref(account_ref)
        url = f"{self._host(region)}/users/current/accounts/{account_id}/positions"
        try:
            response = self._client.get(url)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise RuntimeError(f"MetaApi positions request failed for {account_ref}") from exc
        response.raise_for_status()

        with self._sf() as session:
            rows = session.execute(
                select(Execution.client_order_id, OrderIntent.symbol).join(
                    OrderIntent, Execution.order_intent_id == OrderIntent.id
                )
            ).all()
            known = {
                _client_id(symbol, client_order_id): client_order_id
                for client_order_id, symbol in rows
            }

        result: list[BrokerPosition] = []
        for position in response.json():
            hashed_client_id = position.get("clientId")
            if not hashed_client_id:
                continue
            client_order_id = known.get(str(hashed_client_id))
            if client_order_id is None:
                continue  # a position MetaApi has that we never placed via ProTrixPlus
            side = _position_side(str(position.get("type", "")))
            result.append(
                BrokerPosition(
                    client_order_id=client_order_id,
                    ticket_id=str(position.get("id", "")),
                    deal_id=str(position.get("id", "")),
                    symbol=str(position.get("symbol", "")),
                    volume=Decimal(str(position.get("volume", "0"))),
                    side=side,
                    status="OPEN",
                )
            )
        return result


def _stringify(payload: dict[str, Any]) -> dict[str, str]:
    return {k: str(v) for k, v in payload.items() if k not in {"stringCode"}}
