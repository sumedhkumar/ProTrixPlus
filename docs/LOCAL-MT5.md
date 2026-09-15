# Local MT5 demo routes

Each native worker owns one explicitly selected Protrixplus user and one demo
account. Workers use distinct Redis consumer groups, so every account receives
each accepted signal, while the worker's user route prevents one account from
placing another user's order. This native route is for local demo validation;
MetaApi remains the later production transport.

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

Run the read-only check for the primary local profile from the repository root:

```powershell
.\.venv\Scripts\python.exe infra\scripts\check_mt5_connection.py
```

For a second account, keep an ignored profile such as
`infra/.env.mt5-account2.local`. It can contain only the MT5 and worker-routing
keys accepted by `run-local.ps1`; never commit it. Check it without printing
credentials:

```powershell
.\.venv\Scripts\python.exe infra\scripts\check_mt5_connection.py `
  --profile-file infra\.env.mt5-account2.local
```

Start a ready demo route only after its read-only check reports terminal
permission, account permission, a configured symbol, and a live tick:

```powershell
.\run-local.ps1 mt5-worker -HealthPort 8102
.\run-local.ps1 mt5-worker -ProfileFile infra\.env.mt5-account2.local
```

The Docker mock worker occupies host port `8100`. Each native account must use
its own health port; the primary profile uses `8102` above and account 2 uses
its local profile's `8101`. The launcher keeps every started native profile in
its local process state, so `down` stops all of them together.

The adapter supports BUY/SELL entries plus mapped close, partial-close, SL/TP,
and emergency management. Direction-only alerts also reverse safely: an
opposite BUY/SELL signal closes the app-tracked opposite position before opening
the new direction. Repeated same-direction signals do not pyramid by default.
