$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Base = Join-Path $Root "data\live\yuanta"
if (Test-Path (Join-Path $Base "status.json")) { Get-Content (Join-Path $Base "status.json") }
if (Test-Path (Join-Path $Base "latest.json")) {
  Write-Host "--- latest ---"
  Get-Content (Join-Path $Base "latest.json")
}
