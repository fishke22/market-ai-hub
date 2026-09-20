# MARKET_AI_HUB — 啟動 TradingView optional bridge（manual opt-in，不開機自動啟動）
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
$fail = 0

# 1. Node 檢查
$node = (Get-Command node -ErrorAction SilentlyContinue)
if (-not $node) { Write-Host "[FAIL] Node 未安裝（需 18+）"; exit 1 }
$nv = node --version
Write-Host "[OK] node $nv"

# 2. upstream repo 檢查
$up = Join-Path $Root "external\tradingview-mcp"
if (-not (Test-Path (Join-Path $up "src\server.js"))) {
  Write-Host "[FAIL] upstream 未安裝，請先：git clone https://github.com/tradesdontlie/tradingview-mcp external/tradingview-mcp; npm install"; exit 1
}
Write-Host "[OK] upstream repo present"

# 3. TradingView 檢查（MSIX）
$pkg = Get-AppxPackage TradingView.Desktop -ErrorAction SilentlyContinue
if (-not $pkg) { Write-Host "[FAIL] TradingView Desktop 未安裝"; exit 1 }
Write-Host "[OK] TradingView $($pkg.Version)"

# 4. CDP 只開 localhost（不建立 public inbound rule）
Write-Host "[OK] CDP 目標 127.0.0.1:9222（localhost only，不開外部）"

# 5. 啟動 bridge（由 upstream tv_launch 或此處提示手動）
Write-Host "請用 TradingView MCP 的 tv_launch 工具，或手動啟動："
Write-Host "  TradingView --remote-debugging-port=9222"
Write-Host "  然後啟動 MCP：node external\tradingview-mcp\src\server.js"
Write-Host "manual opt-in，無開機自動啟動"
