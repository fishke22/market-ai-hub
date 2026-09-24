$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Base = & $Python -B -c "from market_ai_hub.integrations.yuanta.live_quote_recorder import recorder_root; print(recorder_root())"
if ($LASTEXITCODE -ne 0) { throw "Cannot resolve recorder data root" }
if (Test-Path (Join-Path $Base "status.json")) { Get-Content -Encoding utf8 (Join-Path $Base "status.json") }
if (Test-Path (Join-Path $Base "latest.json")) {
  Write-Host "--- latest ---"
  Get-Content -Encoding utf8 (Join-Path $Base "latest.json")
}
