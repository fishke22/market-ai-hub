param([switch]$DryRun)
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Py = (Resolve-Path (Join-Path $Root ".venv\Scripts\python.exe")).Path
$Script = (Resolve-Path (Join-Path $PSScriptRoot "update_jpx_micro_direct.py")).Path
$TaskName = "MARKET_AI_HUB_JPX_Micro_Direct_Sync"
$User = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$Arguments = '"' + $Script + '" --months 3 --settlement-lookback-days 10'

if ($DryRun) {
  [ordered]@{
    schema = "JPX_MICRO_DIRECT_TASK_PLAN_V1"
    task_name = $TaskName
    execute = $Py
    arguments = $Arguments
    working_directory = $Root
    trigger = "DAILY_19:00_LOCAL_MACHINE"
    broker_used = $false
  } | ConvertTo-Json -Depth 5
  exit 0
}

$Action = New-ScheduledTaskAction -Execute $Py -Argument $Arguments -WorkingDirectory $Root
$Trigger = New-ScheduledTaskTrigger -Daily -At "19:00"
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -User $User -Force | Out-Null
Write-Host "registered: $TaskName"
