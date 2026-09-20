# Phase 2V-E — Import latest 225LABO Micro data (MANUAL, no auto-download)
# 使用者將合法下載的新 225LABO 檔案放入 <DATA_ROOT>\private\inbox\225labo
# （路徑由 Python resolver 產生，PowerShell 不維護第二份 path truth）
# 本 script：detect → validate → hash → dedup → normalize → update coverage
# 不自動下載；source immutable；incremental idempotent。

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Error "venv python not found: $python"
    exit 1
}

# 單一 path truth：從 Python runtime_paths 取得 inbox path（非 hardcode D:\）
$inbox = & $python -c "from market_ai_hub.config.runtime_paths import private_inbox_dir; print(private_inbox_dir())"
$inbox = $inbox.Trim()

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
