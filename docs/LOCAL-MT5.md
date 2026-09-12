# Local MT5 route

The first local route uses one explicitly selected user, `alice@example.test`,
and one MT5 account. Bob and Carol are not routed while this setting is active;
future accounts can be mapped independently.

The official `MetaTrader5` Python package communicates with a Windows terminal,
so the live worker must run natively on Windows. The Docker worker remains the
safe mock path.

## Configure locally

Edit the ignored `infra/.env` file. Do not commit or paste these values:

```text
PROTRIX_EXECUTION_ADAPTER=mt5
PROTRIX_MT5_USER_EMAIL=alice@example.test
PROTRIX_MT5_PATH=C:\Program Files\MetaTrader 5\terminal64.exe
PROTRIX_MT5_LOGIN=<demo-login>
PROTRIX_MT5_PASSWORD=<demo-password>
PROTRIX_MT5_SERVER=<exact-broker-server>
PROTRIX_MT5_SYMBOL=XAUUSD
PROTRIX_MT5_TRADING_ENABLED=false
```

Run the read-only check from the repository root:

```powershell
.\.venv\Scripts\python.exe infra\scripts\check_mt5_connection.py
```

Only after the read-only check reports the expected account, server, symbol,
and live tick should `PROTRIX_MT5_TRADING_ENABLED` be changed to `true` for a
demo-only test. The adapter currently supports BUY/SELL entries; management
actions are deliberately rejected until per-user position mapping is complete.
