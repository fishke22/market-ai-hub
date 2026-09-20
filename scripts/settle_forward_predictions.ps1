# Phase 2V-D — Settle pending forward predictions (append-only outcome)
# 只做：取得 actual → settle pending forecasts → update metrics。不得修改 forecast。

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Error "venv python not found: $python"
    exit 1
}

Write-Host "[forward_shadow] settling pending predictions..."
& $python -c @"
from market_ai_hub.research import forward_shadow as fs
result = fs.settle_pending()
print('settled:', len(result['settled']), 'forecasts')
for f in result['settled']:
    print('  ', f)
fs.build_status()
print('status updated: FORWARD_SHADOW_STATUS.json')
"@

if ($LASTEXITCODE -ne 0) {
    Write-Error "settle failed"
    exit 1
}
Write-Host "[forward_shadow] settle done (append-only)"
