# Phase 2Q-F.1 — clean-room verification（clone/setup 已另行完成後執行）
# 用法（在 clean clone 內）：
#   powershell -File scripts\verify_clean_room.ps1
# 前置：已建立 venv 並 pip install -e . + 測試依賴。
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = (Get-Command python).Source }

Write-Host "== environment check =="
& $python --version

Write-Host "== default full pytest =="
& $python -m pytest tests/ -q

Write-Host "== MCP tool discovery =="
& $python -c "import sys,asyncio; sys.path.insert(0,'src'); from market_ai_hub.mcp.server import mcp; print(len([t.name for t in asyncio.run(mcp.list_tools())]), 'tools')"

Write-Host "== skills discovery =="
& $python -c "import pathlib; print(sorted(p.name for p in pathlib.Path('skills').iterdir() if p.is_dir()))"

Write-Host "== docs links =="
& $python scripts/check_docs_links.py

Write-Host "== secret/publication sanity =="
& $python scripts/secret_scan.py

Write-Host "clean-room verification done"
