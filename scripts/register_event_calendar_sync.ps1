param([switch]$DryRun)
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Py = (Resolve-Path (Join-Path $Root ".venv\Scripts\python.exe")).Path
$Script = (Resolve-Path (Join-Path $PSScriptRoot "update_event_calendar.py")).Path
$TaskName = "MARKET_AI_HUB_Event_Calendar_Sync"
$User = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

if ($DryRun) {
  [ordered]@{
    schema    = "EVENT_CALENDAR_TASK_PLAN_V1"
    task_name = $TaskName
    execute   = $Py
    arguments = '"' + $Script + '"'
    trigger   = "DAILY_19:05_LOCAL_MACHINE"
    broker_used      = $false
    credentials_used = $false
    order_action     = $false
  } | ConvertTo-Json -Depth 5
  exit 0
}

$Action   = New-ScheduledTaskAction -Execute $Py -Argument ('"' + $Script + '"') -WorkingDirectory $Root
$Trigger  = New-ScheduledTaskTrigger -Daily -At "19:05"
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -User $User -Force | Out-Null
Write-Host "registered: $TaskName"