# TradingView -> MT5 demo execution

The application does not read a TradingView chart or strategy directly. A
TradingView strategy must fire an alert, and TradingView sends that alert to
the application's webhook. The native Windows worker then submits eligible
BUY/SELL entries to Alice's MetaQuotes-Demo MT5 account.

## Local prerequisites

1. Keep MetaTrader 5 logged into the configured demo account with Algo Trading
   enabled.
2. Keep the Docker PostgreSQL, Redis, API, and web services running. The Docker
   worker must remain stopped; the native worker owns MT5 execution.
3. Run the native worker:

   ```powershell
   .\run-local.ps1 mt5-worker
   ```

4. Expose the narrow local gateway through a public HTTPS tunnel. TradingView
   cannot deliver webhooks to `localhost`.

   ```powershell
   .\run-local.ps1 tradingview-gateway
   ```

   The gateway listens privately on `127.0.0.1:9000` and forwards only the
   authenticated TradingView webhook path to the API on `:8000`.

## TradingView alert URL

Use this URL pattern, replacing the host with the HTTPS tunnel hostname and
using the value of `PROTRIX_TRADINGVIEW_WEBHOOK_SECRET` from the local
`infra/.env`:

```text
https://PUBLIC_HOST/webhook/tradingview/SECRET_PATH_VALUE
```

The path secret is used because TradingView alert configuration sends the
alert message in the POST body and does not provide the app's custom
`X-Webhook-Token` header.

## Entry alert message

For a strategy order-fill alert, use a valid JSON message like this. The
TradingView strategy order action placeholder is normalized from lowercase to
uppercase by the direct TradingView route.

```json
{
  "schema_version": "1.0",
  "strategy_key": "trend-rider",
  "strategy_version": "2025.09",
  "signal_id": "{{strategy.order.id}}-{{timenow}}",
  "event_time_utc": "{{timenow}}",
  "action": "{{strategy.order.action}}",
  "symbol": "XAUUSD",
  "timeframe": "{{interval}}"
}
```

The backend's stored strategy assignment remains authoritative for lot sizing;
values such as `master_lot_info` from the alert are informational only.

## Important limitation before enabling exits

The current MT5 adapter accepts BUY/SELL entries only. It does not infer
whether a TradingView SELL is a new short or an exit from a long position, and
it rejects management commands until a stable `position_ref` mapping is
provided. Do not use a generic order-fill message for exits. Confirm the
strategy's exit format and position mapping before enabling automated closes.

Never include MT5 credentials in the TradingView alert body.
