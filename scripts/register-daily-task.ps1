$ErrorActionPreference = 'Stop'
$script = Join-Path $PSScriptRoot 'start-background.ps1'
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$script`""
$logonTrigger = New-ScheduledTaskTrigger -AtLogOn
$dailyTrigger = New-ScheduledTaskTrigger -Daily -At '07:50'
$triggers = @($logonTrigger, $dailyTrigger)
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName 'CareerOS Daily Agent' -Action $action -Trigger $triggers -Settings $settings -Description 'Mantém o CareerOS ativo para execuções às 08:00, 12:00 e 18:00.' -Force
