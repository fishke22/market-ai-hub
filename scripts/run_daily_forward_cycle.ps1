# Phase 2V-E — Daily forward cycle (research only, no broker/order/position)
# 流程：ingest → freshness check → (if fresh) create forecast → settle → status → summary
# 無 TradingView dependency；無 broker。

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Error "venv python not found: $python"
    exit 1
}

Write-Host "[daily_cycle] running forward daily cycle..."
& $python -c @"
import json
from market_ai_hub.data import ylab225_ingest as ing
r = ing.run_daily_cycle()
print('ingest imported:', len(r['ingest']['imported']), 'rejected:', len(r['ingest']['rejected']))
print('coverage:', json.dumps(r['coverage'], ensure_ascii=False))
print('create:', json.dumps(r['create'], ensure_ascii=False, default=str))
print('settled:', len(r['settled']['settled']))
print()
print(r['summary'])
"@

if ($LASTEXITCODE -ne 0) {
    Write-Error "daily cycle failed"
    exit 1
}
Write-Host "[daily_cycle] done"
