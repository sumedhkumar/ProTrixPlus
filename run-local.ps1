<#
.SYNOPSIS
  Run the Protrixplus S0 skeleton WITHOUT Docker - and without touching anything
  already installed on this machine.

  `bootstrap` downloads a *portable* PostgreSQL 16 and Redis into
  `<repo>\.localstack\` (git-ignored), runs them on non-standard ports
  (PG 55432, Redis 6399) bound to 127.0.0.1, with no Windows service, no admin,
  no PATH / registry changes. `teardown` deletes that folder and it's gone.

  If you already have PostgreSQL on :5432 and a Redis on :6379, skip `bootstrap`
  and this script uses those instead.

.USAGE
  ./run-local.ps1 bootstrap   # one-time: download portable PG + Redis, init db cluster
  ./run-local.ps1 setup       # venv + python deps + npm ci + alembic upgrade + seed
  ./run-local.ps1 up          # start infra (if portable) + api + worker + web
  ./run-local.ps1 status      # ports + /health
  ./run-local.ps1 down        # stop app processes (+ portable infra); keeps data
  ./run-local.ps1 reset       # alembic downgrade base -> upgrade head -> re-seed
  ./run-local.ps1 teardown    # down + delete .localstack entirely
  ./run-local.ps1 help
#>

param(
  [Parameter(Position = 0)]
  [ValidateSet('bootstrap', 'setup', 'up', 'mt5-worker', 'tradingview-gateway', 'down', 'status', 'reset', 'teardown', 'help')]
  [string]$Command = 'help',
  [switch]$SkipInstall,
  [switch]$Windows          # `up`: launch each service in its own visible window instead of hidden+logfile
)

$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
$Venv = Join-Path $Root '.venv'
$VenvPy = Join-Path $Venv 'Scripts\python.exe'

$LocalStack = Join-Path $Root '.localstack'
$PgHome = Join-Path $LocalStack 'pg'
$PgData = Join-Path $LocalStack 'pgdata'
$RedisHome = Join-Path $LocalStack 'redis'
$Marker = Join-Path $LocalStack 'ready.json'
$RunDir = Join-Path $Root '.run-local'
$LogDir = Join-Path $RunDir 'logs'
$PidFile = Join-Path $RunDir 'processes.json'

$PG_PORT = 55432
$REDIS_PORT = 6399

$PG_URL = 'https://get.enterprisedb.com/postgresql/postgresql-16.6-1-windows-x64-binaries.zip'
$REDIS_URL = 'https://github.com/redis-windows/redis-windows/releases/download/8.10.1/Redis-8.10.1-Windows-x64-msys2.zip'

# ------------------------------------------------------------------ helpers --
function Info($m) { Write-Host "   $m" -ForegroundColor Gray }
function Step($m) { Write-Host "==> $m" -ForegroundColor Cyan }
function Ok($m) { Write-Host "OK  $m" -ForegroundColor Green }
function Warn($m) { Write-Host "!!  $m" -ForegroundColor Yellow }
function Die($m) { Write-Host "XX  $m" -ForegroundColor Red; exit 1 }

function Test-Port([int]$Port, [string]$RHost = '127.0.0.1', [int]$TimeoutMs = 800) {
  try {
    $c = New-Object System.Net.Sockets.TcpClient
    $iar = $c.BeginConnect($RHost, $Port, $null, $null)
    if ($iar.AsyncWaitHandle.WaitOne($TimeoutMs) -and $c.Connected) { $c.EndConnect($iar); $c.Close(); return $true }
    $c.Close(); return $false
  } catch { return $false }
}
function Wait-Port([int]$Port, [int]$Seconds = 40) {
  for ($i = 0; $i -lt $Seconds; $i++) { if (Test-Port $Port) { return $true }; Start-Sleep 1 }
  return $false
}
function Have-Cmd([string]$n) { return [bool](Get-Command $n -ErrorAction SilentlyContinue) }
function Kill-Tree([int]$ProcId) { try { & taskkill /PID $ProcId /T /F 2>$null | Out-Null } catch { } }
function Get-VenvPy { if (-not (Test-Path $VenvPy)) { Die "no venv - run: ./run-local.ps1 setup" }; return $VenvPy }
function Portable { return (Test-Path $Marker) }

function Load-DotEnv {
  $envFile = Join-Path $Root 'infra\.env'
  if (-not (Test-Path -LiteralPath $envFile)) { return }
  foreach ($line in Get-Content -LiteralPath $envFile) {
    if ($line -match '^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$') {
      $name = $Matches[1]
      $value = $Matches[2].Trim()
      if (($value.StartsWith('"') -and $value.EndsWith('"')) -or
          ($value.StartsWith("'") -and $value.EndsWith("'"))) {
        $value = $value.Substring(1, $value.Length - 2)
      }
      Set-Item "Env:$name" $value
    }
  }
}

function Download-File([string]$Url, [string]$OutFile) {
  Info "downloading $([IO.Path]::GetFileName($OutFile))"
  $old = $ProgressPreference; $ProgressPreference = 'SilentlyContinue'
  try {
    try { Start-BitsTransfer -Source $Url -Destination $OutFile -ErrorAction Stop }
    catch { Invoke-WebRequest -Uri $Url -OutFile $OutFile -UseBasicParsing }
  } finally { $ProgressPreference = $old }
  if (-not (Test-Path $OutFile)) { Die "download failed: $Url" }
}

function Extract-Zip([string]$Zip, [string]$Dest) {
  New-Item -ItemType Directory -Force -Path $Dest | Out-Null
  $bsdtar = Join-Path $env:SystemRoot 'System32\tar.exe'   # bsdtar handles .zip and is ~10x faster
  if (Test-Path $bsdtar) { & $bsdtar -x -f $Zip -C $Dest; if ($LASTEXITCODE -eq 0) { return } }
  Expand-Archive -Path $Zip -DestinationPath $Dest -Force
}

function Find-Exe([string]$Base, [string]$Name) {
  $hit = Get-ChildItem -Path $Base -Filter $Name -Recurse -File -ErrorAction SilentlyContinue | Select-Object -First 1
  if ($hit) { return $hit.FullName }
  return $null
}

# db/redis endpoints for the current mode
function Db-Url {
  if (Portable) { return "postgresql+psycopg://protrix:protrix@127.0.0.1:$PG_PORT/protrix" }
  return 'postgresql+psycopg://protrix:protrix@127.0.0.1:5432/protrix'
}
function Redis-Url {
  if (Portable) { return "redis://127.0.0.1:$REDIS_PORT/0" }
  return 'redis://127.0.0.1:6379/0'
}
function Apply-Env {
  Load-DotEnv
  $e = @{
    PROTRIX_DATABASE_URL          = (Db-Url)
    PROTRIX_REDIS_URL             = (Redis-Url)
    PROTRIX_APP_ENV               = 'local'
    PROTRIX_LOG_LEVEL             = 'INFO'
    PROTRIX_DEV_IDENTITY_ENABLED  = 'true'
    PROTRIX_DEV_JWT_SECRET        = 'dev-only-not-a-real-secret-change-me'
    PROTRIX_WEBHOOK_SHARED_SECRET = 'dev-webhook-token-change-me'
    PROTRIX_EXECUTION_ADAPTER     = 'mock'
    PROTRIX_WORKER_HEALTH_PORT    = '8100'
    PROTRIX_API_URL               = 'http://127.0.0.1:8000'
    NEXT_TELEMETRY_DISABLED       = '1'
  }
  foreach ($k in $e.Keys) {
    if (-not [Environment]::GetEnvironmentVariable($k, 'Process')) {
      Set-Item "Env:$k" $e[$k]
    }
  }
}

function Save-State($obj) {
  New-Item -ItemType Directory -Force -Path $RunDir | Out-Null
  $obj | ConvertTo-Json -Depth 6 | Set-Content -Encoding ascii -Path $PidFile
}
function Stop-PortableRedis {
  Get-CimInstance Win32_Process -Filter "Name='redis-server.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -and $_.CommandLine -match [regex]::Escape($LocalStack) -or $_.ExecutablePath -like "$LocalStack*" } |
    ForEach-Object { Kill-Tree $_.ProcessId; Info 'redis stopped' }
  # fallback: any redis-server whose exe lives under .localstack
  Get-Process redis-server -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -like "$LocalStack*" } | ForEach-Object { Kill-Tree $_.Id }
}
function Load-State { if (Test-Path $PidFile) { return (Get-Content $PidFile -Raw | ConvertFrom-Json) }; return $null }

# --------------------------------------------------------------- portable ----
function Pg-Bin([string]$exe) {
  $p = Find-Exe $PgHome $exe
  if (-not $p) { Die "portable postgres missing ($exe) - run: ./run-local.ps1 bootstrap" }
  return $p
}
function Redis-Exe {
  $p = Find-Exe $RedisHome 'redis-server.exe'
  if (-not $p) { Die "portable redis missing - run: ./run-local.ps1 bootstrap" }
  return $p
}

function Start-PortablePg {
  if (Test-Port $PG_PORT) { Info "postgres already on $PG_PORT"; return $null }
  # Start postgres.exe directly via Start-Process (fully detached handles).
  # `pg_ctl start` hangs on Windows when the caller's stdout is a pipe.
  $pg = Pg-Bin 'postgres.exe'
  $log = Join-Path $LocalStack 'postgres.log'
  # single-string ArgumentList with the (space-containing) data dir quoted -
  # an -ArgumentList *array* does not quote its elements on Windows PowerShell.
  $pgArgs = "-D `"$PgData`" -p $PG_PORT -c listen_addresses=127.0.0.1"
  $p = Start-Process -FilePath $pg -ArgumentList $pgArgs `
    -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput $log -RedirectStandardError (Join-Path $LocalStack 'postgres.err.log')
  if (-not (Wait-Port $PG_PORT 40)) { Die "portable postgres did not start (see $log)" }
  Info "postgres up on $PG_PORT (pid $($p.Id))"
  return $p.Id
}
function Stop-PortablePg {
  $pidfile = Join-Path $PgData 'postmaster.pid'
  if (-not (Test-Path $pidfile)) { return }
  $postmasterPid = $null
  try { $postmasterPid = [int]((Get-Content $pidfile)[0]) } catch { }
  $pg = Pg-Bin 'pg_ctl.exe'
  & $pg -D $PgData -m fast -w -t 20 stop 2>&1 | Out-Null
  if (Test-Port $PG_PORT) {
    & $pg -D $PgData -m immediate stop 2>&1 | Out-Null
  }
  if ($postmasterPid -and (Test-Port $PG_PORT)) { Kill-Tree $postmasterPid }
  Info 'postgres stopped'
}
function Start-PortableRedis {
  if (Test-Port $REDIS_PORT) { Info "redis already on $REDIS_PORT"; return $null }
  $exe = Redis-Exe
  $log = Join-Path $LocalStack 'redis.log'
  # This is an msys2 build - it mangles Windows paths, so pass NO paths: all
  # config on the command line as a single string, persistence off.
  $redisArgs = "--port $REDIS_PORT --bind 127.0.0.1 --save `"`" --appendonly no --protected-mode no"
  $p = Start-Process -FilePath $exe -ArgumentList $redisArgs `
    -WorkingDirectory (Split-Path $exe) -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput $log -RedirectStandardError (Join-Path $LocalStack 'redis.err.log')
  if (-not (Wait-Port $REDIS_PORT 20)) { Die "portable redis did not start (see $log)" }
  Info "redis up on $REDIS_PORT (pid $($p.Id))"
  return $p.Id
}

# ---------------------------------------------------------------- commands ---
function Do-Bootstrap {
  if (Portable) { Ok 'portable stack already bootstrapped'; return }
  New-Item -ItemType Directory -Force -Path $LocalStack | Out-Null
  $tmp = Join-Path $LocalStack '_dl'; New-Item -ItemType Directory -Force -Path $tmp | Out-Null

  Step 'PostgreSQL 16 (portable, ~300 MB)'
  if (-not (Find-Exe $PgHome 'initdb.exe')) {
    $zip = Join-Path $tmp 'pg.zip'
    if (-not (Test-Path $zip)) { Download-File $PG_URL $zip }
    Info 'extracting (this takes a minute)...'
    Extract-Zip $zip $PgHome
  }
  Ok 'postgres binaries ready'

  Step 'Redis (portable)'
  if (-not (Find-Exe $RedisHome 'redis-server.exe')) {
    $zip = Join-Path $tmp 'redis.zip'
    if (-not (Test-Path $zip)) { Download-File $REDIS_URL $zip }
    Info 'extracting...'
    Extract-Zip $zip $RedisHome
  }
  Ok 'redis binary ready'

  Step 'Init database cluster'
  if (-not (Test-Path (Join-Path $PgData 'PG_VERSION'))) {
    $initdb = Pg-Bin 'initdb.exe'
    # -A trust: this cluster only ever listens on 127.0.0.1 on a private port and
    # holds nothing but fake dev data. No password to get wrong, nothing to hang on.
    & $initdb -D $PgData -U protrix -A trust -E UTF8 --locale=C | Out-Null
    if (-not (Test-Path (Join-Path $PgData 'PG_VERSION'))) { Die 'initdb failed' }
  }
  Ok 'cluster initialised (user: protrix)'

  Step 'Create database "protrix"'
  Start-PortablePg
  $psql = Pg-Bin 'psql.exe'
  $exists = (& $psql -w -tAX -h 127.0.0.1 -p $PG_PORT -U protrix -d postgres `
      -c "SELECT 1 FROM pg_database WHERE datname='protrix'" 2>&1)
  if ("$exists".Trim() -ne '1') {
    & $psql -w -h 127.0.0.1 -p $PG_PORT -U protrix -d postgres `
      -c "CREATE DATABASE protrix OWNER protrix" | Out-Null
  }
  & $psql -w -h 127.0.0.1 -p $PG_PORT -U protrix -d protrix `
    -c "ALTER DATABASE protrix SET timezone TO 'UTC'" | Out-Null
  Ok 'database "protrix" ready'

  # keep $tmp (the downloaded .zips) so a re-bootstrap never re-downloads 300 MB
  @{ pg_port = $PG_PORT; redis_port = $REDIS_PORT; created = (Get-Date -Format o) } |
    ConvertTo-Json | Out-File -Encoding utf8 $Marker

  Write-Host ''
  Ok 'bootstrap complete. Next:  ./run-local.ps1 setup   then   ./run-local.ps1 up'
}

function Do-Setup {
  Step 'Python venv'
  if (-not (Test-Path $VenvPy)) {
    if (Have-Cmd 'python') { & python -m venv $Venv } elseif (Have-Cmd 'py') { & py -3 -m venv $Venv } else { Die 'Python 3.12+ not found' }
  }
  Ok "venv: $Venv"

  if (-not $SkipInstall) {
    Step 'Python deps (contracts + api + worker)'
    & $VenvPy -m pip install --upgrade pip --quiet
    & $VenvPy -m pip install --quiet -e "$Root\contracts\python" -r "$Root\api\requirements.txt" -r "$Root\worker\requirements.txt"
    if ($LASTEXITCODE -ne 0) { Die 'pip install failed' }
    if ($env:OS -eq 'Windows_NT') {
      & $VenvPy -m pip install --quiet -r "$Root\worker\requirements-windows.txt"
      if ($LASTEXITCODE -ne 0) { Die 'Windows MT5 dependency install failed' }
    }
    Ok 'python deps installed'

    Step 'Web deps (npm ci)'
    if (-not (Have-Cmd 'npm')) { Die 'Node/npm not found (need Node 20-22)' }
    Push-Location "$Root\web"; npm ci; Pop-Location
    if ($LASTEXITCODE -ne 0) { Die 'npm ci failed' }
    Ok 'web deps installed'
  }

  if (Portable) { Start-PortablePg | Out-Null; Start-PortableRedis | Out-Null }
  Apply-Env

  Step 'Check infrastructure'
  $dbPort = if (Portable) { $PG_PORT } else { 5432 }
  if (-not (Test-Port $dbPort)) {
    if (Portable) { Die 'portable postgres not up' }
    Die 'no PostgreSQL on :5432 - run ./run-local.ps1 bootstrap for a portable one'
  }
  Ok ("database reachable: " + (Db-Url))

  Step 'Migrate + seed'
  Push-Location "$Root\api"
  & $VenvPy -m alembic upgrade head
  if ($LASTEXITCODE -ne 0) { Pop-Location; Die 'alembic upgrade failed' }
  & $VenvPy -m app.seed
  Pop-Location
  if ($LASTEXITCODE -ne 0) { Die 'seed failed' }
  Ok 'schema at head, fake data seeded'

  Write-Host ''
  Ok 'setup complete. Next:  ./run-local.ps1 up'
}

function Launch([string]$Title, [string]$WorkDir, [string]$Inner) {
  if ($Windows) {
    $cmd = "`$Host.UI.RawUI.WindowTitle='$Title'; Set-Location '$WorkDir'; $Inner"
    return (Start-Process powershell -ArgumentList '-NoExit', '-NoProfile', '-Command', $cmd -PassThru).Id
  }
  New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
  $out = Join-Path $LogDir "$Title.log"
  $err = Join-Path $LogDir "$Title.err.log"
  $cmd = "Set-Location '$WorkDir'; $Inner"
  return (Start-Process powershell -ArgumentList '-NoProfile', '-Command', $cmd `
      -WindowStyle Hidden -PassThru -RedirectStandardOutput $out -RedirectStandardError $err).Id
}

function Do-Up {
  Get-VenvPy | Out-Null
  $redisPid = $null
  if (Portable) {
    Step 'Portable infrastructure'
    Start-PortablePg | Out-Null
    $redisPid = Start-PortableRedis
  }
  else {
    Step 'Infrastructure (system)'
    if (-not (Test-Port 5432)) { Die 'no PostgreSQL on :5432 (run ./run-local.ps1 bootstrap for a portable one)' }
    if (-not (Test-Port 6379)) { Die 'no Redis on :6379 (run ./run-local.ps1 bootstrap for a portable one)' }
    Ok 'postgres :5432 and redis :6379 reachable'
  }
  Apply-Env

  Step 'Launching api + worker + web'
  $mode = if ($Windows) { 'separate windows' } else { "hidden, logs in .run-local\logs" }
  Info $mode
  $apiId = Launch 'protrix-api' "$Root\api" "& '$VenvPy' -m uvicorn app.main:app --host 127.0.0.1 --port 8000"
  $wkId = Launch 'protrix-worker' "$Root\worker" "& '$VenvPy' -m app.main"
  $webId = Launch 'protrix-web' "$Root\web" "npm run dev"

  Save-State @{
    mode = if (Portable) { 'portable' } else { 'system' }
    api  = $apiId; worker = $wkId; web = $webId; redis = $redisPid
  }

  Info 'waiting for health...'
  $a = Wait-Port 8000 45; $w = Wait-Port 8100 45; $b = Wait-Port 3000 75
  Write-Host ''
  Ok ("api    http://localhost:8000/health   " + $(if ($a) { 'UP' } else { 'starting (check logs)' }))
  Ok ("worker http://localhost:8100/health   " + $(if ($w) { 'UP' } else { 'starting (check logs)' }))
  Ok ("web    http://localhost:3000          " + $(if ($b) { 'UP' } else { 'starting (check logs)' }))
  Write-Host ''
  Info 'post a signal:   python infra\scripts\simulate_signal.py'
  Info 'stop all:        ./run-local.ps1 down'
}

function Do-Mt5Worker {
  Get-VenvPy | Out-Null
  if (Portable) { Die 'MT5 worker requires the Docker PostgreSQL/Redis ports or system services on :5432/:6379' }
  if (-not (Test-Port 5432)) { Die 'no PostgreSQL on :5432' }
  if (-not (Test-Port 6379)) { Die 'no Redis on :6379' }

  Apply-Env
  $env:PROTRIX_DATABASE_URL = Db-Url
  $env:PROTRIX_REDIS_URL = Redis-Url
  $env:PYTHONPATH = "$Root\contracts\python;$Root\worker"
  if ($env:PROTRIX_EXECUTION_ADAPTER -ne 'mt5') { Die 'infra/.env must set PROTRIX_EXECUTION_ADAPTER=mt5' }
  if ($env:PROTRIX_MT5_TRADING_ENABLED -ne 'true') { Die 'infra/.env must set PROTRIX_MT5_TRADING_ENABLED=true' }

  Step 'Launching native MT5 demo worker'
  $mode = if ($Windows) { 'visible window' } else { 'hidden, logs in .run-local\logs' }
  Info $mode
  $wkId = Launch 'protrix-mt5-worker' "$Root\worker" "& '$VenvPy' -m app.main"
  Save-State @{
    mode = 'native-mt5'; api = $null; worker = $wkId; web = $null; redis = $null
  }
  Info 'waiting for MT5 worker health...'
  $w = Wait-Port 8100 45
  Write-Host ''
  Ok ("worker http://localhost:8100/health   " + $(if ($w) { 'UP' } else { 'starting (check .run-local\logs)' }))
  if (-not $w) { Die 'native MT5 worker did not start' }
}

function Do-TradingViewGateway {
  Get-VenvPy | Out-Null
  Load-DotEnv
  if (-not (Test-Port 8000)) { Die 'API is not reachable on :8000' }
  if (Test-Port 9000) { Die 'port :9000 is already in use' }

  $cloudflared = Join-Path $RunDir 'cloudflared.exe'
  if (-not (Test-Path -LiteralPath $cloudflared)) {
    Die 'cloudflared is missing; place the official Windows binary at .run-local\cloudflared.exe'
  }

  New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
  $gatewayId = Launch 'protrix-tradingview-gateway' $Root "& '$VenvPy' '$Root\infra\scripts\tradingview_gateway.py' --port 9000"
  if (-not (Wait-Port 9000 15)) { Die 'TradingView gateway did not start' }

  $tunnelOut = Join-Path $LogDir 'protrix-tradingview-tunnel.log'
  $tunnelErr = Join-Path $LogDir 'protrix-tradingview-tunnel.err.log'
  if (Test-Path $tunnelOut) { Remove-Item -LiteralPath $tunnelOut -Force }
  if (Test-Path $tunnelErr) { Remove-Item -LiteralPath $tunnelErr -Force }
  $tunnel = Start-Process -FilePath $cloudflared `
    -ArgumentList @('tunnel', '--no-autoupdate', '--edge-ip-version', '4', '--url', 'http://127.0.0.1:9000') `
    -WorkingDirectory $RunDir -WindowStyle Hidden -PassThru `
    -RedirectStandardOutput $tunnelOut -RedirectStandardError $tunnelErr
  Start-Sleep -Seconds 8

  $logText = ''
  foreach ($f in @($tunnelOut, $tunnelErr)) { if (Test-Path $f) { $logText += (Get-Content $f -Raw) } }
  $url = [regex]::Match($logText, 'https://[a-z0-9-]+\.trycloudflare\.com(?=\s|$)').Value
  if (-not $url) { Die "Cloudflare tunnel did not publish a URL (see $tunnelErr)" }
  if (-not $env:PROTRIX_TRADINGVIEW_WEBHOOK_SECRET) { Die 'infra/.env is missing PROTRIX_TRADINGVIEW_WEBHOOK_SECRET' }

  Save-State @{
    mode = 'native-mt5-tradingview'; api = $null; worker = $null; web = $null
    redis = $null; gateway = $gatewayId; tunnel = $tunnel.Id
  }
  Write-Host ''
  Ok "TradingView tunnel: $url"
  Info "Webhook URL: $url/webhook/tradingview/$($env:PROTRIX_TRADINGVIEW_WEBHOOK_SECRET)"
  Info 'stop gateway + tunnel: ./run-local.ps1 down'
}

function Do-Status {
  $pgP = if (Portable) { $PG_PORT } else { 5432 }
  $rdP = if (Portable) { $REDIS_PORT } else { 6379 }
  $rows = @(
    @{ n = 'postgres'; p = $pgP; u = $null },
    @{ n = 'redis   '; p = $rdP; u = $null },
    @{ n = 'api     '; p = 8000; u = 'http://localhost:8000/health' },
    @{ n = 'worker  '; p = 8100; u = 'http://localhost:8100/health' },
    @{ n = 'web     '; p = 3000; u = 'http://localhost:3000/login' }
  )
  Write-Host ("mode: " + $(if (Portable) { 'portable (.localstack)' } else { 'system PostgreSQL/Redis' }))
  foreach ($r in $rows) {
    $open = Test-Port $r.p; $x = ''
    if ($open -and $r.u) {
      try {
        $resp = Invoke-WebRequest -UseBasicParsing -TimeoutSec 4 -Uri $r.u
        $x = "HTTP $($resp.StatusCode)"
        try { $j = $resp.Content | ConvertFrom-Json; if ($j.status) { $x += " status=$($j.status)" } } catch { }
      } catch { $x = 'HTTP err' }
    }
    Write-Host ("  {0}  port {1,-6} {2}  {3}" -f $r.n, $r.p, $(if ($open) { 'LISTEN' } else { '  --  ' }), $x)
  }
}

function Do-Down {
  $s = Load-State
  if ($s) {
    foreach ($k in 'api', 'worker', 'web', 'gateway', 'tunnel') { if ($s.$k) { Info "stop $k (pid $($s.$k))"; Kill-Tree ([int]$s.$k) } }
    if ($s.redis) { Kill-Tree ([int]$s.redis) }
  }
  Get-Process powershell -ErrorAction SilentlyContinue |
    Where-Object { $_.MainWindowTitle -like 'protrix-*' } | ForEach-Object { Kill-Tree $_.Id }
  # kill any stray app processes started from this repo's venv
  Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match 'app\.main|uvicorn app\.main' -and $_.CommandLine -match [regex]::Escape($Venv) } |
    ForEach-Object { Kill-Tree $_.ProcessId }
  Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -match 'tradingview_gateway\.py' -and $_.CommandLine -match [regex]::Escape($Root) } |
    ForEach-Object { Kill-Tree $_.ProcessId }
  Get-Process cloudflared -ErrorAction SilentlyContinue |
    Where-Object { $_.Path -eq (Join-Path $RunDir 'cloudflared.exe') } |
    ForEach-Object { Kill-Tree $_.Id }
  if (Portable) { Stop-PortablePg; Stop-PortableRedis }
  if (Test-Path $PidFile) { Remove-Item $PidFile -Force }
  Ok 'stopped (data kept - use `teardown` to remove .localstack)'
}

function Do-Reset {
  Get-VenvPy | Out-Null
  if (Portable) { Start-PortablePg | Out-Null }
  Apply-Env
  Step 'downgrade base -> upgrade head -> seed'
  Push-Location "$Root\api"
  & $VenvPy -m alembic downgrade base
  & $VenvPy -m alembic upgrade head
  & $VenvPy -m app.seed
  Pop-Location
  Ok 'database reset + re-seeded'
}

function Do-Teardown {
  Do-Down
  if (Test-Path $LocalStack) {
    Step 'removing .localstack'
    Remove-Item -Recurse -Force $LocalStack
    Ok 'portable stack deleted - machine is exactly as before'
  } else { Info 'no .localstack to remove' }
}

function Do-Help {
  Write-Host @'
Protrixplus S0 - run WITHOUT Docker, without touching anything installed.

  ./run-local.ps1 bootstrap   download portable PostgreSQL 16 + Redis into .localstack (~300 MB)
  ./run-local.ps1 setup       venv + python deps + npm ci + alembic upgrade + seed
  ./run-local.ps1 up          start infra + api + worker + web   (add -Windows for visible windows)
  ./run-local.ps1 mt5-worker  start the native Windows MT5 demo worker only
  ./run-local.ps1 tradingview-gateway  expose only the webhook through HTTPS
  ./run-local.ps1 status      ports + /health
  ./run-local.ps1 down        stop everything this script started (keeps data)
  ./run-local.ps1 reset       wipe + re-migrate + re-seed the database
  ./run-local.ps1 teardown    down + delete .localstack (full reverse)

Portable mode uses PG on 55432 and Redis on 6399, bound to 127.0.0.1, no service,
no admin, no PATH/registry changes. If you already run PostgreSQL:5432 and
Redis:6379, skip `bootstrap` and it uses those.

Typical first run:
  ./run-local.ps1 bootstrap
  ./run-local.ps1 setup
  ./run-local.ps1 up
  python infra\scripts\simulate_signal.py
  start http://localhost:3000
'@
}

switch ($Command) {
  'bootstrap' { Do-Bootstrap }
  'setup'     { Do-Setup }
  'up'        { Do-Up }
  'mt5-worker' { Do-Mt5Worker }
  'tradingview-gateway' { Do-TradingViewGateway }
  'status'    { Do-Status }
  'down'      { Do-Down }
  'reset'     { Do-Reset }
  'teardown'  { Do-Teardown }
  default     { Do-Help }
}
