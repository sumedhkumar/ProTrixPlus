"""_normalize_tradingview_payload's order_id -> signal_id synthesis.

TradingView's alert editor sometimes mis-lints a Message value with two
{{...}} placeholders concatenated in one string (e.g.
"{{strategy.order.id}}-{{timenow}}"), so the recommended alert template
(marketplace.alert_config_for_strategy) sends order_id and event_time_utc
as separate single-placeholder fields instead of a pre-combined signal_id.
This is pure normalization logic - no DB, no auth - so it's tested directly
against the function rather than through the HTTP endpoint."""

from __future__ import annotations

from app.routers.webhook import _normalize_tradingview_payload


def test_order_id_and_event_time_combine_into_signal_id() -> None:
    payload = {
        "schema_version": "1.0",
        "strategy_key": "saiyan-occ-r541",
        "strategy_version": "5.41",
        "order_id": "Long",
        "event_time_utc": "2026-09-25T10:15:00Z",
        "action": "buy",
        "symbol": "XAUUSD",
        "timeframe": "1",
    }
    normalized = _normalize_tradingview_payload(payload)
    assert normalized["signal_id"] == "Long-2026-09-25T10:15:00Z"
    assert "order_id" not in normalized  # frozen envelope has additionalProperties: false


def test_order_id_is_dropped_even_without_event_time_utc() -> None:
    normalized = _normalize_tradingview_payload({"order_id": "Long", "action": "buy"})
    assert "order_id" not in normalized
    assert normalized["signal_id"] == "Long-"


def test_explicit_signal_id_wins_over_order_id() -> None:
    normalized = _normalize_tradingview_payload(
        {"order_id": "Long", "signal_id": "explicit-id", "event_time_utc": "2026-09-25T10:15:00Z"}
    )
    assert normalized["signal_id"] == "explicit-id"
    assert "order_id" not in normalized


def test_no_order_id_is_a_no_op_for_signal_id() -> None:
    normalized = _normalize_tradingview_payload({"signal_id": "already-set", "action": "buy"})
    assert normalized["signal_id"] == "already-set"


def test_action_and_timeframe_normalization_still_applies() -> None:
    normalized = _normalize_tradingview_payload(
        {"order_id": "Long", "event_time_utc": "t", "action": "sell", "timeframe": "15"}
    )
    assert normalized["action"] == "SELL"
    assert normalized["timeframe"] == "15m"
