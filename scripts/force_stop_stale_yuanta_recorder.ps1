param([int]$HeartbeatMaxAgeSeconds = 60)
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$PreflightScript = Join-Path $PSScriptRoot "check_yuanta_recorder_owner.ps1"

function Read-OwnerState {
    $raw = & $PreflightScript -HeartbeatMaxAgeSeconds $HeartbeatMaxAgeSeconds
    if ($LASTEXITCODE -ne 0) { throw "YUANTA_STALE_FORCE_PREFLIGHT_FAILED" }
    return (($raw -join [Environment]::NewLine) | ConvertFrom-Json)
}

$pre = Read-OwnerState
if ($pre.classification -eq "NO_RUNNING_OWNER") {
    Write-Host "YUANTA_STALE_OWNER_NOT_RUNNING"
    exit 0
}

$reasons = @($pre.preflight_reasons)
$ownerPids = @($pre.owner_invocation_pids | ForEach-Object { [int]$_ })
$independent = @($pre.independent_matching_pids)
$heartbeatAge = if ($null -eq $pre.heartbeat_age_seconds) { -1 } else { [double]$pre.heartbeat_age_seconds }

if ($independent.Count -gt 0) {
    throw "YUANTA_STALE_FORCE_BLOCKED_INDEPENDENT_OWNER"
}
if ($ownerPids.Count -eq 0 -or -not $pre.status_pid) {
    throw "YUANTA_STALE_FORCE_BLOCKED_OWNER_UNVERIFIED"
}
if (-not ($reasons -contains "HEARTBEAT_STALE")) {
    throw "YUANTA_STALE_FORCE_BLOCKED_HEARTBEAT_NOT_STALE"
}
if ($heartbeatAge -le [double]$HeartbeatMaxAgeSeconds) {
    throw "YUANTA_STALE_FORCE_BLOCKED_HEARTBEAT_AGE"
}
if ($pre.tracked_measurement_gate -or $pre.runtime_measurement_gate) {
    throw "YUANTA_STALE_FORCE_BLOCKED_MEASUREMENT_GATE"
}

# This is intentionally process control only. No broker/account/order API is
# called. It is reachable only after graceful shutdown timed out and preflight
# proved one stale owner invocation with no independent duplicate.
foreach ($pidValue in ($ownerPids | Sort-Object -Descending)) {
    try {
        Stop-Process -Id $pidValue -Force -ErrorAction Stop
    } catch {
        if (Get-Process -Id $pidValue -ErrorAction SilentlyContinue) { throw }
    }
}

$deadline = (Get-Date).AddSeconds(10)
do {
    Start-Sleep -Milliseconds 250
    $after = Read-OwnerState
    if ($after.classification -eq "NO_RUNNING_OWNER") {
        Write-Host "YUANTA_STALE_OWNER_FORCE_STOPPED pids=$($ownerPids -join ',') broker_action=false"
        exit 0
    }
} while ((Get-Date) -lt $deadline)

throw "YUANTA_STALE_FORCE_STOP_TIMEOUT"
