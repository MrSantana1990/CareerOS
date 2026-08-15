$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot
python -m pip install -e '.\apps\api[dev]'
Push-Location apps/api
try { python -m pytest tests } finally { Pop-Location }
pnpm --dir apps/web test --passWithNoTests
