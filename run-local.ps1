<#
.SYNOPSIS
  Run the Protrixplus S0 skeleton WITHOUT Docker.

  Uses a locally-installed PostgreSQL 16 and Redis 7, a Python venv, and Node,
  and launches api + worker + web each in its own PowerShell window.

.USAGE
  ./run-local.ps1 setup     # one-time: venv + deps + npm ci + create db + migrate + seed
  ./run-local.ps1 up        # start redis (if needed) + api + worker + web
  ./run-local.ps1 status    # check ports + /health
  ./run-local.ps1 down      # stop everything this script started
  ./run-local.ps1 reset     # alembic downgrade base -> upgrade head -> re-seed
  ./run-local.ps1 help

.NOTES
  Redis has no official Windows build. This script will use, in order:
  a redis already listening on 6379, `redis-server` on PATH, `memurai`, or
  `redis-server` inside WSL. See docs/RUN-LOCAL.md for install steps.
#>

param(
  [Parameter(Position = 0)]
  [ValidateSet('setup', 'up', 'down', 'status', 'reset', 'help')]
  [string]$Command = 'help',

  [string]$PgBin,                       # e.g. "C:\Program Files\PostgreSQL\16\bin"
  [string]$SuperUser = 'postgres',      # postgres superuser (only used by `setup` to create the db)
  [string]$SuperPassword,              # if omitted and needed, you'll be prompted
  [switch]$SkipInstall                  # `setup`: skip pip/npm install, just db + migrate + seed
)

$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
$Venv = Join-Path $Root '.venv'
$VenvPy = Join-Path $Venv 'Scripts\python.exe'
$StateDir = Join-Path $Root '.run-local'
$PidFile = Join-Path $StateDir 'processes.json'

# Shared environment for every child process.
$SharedEnv = @{
  PROTRIX_DATABASE_URL          = 'postgresql+psycopg://protrix:protrix@localhost:5432/protrix'
  PROTRIX_REDIS_URL             = 'redis://localhost:6379/0'
  PROTRIX_APP_ENV               = 'local'
  PROTRIX_LOG_LEVEL             = 'INFO'
  PROTRIX_DEV_IDENTITY_ENABLED  = 'true'
  PROTRIX_DEV_JWT_SECRET        = 'dev-only-not-a-real-secret-change-me'
  PROTRIX_WEBHOOK_SHARED_SECRET = 'dev-webhook-token-change-me'
  PROTRIX_WORKER_HEALTH_PORT    = '8100'
  PROTRIX_API_URL               = 'http://localhost:8000'
  NEXT_TELEMETRY_DISABLED       = '1'
}

# ---------------------------------------------------------------- helpers ----

function Info($m) { Write-Host "  $m" -ForegroundColor Gray }
function Step($m) { Write-Host "==> $m" -ForegroundColor Cyan }
function Ok($m)   { Write-Host "OK  $m" -ForegroundColor Green }
function Warn($m) { Write-Host "!!  $m" -ForegroundColor Yellow }
function Die($m)  { Write-Host "XX  $m" -ForegroundColor Red; exit 1 }

function Test-Port([int]$Port, [string]$RHost = '127.0.0.1', [int]$TimeoutMs = 800) {
  try {
    $c = New-Object System.Net.Sockets.TcpClient
    $iar = $c.BeginConnect($RHost, $Port, $null, $null)
    $ok = $iar.AsyncWaitHandle.WaitOne($TimeoutMs)
    if ($ok -and $c.Connected) { $c.EndConnect($iar); $c.Close(); return $true }
    $c.Close(); return $false
  } catch { return $false }
}

function Wait-Port([int]$Port, [int]$Seconds = 30, [string]$What = "port $Port") {
  for ($i = 0; $i -lt $Seconds; $i++) {
    if (Test-Port $Port) { return $true }
    Start-Sleep -Seconds 1
  }
  return $false
}

function Have-Cmd([string]$Name) {
  return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Resolve-PgBin {
  if ($PgBin -and (Test-Path (Join-Path $PgBin 'psql.exe'))) { return $PgBin }
  if (Have-Cmd 'psql') { return (Split-Path (Get-Command psql).Source) }
  $candidates = Get-ChildItem 'C:\Program Files\PostgreSQL' -Directory -ErrorAction SilentlyContinue |
    Sort-Object Name -Descending
  foreach ($d in $candidates) {
    $p = Join-Path $d.FullName 'bin'
    if (Test-Path (Join-Path $p 'psql.exe')) { return $p }
  }
  return $null
}

function Get-VenvPy {
  if (-not (Test-Path $VenvPy)) { Die "venv missing - run: ./run-local.ps1 setup" }
  return $VenvPy
}

function Test-DbReady {
  $py = Get-VenvPy
  $code = @'
import sys
try:
    import psycopg
    psycopg.connect("host=localhost port=5432 user=protrix password=protrix dbname=protrix",
                    connect_timeout=3).close()
except Exception as e:
    print(e); sys.exit(1)
'@
  & $py -c $code 2>$null
  return ($LASTEXITCODE -eq 0)
}

function Apply-SharedEnv {
  foreach ($k in $SharedEnv.Keys) { Set-Item -Path "Env:$k" -Value $SharedEnv[$k] }
}

function Save-Processes($list) {
  New-Item -ItemType Directory -Force -Path $StateDir | Out-Null
  $list | ConvertTo-Json -Depth 4 | Out-File -Encoding utf8 $PidFile
}

function Load-Processes {
  if (Test-Path $PidFile) { return (Get-Content $PidFile -Raw | ConvertFrom-Json) }
  return @()
}

function Kill-Tree([int]$ProcId) {
  try { & taskkill /PID $ProcId /T /F 2>$null | Out-Null } catch { }
}

# ---------------------------------------------------------------- redis ------

function Start-Redis {
  if (Test-Port 6379) { Info 'redis already listening on 6379'; return @{ method = 'external' } }

  if (Have-Cmd 'redis-server') {
    Info 'starting redis-server (PATH)'
    $p = Start-Process -FilePath 'redis-server' -ArgumentList '--save', '', '--appendonly', 'no' `
      -WindowStyle Hidden -PassThru
    return @{ method = 'native'; pid = $p.Id }
  }
  if (Have-Cmd 'memurai') {
    Info 'starting memurai'
    $p = Start-Process -FilePath 'memurai' -WindowStyle Hidden -PassThru
    return @{ method = 'memurai'; pid = $p.Id }
  }
  if (Have-Cmd 'wsl') {
    $probe = (& wsl -e sh -c 'command -v redis-server') 2>$null
    if ($probe) {
      Info 'starting redis-server inside WSL (daemonized)'
      & wsl -e sh -c 'redis-server --daemonize yes --save "" --appendonly no' | Out-Null
      return @{ method = 'wsl' }
    }
  }
  Die @'
No Redis available. Install one of:
  * WSL:      wsl --install ; then inside WSL: sudo apt-get update && sudo apt-get install -y redis-server
  * Memurai:  https://www.memurai.com/get-memurai  (native Windows, Redis-compatible)
Then re-run: ./run-local.ps1 up
'@
}

function Stop-Redis($rec) {
  if (-not $rec) { return }
  switch ($rec.method) {
    'native'  { if ($rec.pid) { Kill-Tree $rec.pid } }
    'memurai' { if ($rec.pid) { Kill-Tree $rec.pid } }
    'wsl'     { & wsl -e sh -c 'redis-cli shutdown nosave 2>/dev/null || pkill redis-server' 2>$null | Out-Null }
    default   { Info 'leaving external redis running' }
  }
}

# ---------------------------------------------------------------- launchers -

function Start-AppWindow([string]$Title, [string]$WorkDir, [string]$Inner) {
  $cmd = "`$Host.UI.RawUI.WindowTitle='$Title'; Set-Location '$WorkDir'; $Inner"
  $p = Start-Process -FilePath 'powershell' `
    -ArgumentList '-NoExit', '-NoProfile', '-Command', $cmd `
    -PassThru
  return $p.Id
}

# ---------------------------------------------------------------- commands ---

function Do-Setup {
  Step 'Python venv'
  if (-not (Test-Path $VenvPy)) {
    $py = if (Have-Cmd 'python') { 'python' } elseif (Have-Cmd 'py') { 'py -3' } else { Die 'Python 3.12+ not found' }
    & cmd /c "$py -m venv `"$Venv`""
  }
  Ok "venv at $Venv"

  if (-not $SkipInstall) {
    Step 'Python dependencies (contracts + api + worker)'
    & $VenvPy -m pip install --upgrade pip --quiet
    & $VenvPy -m pip install --quiet -e "$Root\contracts\python" -r "$Root\api\requirements.txt" -r "$Root\worker\requirements.txt"
    if ($LASTEXITCODE -ne 0) { Die 'pip install failed' }
    Ok 'python deps installed'

    Step 'Web dependencies (npm ci)'
    if (-not (Have-Cmd 'npm')) { Die 'Node.js / npm not found (need Node 20-22)' }
    Push-Location "$Root\web"
    npm ci
    Pop-Location
    if ($LASTEXITCODE -ne 0) { Die 'npm ci failed' }
    Ok 'web deps installed'
  }

  Step 'PostgreSQL'
  if (-not (Test-Port 5432)) {
    Die @'
PostgreSQL is not listening on localhost:5432.
Install PostgreSQL 16 (https://www.postgresql.org/download/windows/) and make sure
the "postgresql-x64-16" service is running, then re-run: ./run-local.ps1 setup
'@
  }
  if (Test-DbReady) {
    Ok 'database "protrix" reachable as protrix/protrix'
  }
  else {
    Warn 'role/database "protrix" not found - creating it (needs the postgres superuser)'
    $bin = Resolve-PgBin
    if (-not $bin) { Die 'psql.exe not found - pass -PgBin "C:\Program Files\PostgreSQL\16\bin"' }
    $psql = Join-Path $bin 'psql.exe'
    if (-not $SuperPassword) {
      $sec = Read-Host "Password for PostgreSQL superuser '$SuperUser'" -AsSecureString
      $SuperPassword = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
        [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec))
    }
    $env:PGPASSWORD = $SuperPassword
    $mkRole = "DO `$`$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='protrix') THEN CREATE ROLE protrix LOGIN PASSWORD 'protrix'; END IF; END `$`$;"
    & $psql -U $SuperUser -h localhost -d postgres -v ON_ERROR_STOP=1 -c $mkRole
    if ($LASTEXITCODE -ne 0) { Die 'could not create role protrix' }
    & $psql -U $SuperUser -h localhost -d postgres -c "CREATE DATABASE protrix OWNER protrix;" 2>$null
    & $psql -U $SuperUser -h localhost -d protrix -c "ALTER DATABASE protrix SET timezone TO 'UTC';" | Out-Null
    Remove-Item Env:PGPASSWORD
    if (-not (Test-DbReady)) { Die 'database still not reachable as protrix/protrix' }
    Ok 'database "protrix" created'
  }

  Step 'Migrate + seed'
  Apply-SharedEnv
  Push-Location "$Root\api"
  & $VenvPy -m alembic upgrade head
  if ($LASTEXITCODE -ne 0) { Pop-Location; Die 'alembic upgrade failed' }
  & $VenvPy -m app.seed
  Pop-Location
  if ($LASTEXITCODE -ne 0) { Die 'seed failed' }
  Ok 'schema migrated to head, fake data seeded'

  Write-Host ''
  Ok 'setup complete - now run:  ./run-local.ps1 up'
}

function Do-Up {
  if (-not (Test-Path $VenvPy)) { Die 'run ./run-local.ps1 setup first' }
  New-Item -ItemType Directory -Force -Path $StateDir | Out-Null
  Apply-SharedEnv

  Step 'Redis'
  $redis = Start-Redis
  if (-not (Wait-Port 6379 20)) { Die 'redis did not come up on 6379' }
  Ok 'redis ready on 6379'

  Step 'PostgreSQL'
  if (-not (Test-DbReady)) { Die 'db not reachable - run ./run-local.ps1 setup' }
  Ok 'db ready on 5432'

  Step 'Launching services (each in its own window)'
  $apiId = Start-AppWindow 'protrix-api' "$Root\api" `
    "& '$VenvPy' -m uvicorn app.main:app --host 0.0.0.0 --port 8000"
  $workerId = Start-AppWindow 'protrix-worker' "$Root\worker" `
    "& '$VenvPy' -m app.main"
  $webId = Start-AppWindow 'protrix-web' "$Root\web" `
    "npm run dev"

  Save-Processes @(
    @{ name = 'api'; pid = $apiId },
    @{ name = 'worker'; pid = $workerId },
    @{ name = 'web'; pid = $webId },
    @{ name = 'redis'; redis = $redis }
  )

  Info 'waiting for health...'
  $apiUp = Wait-Port 8000 40
  $wkUp = Wait-Port 8100 40
  $webUp = Wait-Port 3000 60

  Write-Host ''
  Ok  ("api    http://localhost:8000/health   " + $(if ($apiUp) { 'up' } else { 'starting' }))
  Ok  ("worker http://localhost:8100/health   " + $(if ($wkUp) { 'up' } else { 'starting' }))
  Ok  ("web    http://localhost:3000/login    " + $(if ($webUp) { 'up' } else { 'starting' }))
  Write-Host ''
  Info 'fire a signal:  ./run-local.ps1 status   then   python infra/scripts/simulate_signal.py'
  Info 'stop all:       ./run-local.ps1 down'
}

function Do-Status {
  $rows = @(
    @{ n = 'postgres'; port = 5432; url = $null },
    @{ n = 'redis   '; port = 6379; url = $null },
    @{ n = 'api     '; port = 8000; url = 'http://localhost:8000/health' },
    @{ n = 'worker  '; port = 8100; url = 'http://localhost:8100/health' },
    @{ n = 'web     '; port = 3000; url = 'http://localhost:3000/login' }
  )
  foreach ($r in $rows) {
    $open = Test-Port $r.port
    $extra = ''
    if ($open -and $r.url) {
      try {
        $resp = Invoke-WebRequest -UseBasicParsing -TimeoutSec 4 -Uri $r.url
        $extra = "HTTP $($resp.StatusCode)"
        try { $j = $resp.Content | ConvertFrom-Json; if ($j.status) { $extra += " status=$($j.status)" } } catch { }
      } catch { $extra = 'HTTP error' }
    }
    $mark = if ($open) { 'LISTEN' } else { '  --  ' }
    Write-Host ("  {0}  port {1,-5}  {2}  {3}" -f $r.n, $r.port, $mark, $extra)
  }
}

function Do-Down {
  $procs = Load-Processes
  if (-not $procs) { Warn 'nothing recorded in .run-local/processes.json'; }
  foreach ($p in $procs) {
    if ($p.name -eq 'redis') { Stop-Redis $p.redis; continue }
    if ($p.pid) { Info "stopping $($p.name) (pid $($p.pid))"; Kill-Tree ([int]$p.pid) }
  }
  # belt-and-braces: kill stragglers by window title / port owners
  Get-Process powershell -ErrorAction SilentlyContinue |
    Where-Object { $_.MainWindowTitle -like 'protrix-*' } |
    ForEach-Object { Kill-Tree $_.Id }
  if (Test-Path $PidFile) { Remove-Item $PidFile -Force }
  Ok 'stopped'
}

function Do-Reset {
  if (-not (Test-Path $VenvPy)) { Die 'run ./run-local.ps1 setup first' }
  Apply-SharedEnv
  Step 'alembic downgrade base -> upgrade head -> seed'
  Push-Location "$Root\api"
  & $VenvPy -m alembic downgrade base
  & $VenvPy -m alembic upgrade head
  & $VenvPy -m app.seed
  Pop-Location
  Ok 'database reset + re-seeded'
}

function Do-Help {
  Write-Host @'
Protrixplus S0 - run WITHOUT Docker

  ./run-local.ps1 setup     one-time: venv + deps + npm ci + create db + migrate + seed
  ./run-local.ps1 up        start redis (if needed) + api + worker + web (own windows)
  ./run-local.ps1 status    check ports + /health
  ./run-local.ps1 down      stop everything this script started
  ./run-local.ps1 reset     wipe + re-migrate + re-seed the database

Options for `setup`:
  -PgBin "C:\Program Files\PostgreSQL\16\bin"   where psql.exe lives
  -SuperUser postgres  -SuperPassword ****       to create the protrix role/db
  -SkipInstall                                   skip pip/npm, just db+migrate+seed

Prereqs: PostgreSQL 16 on :5432, Node 20-22, Python 3.12+, and a Redis
(WSL redis-server, or Memurai). See docs/RUN-LOCAL.md.
'@
}

switch ($Command) {
  'setup'  { Do-Setup }
  'up'     { Do-Up }
  'status' { Do-Status }
  'down'   { Do-Down }
  'reset'  { Do-Reset }
  default  { Do-Help }
}
