<#
.SYNOPSIS
  Protrixplus S0 developer helper for Windows (PowerShell). Mirrors the Makefile.

.EXAMPLE
  ./dev.ps1 up
  ./dev.ps1 health
  ./dev.ps1 ci-local
#>
param(
  [Parameter(Mandatory = $true)]
  [ValidateSet('env','up','down','reset','logs','ps','health','simulate',
               'install','lint','typecheck','test-unit','test-integration','e2e','build','ci-local')]
  [string]$Task
)

$ErrorActionPreference = 'Stop'
$Compose = @('compose','-f','infra/docker-compose.yml','--env-file','infra/.env')

function Invoke-Step($name, [scriptblock]$block) {
  Write-Host "==> $name" -ForegroundColor Cyan
  & $block
  if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) { throw "$name failed ($LASTEXITCODE)" }
}

switch ($Task) {
  'env'    { if (-not (Test-Path infra/.env)) { Copy-Item infra/.env.example infra/.env } }
  'up'     { if (-not (Test-Path infra/.env)) { Copy-Item infra/.env.example infra/.env }
             docker @Compose up --build -d }
  'down'   { docker @Compose down }
  'reset'  { docker @Compose down -v }
  'logs'   { docker @Compose logs -f }
  'ps'     { docker @Compose ps }
  'health' {
    Invoke-RestMethod http://localhost:8000/health | ConvertTo-Json -Depth 5
    Invoke-RestMethod http://localhost:8100/health | ConvertTo-Json -Depth 5
    (Invoke-WebRequest http://localhost:3000/login -UseBasicParsing).StatusCode
  }
  'simulate' { python infra/scripts/simulate_signal.py }
  'install' {
    Invoke-Step 'pip'  { python -m pip install -e "contracts/python[dev]" -r api/requirements-dev.txt -r worker/requirements-dev.txt -r tests/requirements.txt }
    Invoke-Step 'npm'  { Push-Location web; npm ci; Pop-Location }
  }
  'lint' {
    Invoke-Step 'ruff check'  { ruff check contracts/python api worker }
    Invoke-Step 'ruff format' { ruff format --check contracts/python api worker }
    Invoke-Step 'eslint'      { Push-Location web; npm run lint; Pop-Location }
  }
  'typecheck' {
    Invoke-Step 'mypy contracts' { mypy contracts/python/protrix_contracts }
    Invoke-Step 'mypy api'       { Push-Location api; mypy app; Pop-Location }
    Invoke-Step 'mypy worker'    { Push-Location worker; mypy app; Pop-Location }
    Invoke-Step 'tsc'            { Push-Location web; npm run typecheck; Pop-Location }
  }
  'test-unit' {
    Invoke-Step 'contracts' { pytest contracts/python -q }
    Invoke-Step 'api'       { Push-Location api; pytest -q; Pop-Location }
    Invoke-Step 'worker'    { Push-Location worker; pytest -q; Pop-Location }
    Invoke-Step 'web'       { Push-Location web; npm test; Pop-Location }
  }
  'test-integration' { pytest tests -q }
  'e2e'   { Push-Location web; npx playwright test; Pop-Location }
  'build' { Push-Location web; npm run build; Pop-Location }
  'ci-local' {
    & $PSCommandPath lint
    & $PSCommandPath typecheck
    & $PSCommandPath test-unit
    Write-Host "local CI (no docker) passed" -ForegroundColor Green
  }
}
