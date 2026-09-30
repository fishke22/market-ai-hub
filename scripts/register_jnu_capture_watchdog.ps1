param([switch]$DryRun)
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Ensure = Join-Path $PSScriptRoot "ensure_jnu_data_capture.ps1"
$HiddenRunner = (Resolve-Path (Join-Path $PSScriptRoot "run-hidden.vbs")).Path
$TaskName = "MARKET_AI_HUB_JNU_Capture_Watchdog"
$LegacyStopTaskName = "MARKET_AI_HUB_JNU_Capture_Stop_2205"
$PowerShell = (Get-Command powershell.exe).Source
$WScript = Join-Path $env:WINDIR "System32\wscript.exe"
$Arguments = '"' + $HiddenRunner + '" "' + $PowerShell + '" "-NoProfile" "-WindowStyle" "Hidden" "-ExecutionPolicy" "Bypass" "-File" "' + $Ensure + '"'
$User = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

if ($DryRun) {
    [ordered]@{
        task_name = $TaskName
        execute = $WScript
        arguments = $Arguments
        child_execute = $PowerShell
        hidden_runner = $HiddenRunner
        hidden_window = $true
        user = $User
        interval_minutes = 5
        logon_type = "Interactive"
        preferred_user_window = "18:55-22:00 Asia/Taipei (informational only)"
        early_or_late_capture_allowed = $true
        legacy_stop_task = $LegacyStopTaskName
        legacy_stop_policy = "REMOVE_CONFLICTING_FIXED_2205_STOP"
        broker_order_action = $false
    } | ConvertTo-Json -Depth 4
    exit 0
}

$action = New-ScheduledTaskAction -Execute $WScript -Argument $Arguments -WorkingDirectory $Root
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Days 3650)
$principal = New-ScheduledTaskPrincipal -UserId $User -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 3) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null

$legacyStop = Get-ScheduledTask -TaskName $LegacyStopTaskName -ErrorAction SilentlyContinue
if ($legacyStop) {
    Unregister-ScheduledTask -TaskName $LegacyStopTaskName -Confirm:$false
    Write-Host "REMOVED_LEGACY $LegacyStopTaskName"
}

Write-Host "REGISTERED $TaskName user=$User interval=5m hidden=true"
