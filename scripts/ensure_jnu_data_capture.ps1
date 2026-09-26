param()
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$StartScript = Join-Path $PSScriptRoot "start_yuanta_live_recorder.ps1"
$PreflightScript = Join-Path $PSScriptRoot "check_yuanta_recorder_owner.ps1"

$RecorderRoot = & $Python -B -c "from market_ai_hub.integrations.yuanta.live_quote_recorder import recorder_root; print(recorder_root())"
if ($LASTEXITCODE -ne 0) { throw "Cannot resolve recorder root" }
$StatePath = Join-Path $RecorderRoot "automation_watchdog.json"

function Write-WatchdogState($Status, $Action, $Classification, $Reason) {
    $payload = [ordered]@{
        version = 1
        checked_at = (Get-Date).ToUniversalTime().ToString("o")
        local_day = (Get-Date).DayOfWeek.ToString()
        status = $Status
        action = $Action
        classification = $Classification
        reason = $Reason
        quote_only = $true
        broker_order_action = $false
        jnu_microstructure_requested = $true
    }
    $tmp = $StatePath + ".tmp"
    $payload | ConvertTo-Json -Depth 4 | Set-Content -Path $tmp -Encoding UTF8
    Move-Item -Force -LiteralPath $tmp -Destination $StatePath
}

$day = (Get-Date).DayOfWeek
$OseSession = & $Python -B -c "from datetime import datetime; from zoneinfo import ZoneInfo; from market_ai_hub.services.calendar import is_ose_derivatives_session; d=datetime.now(ZoneInfo('Asia/Tokyo')).date(); print('true' if is_ose_derivatives_session(d) else 'false')"
if ($LASTEXITCODE -ne 0) {
    Write-WatchdogState "ERROR" "NONE" "OSE_CALENDAR_CHECK_FAILED" "FAIL_CLOSED"
    exit 1
}
if (($OseSession -join "").Trim().ToLowerInvariant() -ne "true") {
    Write-WatchdogState "IDLE" "NONE" "OSE_NON_SESSION_DATE" "JPX_OSE_CALENDAR"
    exit 0
}

try {
    $raw = & $PreflightScript
    if ($LASTEXITCODE -ne 0) { throw "PREFLIGHT_FAILED" }
    $pre = ($raw -join [Environment]::NewLine) | ConvertFrom-Json
    $class = [string]$pre.classification

    if ($class -eq "BLOCKED_RUNTIME_BUILD_STALE") {
        & (Join-Path $PSScriptRoot "stop_yuanta_live_recorder.ps1") | Out-Host
        if ($LASTEXITCODE -ne 0) { throw "STALE_OWNER_STOP_FAILED" }
        Start-Sleep -Seconds 1
        $class = "NO_RUNNING_OWNER"
    }

    if ($class -eq "NO_RUNNING_OWNER") {
        & $StartScript | Out-Host
        if ($LASTEXITCODE -ne 0) { throw "START_FAILED" }
        Start-Sleep -Seconds 2
        $raw = & $PreflightScript
        $pre = ($raw -join [Environment]::NewLine) | ConvertFrom-Json
        Write-WatchdogState "ACTIVE" "STARTED_RECORDER" ([string]$pre.classification) "OSE_SESSION_AUTO_START"
        exit 0
    }

    if ($class -in @("SAFE_DEFAULT_OWNER_HEALTHY","SAFE_DEFAULT_OWNER_DEGRADED","MAINTENANCE_OWNER_RUNNING")) {
        Write-WatchdogState "ACTIVE" "KEEP_EXISTING_OWNER" $class "SINGLE_OWNER_PRESENT"
        exit 0
    }

    Write-WatchdogState "BLOCKED" "NONE" $class "FAIL_CLOSED_PREFLIGHT"
    exit 2
}
catch {
    Write-WatchdogState "ERROR" "NONE" "UNKNOWN" $_.Exception.GetType().Name
    exit 1
}
