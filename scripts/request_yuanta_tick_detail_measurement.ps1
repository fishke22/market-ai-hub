param(
  [Parameter(Mandatory=$true)]
  [ValidatePattern('^JNU\\d{4}$')]
  [string]$Symbol,
  [ValidateRange(1,20)]
  [int]$LastCount = 20
)
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Inbox = & $Python -B -c "from market_ai_hub.integrations.yuanta.live_quote_recorder import recorder_root, _load_config, CONFIG_PATH, _within; print(_within(recorder_root(), _load_config(CONFIG_PATH)['dynamic_requests'].get('inbox', 'control/inbox')))"
if ($LASTEXITCODE -ne 0) { throw "Cannot resolve recorder inbox" }
New-Item -ItemType Directory -Force -Path $Inbox | Out-Null
$id = [guid]::NewGuid().ToString("N")
$p = Join-Path $Inbox ("tick-detail-" + $id + ".json")
$temp = $p + ".partial"
@{
  action = "tick_detail_measurement"
  market_no = 207
  symbol = $Symbol.ToUpperInvariant()
  last_count = $LastCount
  requested_at = (Get-Date).ToUniversalTime().ToString("o")
} | ConvertTo-Json | Set-Content -Path $temp -Encoding UTF8
Move-Item -LiteralPath $temp -Destination $p
Write-Host "YUANTA_TICK_DETAIL_MEASUREMENT_QUEUED $p"
