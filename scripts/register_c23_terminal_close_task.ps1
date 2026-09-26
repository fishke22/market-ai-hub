param([switch]$DryRun, [switch]$PreserveExisting)
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Script = (Resolve-Path (Join-Path $PSScriptRoot "run_c23_terminal_close_maintenance.ps1")).Path
$TaskName = "MARKET_AI_HUB_C23_Terminal_Close_Measurement"
$PowerShell = (Get-Command powershell.exe).Source
$Arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $Script + '"'
$User = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

if ($DryRun) {
    [ordered]@{
        schema = "C23_TERMINAL_CLOSE_TASK_PLAN_V1"
        task_name = $TaskName
        execute = $PowerShell
        arguments = $Arguments
        user = $User
        interval_minutes = 5
        schedule = "CONTINUOUS_POLL"
        window_guard = "OSE_SESSION_DATE_AND_15_45_TO_17_00_JST"
        max_attempts_per_trading_date = 3
        logon_type = "Interactive"
        values_exposed = $false
        broker_order_action = $false
    } | ConvertTo-Json -Depth 4
    exit 0
}

$Existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
if ($Existing -and $PreserveExisting) {
    Write-Host "PRESERVED $TaskName"
    exit 0
}

$Action = New-ScheduledTaskAction -Execute $PowerShell -Argument $Arguments -WorkingDirectory $Root
$Trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Days 3650)
$Principal = New-ScheduledTaskPrincipal -UserId $User -LogonType Interactive -RunLevel Limited
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 10) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Principal $Principal -Settings $Settings -Force | Out-Null
Write-Host "REGISTERED $TaskName user=$User interval=5m window=OSE_CLOSE_CONTROLLED"
