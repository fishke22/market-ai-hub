param(
  [Parameter(Mandatory=$true)][int]$MarketNo,
  [Parameter(Mandatory=$true)][ValidatePattern('^[A-Za-z0-9_./-]{1,40}$')][string]$Symbol
)
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$PreflightScript = Join-Path $PSScriptRoot "check_yuanta_recorder_owner.ps1"
$PreflightRaw = & $PreflightScript
if ($LASTEXITCODE -ne 0) { throw "YUANTA_LIVE_PREFLIGHT_FAILED" }
$Preflight = ($PreflightRaw -join [Environment]::NewLine) | ConvertFrom-Json
if ($Preflight.classification -notin @("SAFE_DEFAULT_OWNER_HEALTHY", "MAINTENANCE_OWNER_RUNNING") -or
    $Preflight.status -ne "RUNNING" -or @($Preflight.health_reasons).Count -ne 0) {
  throw "YUANTA_QUOTE_REQUEST_BLOCKED_$($Preflight.classification)"
}
$Inbox = & $Python -B -c "from market_ai_hub.integrations.yuanta.live_quote_recorder import recorder_root, _load_config, CONFIG_PATH, _within; print(_within(recorder_root(), _load_config(CONFIG_PATH)['dynamic_requests'].get('inbox', 'control/inbox')))"
if ($LASTEXITCODE -ne 0) { throw "Cannot resolve recorder inbox" }
New-Item -ItemType Directory -Force -Path $Inbox | Out-Null
$id = [guid]::NewGuid().ToString("N")
$p = Join-Path $Inbox ("request-" + $id + ".json")
$temp = $p + ".partial"
@{action="subscribe"; market_no=$MarketNo; symbol=$Symbol; requested_at=(Get-Date).ToUniversalTime().ToString("o")} |
  ConvertTo-Json | Set-Content -Path $temp -Encoding UTF8
Move-Item -LiteralPath $temp -Destination $p
Write-Host "YUANTA_QUOTE_REQUEST_QUEUED $p"
