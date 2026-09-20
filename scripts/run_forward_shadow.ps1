# Phase 2V-D — Forward Shadow daily tick (research forecast ONLY, NOT trading)
# 只做：research forecast + registry write。無 Yuanta login / TradingView / order / notification。
# 預設手動執行；Windows Task Scheduler 需 user explicit opt-in（setup_windows.ps1 不得自動啟用）。

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Error "venv python not found: $python"
    exit 1
}

Write-Host "[forward_shadow] creating daily forecasts (research-only)..."
& $python -c @"
from market_ai_hub.research import forward_shadow as fs
result = fs.create_daily_forecasts()
print('origin:', result['origin'])
print('created:', len(result['created']), 'forecasts')
for f in result['created']:
    print('  ', f)
fs.build_status()
print('status updated: FORWARD_SHADOW_STATUS.json')
"@

if ($LASTEXITCODE -ne 0) {
    Write-Error "forward shadow tick failed"
    exit 1
}
Write-Host "[forward_shadow] done (research forecast only)"
