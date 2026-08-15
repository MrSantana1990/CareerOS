$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot
if (-not (Test-Path '.env')) { Copy-Item -LiteralPath '.env.example' -Destination '.env'; Write-Host 'Arquivo .env criado. Troque as senhas antes de iniciar.' }
corepack enable
pnpm install
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { python -m venv .venv }
& $python -m pip install -e '.\apps\automation-host'
Write-Host 'Dependências instaladas. Revise .env e execute .\scripts\start.ps1.'
