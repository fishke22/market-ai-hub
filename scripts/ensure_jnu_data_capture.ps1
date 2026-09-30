param()
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$StartScript = Join-Path $PSScriptRoot "start_yuanta_live_recorder.ps1"
$PreflightScript = Join-Path $PSScriptRoot "check_yuanta_recorder_owner.ps1"
$ForceStopScript = Join-Path $PSScriptRoot "force_stop_stale_yuanta_recorder.ps1"
$CoverageScript = Join-Path $PSScriptRoot "update_jnu_capture_coverage.py"
$ResearchSummaryScript = Join-Path $PSScriptRoot "update_jnu_capture_research_summary.py"
$BriefScript = Join-Path $PSScriptRoot "update_jnu_capture_brief.py"
$DatasetScript = Join-Path $PSScriptRoot "update_jnu_capture_dataset.py"
$RollupScript = Join-Path $PSScriptRoot "update_jnu_capture_window_rollup.py"
$SessionViewScript = Join-Path $PSScriptRoot "update_jnu_market_session_view.py"

$RecorderRoot = & $Python -B -c "from market_ai_hub.integrations.yuanta.live_quote_recorder import recorder_root; print(recorder_root())"
if ($LASTEXITCODE -ne 0) { throw "Cannot resolve recorder root" }
$StatePath = Join-Path $RecorderRoot "automation_watchdog.json"
$C23StatePath = Join-Path $RecorderRoot "automation\c23_terminal_close.json"

function Write-WatchdogState($Status, $Action, $Classification, $Reason) {
    $artifactRefresh = [ordered]@{
        status = "RUNNING"
        completed_steps = @()
        failed_step = $null
        failed_exit_code = $null
        failure_type = $null
        skipped_steps = @()
    }
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
        artifact_refresh = $artifactRefresh
    }
    $tmp = $StatePath + ".tmp"
    $payload | ConvertTo-Json -Depth 6 | Set-Content -Path $tmp -Encoding UTF8
    Move-Item -Force -LiteralPath $tmp -Destination $StatePath

    $runtimeBuild = ""
    if (Test-Path (Join-Path $RecorderRoot "status.json")) {
        try {
            $runtimeBuild = [string]((Get-Content (Join-Path $RecorderRoot "status.json") -Raw -Encoding UTF8 | ConvertFrom-Json).runtime_build_id)
        } catch {
            $payload["runtime_build_read_error"] = $_.Exception.GetType().Name
        }
    }

    $artifactSteps = @(
        [pscustomobject]@{
            Name = "coverage"
            Script = $CoverageScript
            Arguments = @("--recorder-root", $RecorderRoot, "--classification", $Classification, "--runtime-build-id", $runtimeBuild)
        },
        [pscustomobject]@{
            Name = "research_summary"
            Script = $ResearchSummaryScript
            Arguments = @("--recorder-root", $RecorderRoot)
        },
        [pscustomobject]@{
            Name = "live_brief"
            Script = $BriefScript
            Arguments = @("--recorder-root", $RecorderRoot)
        },
        [pscustomobject]@{
            Name = "closed_window_dataset"
            Script = $DatasetScript
            Arguments = @("--recorder-root", $RecorderRoot)
        },
        [pscustomobject]@{
            Name = "window_rollup"
            Script = $RollupScript
            Arguments = @("--recorder-root", $RecorderRoot)
        },
        [pscustomobject]@{
            Name = "market_session_view"
            Script = $SessionViewScript
            Arguments = @("--recorder-root", $RecorderRoot)
        }
    )

    $artifactFailed = $false
    foreach ($step in $artifactSteps) {
        if ($artifactFailed) {
            $artifactRefresh.skipped_steps += $step.Name
            continue
        }
        try {
            $stepArgs = [object[]]$step.Arguments
            & $Python -B $step.Script @stepArgs | Out-Null
            $stepExitCode = $LASTEXITCODE
            if ($stepExitCode -ne 0) {
                $artifactRefresh.status = "ERROR"
                $artifactRefresh.failed_step = $step.Name
                $artifactRefresh.failed_exit_code = $stepExitCode
                $artifactFailed = $true
            } else {
                $artifactRefresh.completed_steps += $step.Name
            }
        } catch {
            $artifactRefresh.status = "ERROR"
            $artifactRefresh.failed_step = $step.Name
            $artifactRefresh.failure_type = $_.Exception.GetType().Name
            $artifactFailed = $true
        }
    }
    if (-not $artifactFailed) {
        $artifactRefresh.status = "PASS"
    }

    $tmp = $StatePath + ".tmp"
    $payload | ConvertTo-Json -Depth 6 | Set-Content -Path $tmp -Encoding UTF8
    Move-Item -Force -LiteralPath $tmp -Destination $StatePath
}

if (Test-Path $C23StatePath) {
    try {
        $c23 = Get-Content $C23StatePath -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($c23.status -eq "IN_PROGRESS" -and $c23.updated_at) {
            $age = ((Get-Date).ToUniversalTime() - [datetimeoffset]::Parse($c23.updated_at).UtcDateTime).TotalMinutes
            if ($age -ge 0 -and $age -lt 15) {
                Write-WatchdogState "IDLE" "NONE" "C23_MAINTENANCE_IN_PROGRESS" "CONTROLLED_HANDOVER"
                exit 0
            }
        }
    } catch {}
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
        $gracefulStopped = $false
        try {
            & (Join-Path $PSScriptRoot "stop_yuanta_live_recorder.ps1") | Out-Host
            $gracefulStopped = ($LASTEXITCODE -eq 0)
        } catch {
            $gracefulStopped = $false
        }
        if (-not $gracefulStopped) {
            $freshRaw = & $PreflightScript
            if ($LASTEXITCODE -ne 0) { throw "STALE_OWNER_RECHECK_FAILED" }
            $fresh = ($freshRaw -join [Environment]::NewLine) | ConvertFrom-Json
            if (@($fresh.preflight_reasons) -contains "HEARTBEAT_STALE") {
                & $ForceStopScript | Out-Host
                if ($LASTEXITCODE -ne 0) { throw "STALE_OWNER_FORCE_STOP_FAILED" }
            } else {
                throw "STALE_OWNER_GRACEFUL_STOP_FAILED_HEARTBEAT_LIVE"
            }
        }
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
