# Phase 2V-F — Safe training launcher（resource preflight → acquire slot → launch → release）
# 用法：.\run_training_safe.ps1 -JobType "retrain" -ModelTier "GPU_HEAVY" -Command "python scripts\my_train.py"
# 預設 DESKTOP_SAFE；不獨占整台電腦。

param(
    [string]$JobType = "training",
    [string]$ModelTier = "GPU_HEAVY",
    [string]$Command = ""
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
$jobId = "job_" + (Get-Date -Format "yyyyMMddHHmmss")

if (-not (Test-Path $python)) { Write-Error "venv python not found"; exit 1 }
if (-not $Command) { Write-Error "Command required (e.g. python scripts\my_train.py)"; exit 1 }

Write-Host "[safe_training] preflight ($JobType / $ModelTier)..."
& $python -c @"
import sys
from market_ai_hub.services.resource_governor import get_governor, RESOURCE_OK
g = get_governor()
state = g.preflight('$JobType', '$ModelTier')
print('preflight state:', state)
if state != RESOURCE_OK:
    print('DEFERRED:', state)
    sys.exit(2)
"@
if ($LASTEXITCODE -eq 2) {
    Write-Host "[safe_training] resource not available, deferred (no heavy job launched)"
    exit 0
}

Write-Host "[safe_training] acquiring heavy slot..."
& $python -c @"
import sys
from market_ai_hub.services.resource_governor import get_governor, RESOURCE_OK
g = get_governor()
state = g.request_resource_slot('$jobId', '$JobType', '$ModelTier')
print('slot state:', state)
if state != RESOURCE_OK:
    print('SLOT_BLOCKED:', state)
    sys.exit(2)
"@
if ($LASTEXITCODE -eq 2) {
    Write-Host "[safe_training] could not acquire slot (another heavy job active), deferred"
    exit 0
}

Write-Host "[safe_training] launching (low priority): $Command"
try {
    Invoke-Expression $Command
    $rc = $LASTEXITCODE
} finally {
    & $python -c @"
from market_ai_hub.services.resource_governor import get_governor
get_governor().release_resource_slot('$jobId')
print('slot released')
"@
}

Write-Host "[safe_training] done (exit $rc)"
exit $rc
