param(
    [switch]$Apply
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Script = Join-Path $Root "scripts\run_accuracy_v2_p5_forward_cycle.py"
$TaskName = "MARKET_AI_HUB_AccuracyV2_P5_PublicForward"
$Description = "Public-source-only Accuracy v2 P5 forward monitor; no broker/account/recorder/order action."

$plan = [ordered]@{
    schema = "AV2P5_TASK_PLAN_V1"
    task_name = $TaskName
    execute = $Python
    arguments = "`"$Script`""
    timezone = "Asia/Taipei"
    weekdays_only = $true
    planned_times = @("08:05", "08:15")
    broker_used = $false
    credentials_used = $false
    recorder_restart = $false
    order_action = $false
    apply_requested = [bool]$Apply
}

if (-not $Apply) {
    $plan.status = "DRY_RUN_NOT_REGISTERED"
    $plan | ConvertTo-Json -Depth 5
    exit 0
}

if (-not (Test-Path $Python)) { throw "P5_PYTHON_NOT_FOUND" }
if (-not (Test-Path $Script)) { throw "P5_SCRIPT_NOT_FOUND" }
if ([TimeZoneInfo]::Local.Id -ne "Taipei Standard Time") {
    throw "P5_LOCAL_TIMEZONE_MUST_BE_TAIPEI_STANDARD_TIME"
}

$action = New-ScheduledTaskAction -Execute $Python -Argument "`"$Script`"" -WorkingDirectory $Root
$trigger1 = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 08:05
$trigger2 = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 08:15
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger @($trigger1, $trigger2) -Settings $settings -Description $Description -Force | Out-Null

$plan.status = "REGISTERED"
$plan | ConvertTo-Json -Depth 5
