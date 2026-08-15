$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$python = Join-Path $projectRoot '.venv\Scripts\python.exe'
$node = (Get-Command node -ErrorAction Stop).Source
$next = Join-Path $projectRoot 'apps\web\node_modules\next\dist\bin\next'
$aiRoot = 'D:\DEV\IA-Local'
$llama = Join-Path $aiRoot 'runtime\llama-server.exe'
$model = Join-Path $aiRoot 'models\Qwen3-4B-Q4_K_M.gguf'

if (-not (Get-NetTCPConnection -LocalPort 8080 -State Listen -ErrorAction SilentlyContinue) -and (Test-Path $llama) -and (Test-Path $model)) {
  Start-Process -FilePath $llama -ArgumentList '--model',$model,'--alias','Qwen3-4B-CareerOS','--host','127.0.0.1','--port','8080','--ctx-size','8192','--threads','6','--jinja','--reasoning','off','--temp','0.2','--top-k','20','--top-p','0.8','--min-p','0','--presence-penalty','1.2' -WorkingDirectory $aiRoot -RedirectStandardOutput (Join-Path $aiRoot 'server-out.log') -RedirectStandardError (Join-Path $aiRoot 'server-error.log') -WindowStyle Hidden
}

if (-not (Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue)) {
  Start-Process -FilePath $python -ArgumentList '-m','uvicorn','src.main:app','--app-dir',(Join-Path $projectRoot 'apps\automation-host'),'--host','0.0.0.0','--port','8765' -WorkingDirectory $projectRoot -WindowStyle Hidden
}
if (-not (Get-NetTCPConnection -LocalPort 3000 -State Listen -ErrorAction SilentlyContinue)) {
  Start-Process -FilePath $node -ArgumentList $next,'start','--port','3000' -WorkingDirectory (Join-Path $projectRoot 'apps\web') -WindowStyle Hidden
}
