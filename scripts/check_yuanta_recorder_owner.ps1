param([int]$HeartbeatMaxAgeSeconds = 60)
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"

$RecorderRoot = & $Python -B -c "from market_ai_hub.integrations.yuanta.live_quote_recorder import recorder_root; print(recorder_root())"
if ($LASTEXITCODE -ne 0) { throw "Cannot resolve recorder data root" }
$DiskBuild = & $Python -B -c "from market_ai_hub.services.build_info import build_fingerprint; print(build_fingerprint()['build_id'])"
if ($LASTEXITCODE -ne 0) { throw "Cannot resolve disk build id" }
$TrackedMeasurement = & $Python -B -c "from market_ai_hub.integrations.yuanta.live_quote_recorder import _load_config, CONFIG_PATH; print(str(bool(_load_config(CONFIG_PATH).get('tick_detail_measurements',{}).get('enabled',False))).lower())"
if ($LASTEXITCODE -ne 0) { throw "Cannot resolve tracked measurement gate" }

$StatusPath = Join-Path $RecorderRoot "status.json"
$status = $null
if (Test-Path $StatusPath) {
    try { $status = Get-Content $StatusPath -Encoding utf8 -Raw | ConvertFrom-Json } catch {}
}

$matching = @(Get-CimInstance Win32_Process | Where-Object {
    $_.Name -match '^python' -and
    $_.CommandLine -match 'market_ai_hub\.integrations\.yuanta\.live_quote_recorder'
})
$byPid = @{}
foreach ($proc in $matching) { $byPid[[int]$proc.ProcessId] = $proc }
$ownerPid = if ($status -and $status.pid) { [int]$status.pid } else { 0 }
$component = @{}
if ($ownerPid -and $byPid.ContainsKey($ownerPid)) {
    $component[$ownerPid] = $true
    do {
        $changed = $false
        foreach ($proc in $matching) {
            $pidValue = [int]$proc.ProcessId
            if ($component.ContainsKey($pidValue)) { continue }
            $connected = $false
            foreach ($componentPid in @($component.Keys)) {
                $node = $byPid[[int]$componentPid]
                if ([int]$proc.ParentProcessId -eq [int]$componentPid -or
                    [int]$node.ParentProcessId -eq $pidValue) {
                    $connected = $true
                    break
                }
            }
            if ($connected) {
                $component[$pidValue] = $true
                $changed = $true
            }
        }
    } while ($changed)
}

$ownerInvocationPids = @($component.Keys | ForEach-Object { [int]$_ } | Sort-Object)
$independentPids = @($matching | Where-Object {
    -not $component.ContainsKey([int]$_.ProcessId)
} | ForEach-Object { [int]$_.ProcessId } | Sort-Object)

$heartbeatAge = $null
if ($status -and $status.heartbeat_at) {
    try {
        $heartbeat = [datetimeoffset]::Parse([string]$status.heartbeat_at)
        $heartbeatAge = [math]::Max(0, ([datetimeoffset]::UtcNow - $heartbeat.ToUniversalTime()).TotalSeconds)
    } catch {}
}
$reasons = @()
if (-not $status) { $reasons += "STATUS_MISSING" }
if ($ownerPid -and -not $byPid.ContainsKey($ownerPid)) { $reasons += "OWNER_PID_NOT_RUNNING" }
if ($independentPids.Count -gt 0) { $reasons += "INDEPENDENT_RECORDER_PROCESS" }
if ($null -eq $heartbeatAge) { $reasons += "HEARTBEAT_MISSING" }
elseif ($heartbeatAge -gt $HeartbeatMaxAgeSeconds) { $reasons += "HEARTBEAT_STALE" }
if ($status -and $status.runtime_build_id -and [string]$status.runtime_build_id -ne [string]$DiskBuild) {
    $reasons += "RUNTIME_BUILD_STALE"
}
if ($TrackedMeasurement -ne "false") { $reasons += "TRACKED_MEASUREMENT_GATE_ENABLED" }

$class = "NO_RUNNING_OWNER"
if ($matching.Count -gt 0 -and (-not $status -or -not $ownerPid -or -not $byPid.ContainsKey($ownerPid))) {
    $class = "BLOCKED_OWNER_UNVERIFIED"
} elseif ($status -and $ownerPid -and $byPid.ContainsKey($ownerPid)) {
    if ($independentPids.Count -gt 0) { $class = "BLOCKED_DUPLICATE_OWNER_RISK" }
    elseif ($TrackedMeasurement -ne "false") { $class = "BLOCKED_TRACKED_MEASUREMENT_GATE_ENABLED" }
    elseif ($reasons -contains "RUNTIME_BUILD_STALE") { $class = "BLOCKED_RUNTIME_BUILD_STALE" }
    elseif ($status.tick_detail_measurements_runtime_enabled) { $class = "MAINTENANCE_OWNER_RUNNING" }
    elseif ([string]$status.status -eq "RUNNING" -and -not ($reasons -contains "HEARTBEAT_STALE")) {
        $class = "SAFE_DEFAULT_OWNER_HEALTHY"
    } else { $class = "SAFE_DEFAULT_OWNER_DEGRADED" }
}

[ordered]@{
    classification = $class
    recorder_root = [string]$RecorderRoot
    status = if ($status) { [string]$status.status } else { $null }
    status_pid = $ownerPid
    owner_invocation_pids = $ownerInvocationPids
    independent_matching_pids = $independentPids
    matching_python_process_count = $matching.Count
    heartbeat_age_seconds = if ($null -eq $heartbeatAge) { $null } else { [math]::Round($heartbeatAge, 3) }
    heartbeat_max_age_seconds = $HeartbeatMaxAgeSeconds
    runtime_build_id = if ($status) { [string]$status.runtime_build_id } else { $null }
    disk_build_id = [string]$DiskBuild
    runtime_measurement_gate = if ($status) { [bool]$status.tick_detail_measurements_runtime_enabled } else { $null }
    tracked_measurement_gate = ($TrackedMeasurement -eq "true")
    health_reasons = if ($status -and $status.health_reasons) { @($status.health_reasons) } else { @() }
    preflight_reasons = $reasons
    broker_action_performed = $false
} | ConvertTo-Json -Depth 6
