# MARKET_AI_HUB — 設定 Yuanta Legacy Quote 登入ID（本機一次性，存 Windows Credential Manager）
# 登入ID（身份證ID）是敏感 PII：只存 WinCred，不寫 source/config/docs/log。
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
$sidePy = Join-Path $Root ".venv-yuanta-futures-x86\Scripts\python.exe"

if (-not (Test-Path $sidePy)) {
  Write-Host "sidecar not set up. run: scripts\setup_yuanta_futures_x86.ps1"; exit 1
}

$env:PYTHONPATH = Join-Path $Root "src"
& $sidePy -m market_ai_hub.integrations.yuanta.setup_legacy_login_id
exit $LASTEXITCODE
