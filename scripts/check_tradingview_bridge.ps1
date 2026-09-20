# MARKET_AI_HUB — 檢查 TradingView optional bridge 狀態（唯讀）
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot

$node = (Get-Command node -ErrorAction SilentlyContinue)
Write-Host "node: $(if ($node) { node --version } else { 'MISSING' })"

$up = Join-Path $Root "external\tradingview-mcp\src\server.js"
Write-Host "upstream repo: $(if (Test-Path $up) { 'present' } else { 'MISSING' })"

$pkg = Get-AppxPackage TradingView.Desktop -ErrorAction SilentlyContinue
Write-Host "TradingView: $(if ($pkg) { $pkg.Version } else { 'NOT INSTALLED' })"

# CDP localhost probe
try {
  $r = Invoke-WebRequest -Uri "http://127.0.0.1:9222/json/version" -TimeoutSec 3 -UseBasicParsing
  Write-Host "CDP 127.0.0.1:9222: REACHABLE"
} catch {
  Write-Host "CDP 127.0.0.1:9222: NOT REACHABLE（TradingView 未開 debug port）"
}

# config
$cfg = Join-Path $Root "config\tradingview.yaml"
if (Test-Path $cfg) {
  $enabled = (Select-String -Path $cfg -Pattern '^enabled:' | ForEach-Object { $_.Line })
  Write-Host "config: $enabled（預設 disabled，使用者明確啟用才用）"
}
