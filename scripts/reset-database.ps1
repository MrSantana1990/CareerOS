$ErrorActionPreference = 'Stop'
$answer = Read-Host 'Isso remove o volume PostgreSQL do CareerOS. Digite RESET para confirmar'
if ($answer -ne 'RESET') { Write-Host 'Cancelado.'; exit 0 }
Set-Location (Split-Path -Parent $PSScriptRoot)
docker compose down
$volume = docker volume ls --format '{{.Name}}' | Where-Object { $_ -eq 'careeros_postgres_data' }
if ($volume) { docker volume rm $volume }

