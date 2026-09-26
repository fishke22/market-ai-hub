param([switch]$DryRun)
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Start = Join-Path $PSScriptRoot "start_yuanta_live_recorder.ps1"
$Stop = Join-Path $PSScriptRoot "stop_yuanta_live_recorder.ps1"
$Preflight = Join-Path $PSScriptRoot "check_yuanta_recorder_owner.ps1"
$Request = Join-Path $PSScriptRoot "request_yuanta_tick_detail_measurement.ps1"
$Materialize = Join-Path $PSScriptRoot "materialize_ose_terminal_close.py"
$Forward = Join-Path $PSScriptRoot "run_w32_osaka_forward_cycle.py"

$RecorderRoot = & $Python -B -c "from market_ai_hub.integrations.yuanta.live_quote_recorder import recorder_root; print(recorder_root())"
if ($LASTEXITCODE -ne 0) { throw "C23_RECORDER_ROOT_FAILED" }
$AutomationDir = Join-Path $RecorderRoot "automation"
$StatePath = Join-Path $AutomationDir "c23_terminal_close.json"
New-Item -ItemType Directory -Force -Path $AutomationDir | Out-Null

$AttemptCount = 0

function Write-State([string]$Status, [string]$Phase, [string]$Reason, [string]$TradingDate="", [string]$Contract="", [hashtable]$Extra=@{}) {
    $body = [ordered]@{
        schema = "C23_TERMINAL_CLOSE_AUTOMATION_V1"
        updated_at = (Get-Date).ToUniversalTime().ToString("o")
        status = $Status
        phase = $Phase
        reason = $Reason
        trading_date = $TradingDate
        contract_code = $Contract
        values_exposed = $false
        broker_order_action = $false
        attempt_count = $AttemptCount
    }
    foreach ($k in $Extra.Keys) { $body[$k] = $Extra[$k] }
    $tmp = $StatePath + ".tmp"
    $body | ConvertTo-Json -Depth 8 | Set-Content -Path $tmp -Encoding UTF8
    Move-Item -Force -LiteralPath $tmp -Destination $StatePath
}

$WindowJson = & $Python -B -c "import json; from datetime import datetime, timezone; from market_ai_hub.research.v2.tick_detail_source import ose_close_query_window; print(json.dumps(ose_close_query_window(datetime.now(timezone.utc)), sort_keys=True))"
if ($LASTEXITCODE -ne 0) { throw "C23_WINDOW_CHECK_FAILED" }
$Window = ($WindowJson -join [Environment]::NewLine) | ConvertFrom-Json
if ($Window.status -ne "QUERY_WINDOW_READY") {
    Write-State "IDLE" "WINDOW_CHECK" ([string]$Window.reason) ([string]$Window.trading_date)
    Write-Host "C23_TERMINAL_CLOSE_IDLE reason=$($Window.reason)"
    exit 0
}
$TradingDate = [string]$Window.trading_date

if (Test-Path $StatePath) {
    try {
        $Old = Get-Content $StatePath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ([string]$Old.trading_date -eq $TradingDate) {
            if ($Old.attempt_count) { $AttemptCount = [int]$Old.attempt_count }
            if ($Old.status -eq "SUCCESS") {
                Write-Host "C23_TERMINAL_CLOSE_ALREADY_DONE trading_date=$TradingDate"
                exit 0
            }
        }
    } catch {}
}

$Symbol = (& $Python -B -c "import re; from market_ai_hub.integrations.yuanta.live_quote_recorder import _load_config, CONFIG_PATH, resolve_default_subscriptions; rows=resolve_default_subscriptions(_load_config(CONFIG_PATH)); xs=[s for m,s,k in rows if m==207 and k=='ose_micro' and re.fullmatch(r'JNU\d{4}',s)]; print(xs[0] if xs else '')").Trim()
if ($LASTEXITCODE -ne 0 -or $Symbol -notmatch '^JNU\d{4}$') { throw "C23_EXACT_JNU_RESOLUTION_FAILED" }

if ($DryRun) {
    [ordered]@{
        schema = "C23_TERMINAL_CLOSE_AUTOMATION_PLAN_V1"
        trading_date = $TradingDate
        contract_code = $Symbol
        measurement_window_status = $Window.status
        would_start_maintenance_owner = $true
        would_materialize_daily_close = $true
        would_run_w32_forward_cycle = $true
        would_restore_safe_default_owner = $true
        values_exposed = $false
        broker_order_action = $false
    } | ConvertTo-Json -Depth 5
    exit 0
}

if ($AttemptCount -ge 3) {
    Write-State "BLOCKED" "ATTEMPT_LIMIT" "MAX_THREE_ATTEMPTS_PER_TRADING_DATE" $TradingDate $Symbol @{
        attempt_count = $AttemptCount
    }
    Write-Host "C23_TERMINAL_CLOSE_ATTEMPT_LIMIT trading_date=$TradingDate attempts=$AttemptCount"
    exit 0
}

$Mutex = New-Object System.Threading.Mutex($false, "Local\MARKET_AI_HUB_C23_TERMINAL_CLOSE")
if (-not $Mutex.WaitOne(0)) {
    Write-Host "C23_TERMINAL_CLOSE_ALREADY_RUNNING"
    $Mutex.Dispose()
    exit 0
}

$HandoverAttempted = $false
$Completed = $false
$AttemptCount += 1
try {
    Write-State "IN_PROGRESS" "PREFLIGHT" "CONTROLLED_MAINTENANCE" $TradingDate $Symbol

    $PreRaw = & $Preflight
    if ($LASTEXITCODE -ne 0) { throw "C23_PREFLIGHT_FAILED" }
    $Pre = ($PreRaw -join [Environment]::NewLine) | ConvertFrom-Json
    $Class = [string]$Pre.classification

    if ($Class -eq "MAINTENANCE_OWNER_RUNNING") {
        throw "C23_OTHER_MAINTENANCE_OWNER_RUNNING"
    }
    if ($Class -in @("BLOCKED_DUPLICATE_OWNER_RISK", "BLOCKED_OWNER_UNVERIFIED", "BLOCKED_TRACKED_MEASUREMENT_GATE_ENABLED")) {
        throw "C23_OWNER_STATE_BLOCKED_$Class"
    }
    if ($Class -in @("SAFE_DEFAULT_OWNER_HEALTHY", "SAFE_DEFAULT_OWNER_DEGRADED", "BLOCKED_RUNTIME_BUILD_STALE")) {
        Write-State "IN_PROGRESS" "STOP_SAFE_DEFAULT" "CONTROLLED_HANDOVER" $TradingDate $Symbol
        & $Stop | Out-Host
        if ($LASTEXITCODE -ne 0) { throw "C23_SAFE_DEFAULT_STOP_FAILED" }
    } elseif ($Class -ne "NO_RUNNING_OWNER") {
        throw "C23_OWNER_STATE_UNEXPECTED_$Class"
    }

    $HandoverAttempted = $true
    Write-State "IN_PROGRESS" "START_MAINTENANCE" "RUNTIME_GATE_ONLY" $TradingDate $Symbol
    & $Start -EnableTickDetailMeasurements | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "C23_MAINTENANCE_START_FAILED" }

    $PreRaw = & $Preflight
    $Pre = ($PreRaw -join [Environment]::NewLine) | ConvertFrom-Json
    if ($LASTEXITCODE -ne 0 -or $Pre.classification -ne "MAINTENANCE_OWNER_RUNNING" -or -not $Pre.runtime_measurement_gate) {
        throw "C23_MAINTENANCE_OWNER_NOT_VERIFIED"
    }

    Write-State "IN_PROGRESS" "REQUEST_MEASUREMENT" "ONE_REQUEST_PER_RUN" $TradingDate $Symbol
    $ReqOut = & $Request -Symbol $Symbol -LastCount 20
    if ($LASTEXITCODE -ne 0) { throw "C23_MEASUREMENT_QUEUE_FAILED" }
    $QueuedLine = @($ReqOut | Where-Object { $_ -like "YUANTA_TICK_DETAIL_MEASUREMENT_QUEUED *" }) | Select-Object -Last 1
    if (-not $QueuedLine) { throw "C23_MEASUREMENT_QUEUE_PATH_MISSING" }
    $QueuedPath = $QueuedLine.Substring("YUANTA_TICK_DETAIL_MEASUREMENT_QUEUED ".Length).Trim()
    $Stem = [System.IO.Path]::GetFileNameWithoutExtension($QueuedPath)
    $ControlDir = Split-Path (Split-Path $QueuedPath -Parent) -Parent
    $ProcessedResult = Join-Path (Join-Path $ControlDir "processed") ($Stem + ".result.json")
    $FailedResult = Join-Path (Join-Path $ControlDir "failed") ($Stem + ".result.json")

    $Deadline = (Get-Date).AddSeconds(20)
    $ResultPath = $null
    do {
        Start-Sleep -Milliseconds 250
        if (Test-Path $ProcessedResult) { $ResultPath = $ProcessedResult; break }
        if (Test-Path $FailedResult) { $ResultPath = $FailedResult; break }
    } while ((Get-Date) -lt $Deadline)
    if (-not $ResultPath) { throw "C23_MEASUREMENT_RESULT_TIMEOUT" }

    $Measurement = Get-Content $ResultPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($Measurement.status -ne "TICK_DETAIL_RUNTIME_EVIDENCE_RECORDED") {
        throw "C23_MEASUREMENT_FAILED_$($Measurement.status)"
    }

    Write-State "IN_PROGRESS" "MATERIALIZE_DAILY" "VERIFIED_ARTIFACT_PAIR" $TradingDate $Symbol @{
        source_snapshot_id = [string]$Measurement.source_snapshot_id
        evidence_id = [string]$Measurement.evidence_id
    }
    $MatOut = & $Python -B $Materialize --raw-artifact ([string]$Measurement.raw_artifact) --evidence-artifact ([string]$Measurement.evidence_artifact) --expected-contract-code $Symbol
    if ($LASTEXITCODE -ne 0) { throw "C23_DAILY_MATERIALIZATION_FAILED" }
    $Materialized = ($MatOut -join [Environment]::NewLine) | ConvertFrom-Json
    if ($Materialized.status -notin @("MATERIALIZED", "ALREADY_MATERIALIZED")) {
        throw "C23_DAILY_MATERIALIZATION_STATUS_$($Materialized.status)"
    }

    Write-State "IN_PROGRESS" "W32_FORWARD_CYCLE" "SETTLE_THEN_PRECOMMIT" $TradingDate $Symbol @{
        source_snapshot_id = [string]$Measurement.source_snapshot_id
        evidence_id = [string]$Measurement.evidence_id
    }
    $ForwardOut = & $Python -B $Forward --contract-code $Symbol
    if ($LASTEXITCODE -ne 0) { throw "C23_W32_FORWARD_CYCLE_FAILED" }
    $ForwardResult = ($ForwardOut -join [Environment]::NewLine) | ConvertFrom-Json

    Write-State "SUCCESS" "COMPLETE" "VERIFIED_DAILY_AND_FORWARD_CYCLE" $TradingDate $Symbol @{
        source_snapshot_id = [string]$Measurement.source_snapshot_id
        evidence_id = [string]$Measurement.evidence_id
        materialization_status = [string]$Materialized.status
        precommit_status = [string]$ForwardResult.precommit.status
        prediction_id = [string]$ForwardResult.precommit.prediction_id
        event_probability_precommit_status = [string]$ForwardResult.event_probability_precommit.status
        event_probability_prediction_id = [string]$ForwardResult.event_probability_precommit.prediction_id
        settlement_count = @($ForwardResult.settlements).Count
    }
    $Completed = $true
    Write-Host "C23_TERMINAL_CLOSE_SUCCESS trading_date=$TradingDate contract=$Symbol"
}
catch {
    Write-State "FAILED" "FAIL_CLOSED" $_.Exception.Message $TradingDate $Symbol
    Write-Error $_
    exit 1
}
finally {
    if ($HandoverAttempted) {
        # Stop either a confirmed maintenance owner or any partially started owner, then
        # restore the normal quote-only runtime.  The watchdog remains a second recovery layer.
        try { & $Stop | Out-Host } catch {}
        try { & $Start | Out-Host } catch {}
    }
    try { $Mutex.ReleaseMutex() } catch {}
    $Mutex.Dispose()
}
