$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot
if (-not (Test-Path '.env')) { throw 'Execute .\scripts\setup.ps1 e configure o arquivo .env.' }
docker info *> $null
$dockerReady = $LASTEXITCODE -eq 0
if ($dockerReady) {
  docker compose up --build -d
  docker compose ps
} else {
  Write-Warning 'Docker Desktop está desligado. Iniciando painel e agente diretamente no Windows.'
  if (-not (Test-Path 'apps\web\.next\BUILD_ID')) { pnpm --dir apps/web build }
  if (-not (Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue)) {
    $node = (Get-Command node -ErrorAction Stop).Source
    $next = Join-Path $projectRoot 'apps\web\node_modules\next\dist\bin\next'
    Start-Process -FilePath $node -ArgumentList $next,'start','--port','3000' -WorkingDirectory (Join-Path $projectRoot 'apps\web') -WindowStyle Hidden
  }
}
if (-not (Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue)) {
  Start-Process powershell -WindowStyle Hidden -ArgumentList '-NoProfile','-ExecutionPolicy','Bypass','-File',(Join-Path $PSScriptRoot 'run-automation-host.ps1')
}
Write-Host 'CareerOS: http://localhost:3000 | API: http://localhost:8001/docs'
