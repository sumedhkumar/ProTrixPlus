# TradingView -> MT5 demo execution

The application does not read a TradingView chart or strategy directly. A
TradingView strategy must fire an alert, and TradingView sends that alert to
the application's webhook. Each healthy native Windows worker then submits
eligible orders only for its own configured MetaQuotes-Demo account.

## Local prerequisites

1. Keep MetaTrader 5 logged into every configured demo account with Algo
   Trading and external Python API trading enabled.
2. Keep the Docker PostgreSQL, Redis, API, worker, and web services running.
   The Docker worker is the safe mock route; native workers own their separate
   MT5 demo routes.
3. Run each native worker on its own health port:

   ```powershell
   .\run-local.ps1 mt5-worker -HealthPort 8102
   .\run-local.ps1 mt5-worker -ProfileFile infra\.env.mt5-account2.local
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

## Direction-only alerts and position safety

The normal BUY/SELL alert body is directional. If an app-tracked position is
open in the opposite direction for the same strategy and symbol, the worker
first closes that mapped position and opens the new direction only after the
close fills. Repeated same-direction alerts do not pyramid by default.

Explicit `CLOSE`, `PARTIAL_CLOSE`, `MODIFY_SLTP`, and `EMERGENCY_CLOSE` alerts
must supply the app's `position_ref`; the worker maps that reference to its own
user- and strategy-owned broker position. A webhook never supplies a broker
ticket directly.

Never include MT5 credentials in the TradingView alert body.
