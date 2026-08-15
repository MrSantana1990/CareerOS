$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { python -m venv .venv }
& $python -m pip install --disable-pip-version-check -e '.\apps\automation-host'
& $python -m uvicorn src.main:app --app-dir apps/automation-host --host 0.0.0.0 --port 8765
