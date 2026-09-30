param([switch]$Apply)
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Script = Join-Path $Root "scripts\dispatch_accuracy_v2_p5_zero_cost_fallback.py"
$TaskName = "MARKET_AI_HUB_AccuracyV2_P5_ZeroCostFallback"
$User = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

$plan = [ordered]@{
    schema = "AV2P5_ZERO_COST_LOCAL_TASK_V1"
    task_name = $TaskName
    execute = $Python
    arguments = ('"' + $Script + '"')
    timezone = "Asia/Taipei"
    weekdays_only = $true
    planned_times = @("07:52", "08:08")
    github_public_standard_runner_only = $true
    aws_required = $false
    paid_service_required = $false
    broker_used = $false
    recorder_restart = $false
    account_access = $false
    order_action = $false
    apply_requested = [bool]$Apply
}
if (-not $Apply) {
    $plan.status = "DRY_RUN_NOT_REGISTERED"
    $plan | ConvertTo-Json -Depth 5
    exit 0
}
if (-not (Test-Path $Python)) { throw "P5_ZERO_COST_PYTHON_NOT_FOUND" }
if (-not (Test-Path $Script)) { throw "P5_ZERO_COST_DISPATCH_SCRIPT_NOT_FOUND" }
if ([TimeZoneInfo]::Local.Id -ne "Taipei Standard Time") {
    throw "P5_ZERO_COST_LOCAL_TIMEZONE_MUST_BE_TAIPEI_STANDARD_TIME"
}
if (-not (Get-Command gh.exe -ErrorAction SilentlyContinue)) {
    throw "P5_ZERO_COST_GH_CLI_NOT_FOUND"
}

$action = New-ScheduledTaskAction -Execute $Python -Argument ('"' + $Script + '"') -WorkingDirectory $Root
$triggers = @(
    (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 07:52),
    (New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday,Tuesday,Wednesday,Thursday,Friday -At 08:08)
)
$principal = New-ScheduledTaskPrincipal -UserId $User -LogonType Interactive -RunLevel Limited
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 2)
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $triggers -Principal $principal -Settings $settings -Force | Out-Null
$plan.status = "REGISTERED"
$plan | ConvertTo-Json -Depth 5
