param(
    [switch]$Apply
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Script = Join-Path $Root "scripts\sync_accuracy_v2_p5_cloud_state.py"
$TaskName = "MARKET_AI_HUB_AccuracyV2_P5_CloudSync"
$Description = "Merge public-source-only P5 cloud artifact into local append-only audit; no broker/account/order access."

$plan = [ordered]@{
    schema = "AV2P5_CLOUD_SYNC_TASK_V1"
    task_name = $TaskName
    execute = $Python
    arguments = ('"' + $Script + '" --mode merge-local')
    timezone = "Asia/Taipei"
    weekdays_only = $true
    planned_time = "19:05"
    cloud_artifact = "p5-cloud-state"
    broker_used = $false
    account_access = $false
    recorder_restart = $false
    order_action = $false
    local_audit_overwrite = $false
    apply_requested = [bool]$Apply
}

if (-not $Apply) {
    $plan.status = "DRY_RUN_NOT_REGISTERED"
    $plan | ConvertTo-Json -Depth 5
    exit 0
}

if (-not (Test-Path $Python)) { throw "P5_CLOUD_SYNC_PYTHON_NOT_FOUND" }
if (-not (Test-Path $Script)) { throw "P5_CLOUD_SYNC_SCRIPT_NOT_FOUND" }
if ([TimeZoneInfo]::Local.Id -ne "Taipei Standard Time") {
    throw "P5_CLOUD_SYNC_LOCAL_TIMEZONE_MUST_BE_TAIPEI_STANDARD_TIME"
}

$action = New-ScheduledTaskAction -Execute $Python -Argument ('"' + $Script + '" --mode merge-local') -WorkingDirectory $Root
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 19:05
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Description $Description -Force | Out-Null

$plan.status = "REGISTERED"
$plan | ConvertTo-Json -Depth 5
