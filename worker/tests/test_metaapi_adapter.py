"""MetaApiExecutionAdapter: request shape, response mapping, and the safety
gates - all against a fake HTTP transport (httpx.MockTransport), never the
real MetaApi service."""

from __future__ import annotations

import json
import uuid
from decimal import Decimal

import httpx
import pytest
from protrix_contracts.db.models import Execution, OrderIntent, Signal
from sqlalchemy import select

from app.adapters.base import ExecutionTimeout, OrderIntentDTO
from app.adapters.metaapi import MetaApiExecutionAdapter, _client_id
from app.config import WorkerConfig
from tests.conftest import make_signal

pytestmark = pytest.mark.dbtest

ACCOUNT_REF = "london:b6b65caf-5b94-476e-8e7b-889b819f4f97"


def _config(*, trading_enabled: bool = True) -> WorkerConfig:
    return WorkerConfig(
        database_url="",
        redis_url="",
        signal_stream="",
        consumer_group="",
        consumer_name="",
        log_level="INFO",
        service_name="worker",
        health_port=8000,
        execution_adapter="metaapi",
        mt5_user_email="",
        mt5_path="",
        mt5_login=0,
        mt5_password="",
        mt5_server="",
        mt5_trading_enabled=False,
        mt5_magic=0,
        mt5_deviation_points=0,
        mt5_timeout_seconds=1.0,
        metaapi_token="test-token",
        metaapi_trading_enabled=trading_enabled,
        metaapi_magic=260910,
        metaapi_timeout_seconds=5.0,
        relay_poll_seconds=0.5,
        relay_batch=50,
        reclaim_idle_ms=30000,
        catch_up_on_start=False,
    )


def _order(**overrides: object) -> OrderIntentDTO:
    fields: dict[str, object] = {
        "client_order_id": "coid-1",
        "account_ref": ACCOUNT_REF,
        "symbol": "XAUUSD",
        "side": "BUY",
        "volume": Decimal("0.10"),
        "action": "BUY",
        "command_target": "ENTRY",
    }
    fields.update(overrides)
    return OrderIntentDTO(**fields)  # type: ignore[arg-type]


def _adapter_with_transport(
    sf, handler, *, trading_enabled: bool = True
) -> MetaApiExecutionAdapter:
    adapter = MetaApiExecutionAdapter(sf, _config(trading_enabled=trading_enabled))
    adapter._client = httpx.Client(  # noqa: SLF001 - test-only transport swap
        headers=adapter._client.headers,  # noqa: SLF001
        transport=httpx.MockTransport(handler),
    )
    return adapter


@pytest.fixture
def ids(sf, seeded):
    make_signal(sf)
    return seeded


def test_trading_disabled_rejects_without_any_http_call(sf, ids) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not call MetaApi while trading is disabled")

    adapter = _adapter_with_transport(sf, handler, trading_enabled=False)
    result = adapter.place(_order())
    assert result.status == "REJECTED"
    assert result.raw["reason"] == "trading_disabled"


def test_management_action_rejects_without_any_http_call(sf, ids) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not call MetaApi for an unsupported management action")

    adapter = _adapter_with_transport(sf, handler)
    result = adapter.place(_order(command_target="CLOSE", action="CLOSE"))
    assert result.status == "REJECTED"
    assert result.raw["reason"] == "management_action_not_yet_supported"


def test_missing_account_ref_rejects_without_any_http_call(sf, ids) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not call MetaApi with an unroutable account_ref")

    adapter = _adapter_with_transport(sf, handler)
    result = adapter.place(_order(account_ref="not-a-real-account-ref"))
    assert result.status == "REJECTED"
    assert result.raw["reason"] == "no_metaapi_account_configured"


def test_client_id_matches_metaapis_real_accepted_shape() -> None:
    """The exact bug caught live, twice: MetaApi's clientId field rejects
    both our raw UUID order ids (36 chars, hyphenated) and a plain 24-char
    lowercase-hex digest ("Invalid value. Value must match required
    pattern."). Must match the shape of MetaApi's own confirmed-real
    examples: '<2-letter prefix>_<SYMBOL>_<mixed-case alnum suffix>'."""
    raw = str(uuid.uuid4())
    client_id = _client_id("XAUUSD", raw)
    assert client_id != raw
    assert client_id.startswith("PX_XAUUSD_")
    suffix = client_id.removeprefix("PX_XAUUSD_")
    assert suffix.isalnum()
    assert len(client_id) <= 30
    # deterministic - sync_positions's reverse lookup depends on this
    assert _client_id("XAUUSD", raw) == client_id


def test_successful_buy_sends_the_correct_request_and_maps_the_response(sf, ids) -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["url"] = str(request.url)
        seen["auth_token"] = request.headers.get("auth-token")
        seen["json"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "numericCode": 10009,
                "stringCode": "TRADE_RETCODE_DONE",
                "message": "OK",
                "orderId": "555",
                "positionId": "777",
            },
        )

    adapter = _adapter_with_transport(sf, handler)
    result = adapter.place(_order(stop_loss=Decimal("2600.00"), take_profit=Decimal("2700.00")))

    assert seen["method"] == "POST"
    assert (
        seen["url"] == "https://mt-client-api-v1.london.agiliumtrade.ai/users/current/accounts/"
        "b6b65caf-5b94-476e-8e7b-889b819f4f97/trade"
    )
    assert seen["auth_token"] == "test-token"
    body = seen["json"]
    assert body["actionType"] == "ORDER_TYPE_BUY"
    assert body["symbol"] == "XAUUSD"
    assert body["volume"] == 0.10
    assert body["clientId"] == _client_id("XAUUSD", "coid-1")
    assert body["clientId"] != "coid-1"  # never the raw id - see test above
    assert "comment" not in body  # every byte matters against the 30-char cap
    assert body["stopLoss"] == 2600.00
    assert body["takeProfit"] == 2700.00
    assert body["magic"] == 260910

    assert result.status == "ACKNOWLEDGED"
    assert result.ticket_id == "555"
    assert result.deal_id == "777"


def test_sell_maps_to_order_type_sell(sf, ids) -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["json"] = json.loads(request.content)
        return httpx.Response(
            200, json={"stringCode": "TRADE_RETCODE_DONE", "orderId": "1", "positionId": "2"}
        )

    adapter = _adapter_with_transport(sf, handler)
    adapter.place(_order(side="SELL", action="SELL"))
    assert seen["json"]["actionType"] == "ORDER_TYPE_SELL"


def test_broker_rejection_is_a_clean_rejected_not_a_timeout(sf, ids) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "numericCode": 10004,
                "stringCode": "TRADE_RETCODE_REJECT",
                "message": "not enough margin",
            },
        )

    adapter = _adapter_with_transport(sf, handler)
    result = adapter.place(_order())
    assert result.status == "REJECTED"
    assert result.raw["stringCode"] == "TRADE_RETCODE_REJECT"


def test_client_error_response_is_rejected_not_a_timeout(sf, ids) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"message": "unknown symbol"})

    adapter = _adapter_with_transport(sf, handler)
    result = adapter.place(_order())
    assert result.status == "REJECTED"
    assert result.raw["http_status"] == "400"


def test_server_error_raises_execution_timeout_not_rejected(sf, ids) -> None:
    """A 5xx from MetaApi's own gateway is not a broker answer - must trigger
    reconciliation, never be silently treated as a clean rejection."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="bad gateway")

    adapter = _adapter_with_transport(sf, handler)
    with pytest.raises(ExecutionTimeout):
        adapter.place(_order())


def test_network_timeout_raises_execution_timeout(sf, ids) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("simulated", request=request)

    adapter = _adapter_with_transport(sf, handler)
    with pytest.raises(ExecutionTimeout):
        adapter.place(_order())


def _insert_execution(sf, ids, *, client_order_id: str) -> None:
    with sf() as session:
        sig = session.scalar(select(Signal))
        intent = OrderIntent(
            user_id=ids["alice"],
            strategy_id=ids["strategy"],
            signal_id=sig.id,
            command_target="ENTRY",
            action="BUY",
            symbol="XAUUSD",
            computed_lot=Decimal("0.10"),
            master_lot=Decimal("1.00"),
            multiplier=Decimal("1.0000"),
            eligibility_status="ACTIVE",
            status="CREATED",
        )
        session.add(intent)
        session.flush()
        session.add(
            Execution(
                order_intent_id=intent.id,
                client_order_id=client_order_id,
                adapter="metaapi",
                state="FILLED",
            )
        )
        session.commit()


def test_sync_positions_reverse_maps_the_hashed_client_id_back_to_the_real_one(sf, ids) -> None:
    _insert_execution(sf, ids, client_order_id="coid-1")
    hashed = _client_id("XAUUSD", "coid-1")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert str(request.url).endswith(
            "/users/current/accounts/b6b65caf-5b94-476e-8e7b-889b819f4f97/positions"
        )
        return httpx.Response(
            200,
            json=[
                {
                    "id": "999",
                    "symbol": "XAUUSD",
                    "type": "POSITION_TYPE_BUY",
                    "volume": 0.1,
                    "clientId": hashed,
                },
                {
                    "id": "1000",
                    "symbol": "EURUSD",
                    "type": "POSITION_TYPE_SELL",
                    "volume": 0.2,
                    "clientId": "some-other-apps-position-not-ours",
                },
            ],
        )

    adapter = _adapter_with_transport(sf, handler)
    positions = adapter.sync_positions(ACCOUNT_REF)
    assert len(positions) == 1
    assert positions[0].client_order_id == "coid-1"  # the real id, not the hash
    assert positions[0].ticket_id == "999"
    assert positions[0].side == "BUY"
    assert positions[0].volume == Decimal("0.1")
