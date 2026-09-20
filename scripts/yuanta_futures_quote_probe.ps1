# MARKET_AI_HUB — 執行元大期貨 quote probe（32-bit sidecar，auth 成功後，read-only）
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$sidePy = Join-Path $Root ".venv-yuanta-futures-x86\Scripts\python.exe"

if (-not (Test-Path $sidePy)) {
  Write-Host "sidecar not set up. run: scripts\setup_yuanta_futures_x86.ps1"; exit 1
}

$env:PYTHONPATH = Join-Path $Root "src"
$args = @("-m", "market_ai_hub.integrations.yuanta.futures_quote_probe") + $args
& $sidePy @args
exit $LASTEXITCODE
