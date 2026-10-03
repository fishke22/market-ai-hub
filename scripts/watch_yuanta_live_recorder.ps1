param()
# Recorder watchdog (hidden task). Starts the recorder only when NO owner is running.
# All safety lives in start_yuanta_live_recorder.ps1 (preflight + stale-build guard);
# this script never stops, never relogs in, and never touches a healthy owner.
$ErrorActionPreference = "Continue"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Preflight = Join-Path $PSScriptRoot "check_yuanta_recorder_owner.ps1"
$Start = Join-Path $PSScriptRoot "start_yuanta_live_recorder.ps1"

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
