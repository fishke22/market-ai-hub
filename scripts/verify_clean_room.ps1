# Phase 2Q-F.2 — clean-room verification（fail-closed）。
# 用法（在 clean clone 內）：powershell -File scripts\verify_clean_room.ps1
# 前置：已建立 venv 並 pip install -e . + 測試依賴。
# 任何一步 exit code != 0 → 立即 FAIL，exit 1。全部 PASS 才 exit 0。

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $root
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = (Get-Command python).Source }

$failed = $false

function Step($name, $script) {
    Write-Host ("== {0} ==" -f $name)
    & $script
    if ($LASTEXITCODE -ne 0) {
        Write-Host ("{0} = FAIL" -f $name) -ForegroundColor Red
        $script:failed = $true
    } else {
        Write-Host ("{0} = PASS" -f $name) -ForegroundColor Green
    }
}

Step "ENVIRONMENT" { & $python --version }

Step "DEFAULT_PYTEST" {
    & $python -m pytest tests/ -q
}

Step "MCP_TOOLS" {
    & $python -c "import sys,asyncio; sys.path.insert(0,'src'); from market_ai_hub.mcp.server import mcp; n=len([t.name for t in asyncio.run(mcp.list_tools())]); assert n==21, f'tools={n}'; print(n,'tools')"
}

Step "SKILLS" {
    & $python -c "import pathlib; s=sorted(p.name for p in pathlib.Path('skills').iterdir() if p.is_dir()); assert s==['model-validation-audit','osaka-micro-analysis','taiwan-stock-v28'], s; print(s)"
}

Step "DOC_LINKS" {
    & $python scripts/check_docs_links.py
}

Step "SECRET_SCAN" {
    & $python scripts/secret_scan.py
}

Write-Host ""
if ($failed) {
    Write-Host "CLEAN_ROOM_ACCEPTANCE = FAIL" -ForegroundColor Red
    exit 1
}
Write-Host "CLEAN_ROOM_ACCEPTANCE = PASS" -ForegroundColor Green
exit 0
