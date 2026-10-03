param()
# Recorder watchdog (hidden task). Starts the recorder only when NO owner is running.
# All safety lives in start_yuanta_live_recorder.ps1 (preflight + stale-build guard);
# this script never stops, never relogs in, and never touches a healthy owner.
$ErrorActionPreference = "Continue"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Preflight = Join-Path $PSScriptRoot "check_yuanta_recorder_owner.ps1"
$Start = Join-Path $PSScriptRoot "start_yuanta_live_recorder.ps1"

# Respect the C23 terminal-close maintenance window: when its state was updated less than
# 15 minutes ago the recorder is intentionally stopped for measurement, so starting it here
# would fight the maintenance handover. Same rule as ensure_jnu_data_capture.ps1.
$RecorderRoot = & $Python -B -c "from market_ai_hub.integrations.yuanta.live_quote_recorder import recorder_root; print(recorder_root())" 2>$null
$C23State = Join-Path $RecorderRoot "automation\c23_terminal_close.json"
if (Test-Path $C23State) {
    try {
        $c23 = Get-Content $C23State -Raw -Encoding UTF8 | ConvertFrom-Json
        # Only an ACTIVE maintenance handover forbids starting; IDLE (window check) means
        # the recorder should be up, so the watchdog stays free to start it.
        if ([string]$c23.status -eq "IN_PROGRESS") {
            Write-Output "WATCHDOG_SKIP_C23_MAINTENANCE"
            exit 0
        }
    } catch { }
}

$raw = & $Preflight 2>$null
if ($LASTEXITCODE -ne 0) { exit 0 }
try {
    $p = ($raw -join [Environment]::NewLine) | ConvertFrom-Json
} catch {
    exit 0
}
if ($p.classification -eq "NO_RUNNING_OWNER") {
    & $Start | Out-Null
    exit 0
}
if ($p.classification -in @("BLOCKED_RUNTIME_BUILD_STALE", "BLOCKED_DUPLICATE_OWNER_RISK",
                            "BLOCKED_OWNER_UNVERIFIED", "BLOCKED_TRACKED_MEASUREMENT_GATE_ENABLED")) {
    Write-Output ("WATCHDOG_NOT_ACTING_" + $p.classification)
} else {
    Write-Output ("WATCHDOG_OK_" + $p.classification)
}
exit 0
