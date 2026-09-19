# MARKET_AI_HUB — 安裝驗證腳本
# 用法：powershell -ExecutionPolicy Bypass -File scripts\verify_install.ps1
# 最後輸出 INSTALLATION VERIFIED 或 FAIL（並列原因）。

$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$fail = @()

Write-Host "=== MARKET_AI_HUB verify_install ===" -ForegroundColor Cyan

# 1. Python
$venvPy = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    Write-Host "[FAIL] 找不到 .venv\Scripts\python.exe（請先跑 setup_windows.ps1）" -ForegroundColor Red
    Write-Host "FAIL"; exit 1
}
$ver = (& $venvPy -c "import sys;print(sys.version.split()[0])").Trim()
Write-Host "[OK] Python $ver"

# 2. 核心 dependencies
& $venvPy -c "import numpy, pandas, sklearn, xgboost, lightgbm, duckdb, pyarrow, yfinance, mcp, pydantic, exchange_calendars; print('[OK] core dependencies import')" 2>&1 | Write-Host
if ($LASTEXITCODE -ne 0) { $fail += "core dependencies import" }

# 3. market-ai import + build id
$build = (& $venvPy -c "from market_ai_hub.services.build_info import build_fingerprint; print(build_fingerprint()['build_id'])" 2>&1).Trim()
if ($LASTEXITCODE -ne 0) { $fail += "market_ai_hub import" } else { Write-Host "[OK] market_ai_hub import (build_id $build)" }

# 4. 模型可用性
& $venvPy scripts\download_models.py --check | Write-Host
if ($LASTEXITCODE -ne 0) { $fail += "models missing (run download_models.py --download)" }

# 5. Torch / CUDA（非必要）
& $venvPy -c "import torch; print('[OK] torch', torch.__version__, 'cuda', torch.cuda.is_available())" 2>&1 | Write-Host

# 6. MCP server start + health_check + build
& $venvPy -c @"
import asyncio, json
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
async def run():
    params = StdioServerParameters(command=r'$Root\.venv\Scripts\market-ai-mcp.exe', args=[])
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = await s.list_tools()
            hc = await s.call_tool('health_check', {})
            d = json.loads(hc.content[0].text)
            print('MCP tools:', len(tools.tools))
            print('health status:', d.get('status'))
            print('build_id:', d.get('build', {}).get('build_id'))
asyncio.run(run())
"@ 2>&1 | Write-Host
if ($LASTEXITCODE -ne 0) { $fail += "MCP server start / health_check" }

# 7. pytest smoke subset（輕量，不需要 GPU / 模型）
Write-Host "[..] pytest smoke subset"
& $venvPy -m pytest tests -q -m "not integration and not live" 2>&1 | Select-Object -Last 3 | Write-Host
if ($LASTEXITCODE -ne 0) { $fail += "pytest smoke subset" }

Write-Host ""
if ($fail.Count -eq 0) {
    Write-Host "INSTALLATION VERIFIED" -ForegroundColor Green
    exit 0
} else {
    Write-Host "FAIL" -ForegroundColor Red
    $fail | ForEach-Object { Write-Host " - $_" }
    exit 1
}
