param([switch]$DryRun)
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Ensure = Join-Path $PSScriptRoot "ensure_jnu_data_capture.ps1"
$TaskName = "MARKET_AI_HUB_JNU_Capture_Watchdog"
$PowerShell = (Get-Command powershell.exe).Source
$Arguments = '-NoProfile -ExecutionPolicy Bypass -File "' + $Ensure + '"'
$User = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

if ($DryRun) {
    [ordered]@{
        task_name = $TaskName
        execute = $PowerShell
        arguments = $Arguments
        user = $User
        interval_minutes = 5
        logon_type = "Interactive"
    } | ConvertTo-Json -Depth 4
    exit 0
}

$action = New-ScheduledTaskAction -Execute $PowerShell -Argument $Arguments -WorkingDirectory $Root
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 5) -RepetitionDuration (New-TimeSpan -Days 3650)
$principal = New-ScheduledTaskPrincipal -UserId $User -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 3) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force | Out-Null
Write-Host "REGISTERED $TaskName user=$User interval=5m"
