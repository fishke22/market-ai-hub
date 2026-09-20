# Phase 2V-E — Import latest 225LABO Micro data (MANUAL, no auto-download)
# 使用者將合法下載的新 225LABO 檔案放入 D:\MARKET_AI_HUB_PRIVATE_INBOX\225labo
# 本 script：detect → validate → hash → dedup → normalize → update coverage
# 不自動下載；source immutable；incremental idempotent。

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
$inbox = "D:\MARKET_AI_HUB_PRIVATE_INBOX\225labo"

if (-not (Test-Path $python)) {
    Write-Error "venv python not found: $python"
    exit 1
}

if (-not (Test-Path $inbox)) {
    Write-Host "[import] inbox not found, creating: $inbox (drop new 225LABO .zip/.xlsx here)"
    New-Item -ItemType Directory -Path $inbox -Force | Out-Null
}

Write-Host "[import] scanning inbox for new 225LABO files..."
& $python -c @"
import json
from market_ai_hub.data import ylab225_ingest as ing
r = ing.ingest_from_inbox()
print('imported:', len(r['imported']), '| new_days:', r['new_days'])
for x in r['imported']:
    print('  ', x['file'], 'sha=', x['sha256'][:16], 'new_days=', x['new_days'])
for x in r['rejected']:
    print('  REJECTED:', x['file'], '-', x['reason'])
cov = ing.coverage_summary()
print('coverage:', json.dumps(cov, ensure_ascii=False))
"@

if ($LASTEXITCODE -ne 0) {
    Write-Error "import failed"
    exit 1
}
Write-Host "[import] done (incremental, idempotent, source immutable)"
