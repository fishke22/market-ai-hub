param(
  [Parameter(Mandatory=$true)][int]$MarketNo,
  [Parameter(Mandatory=$true)][ValidatePattern('^[A-Za-z0-9_./-]{1,40}$')][string]$Symbol
)
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Inbox = Join-Path $Root "data\live\yuanta\control\inbox"
New-Item -ItemType Directory -Force -Path $Inbox | Out-Null
$id = [guid]::NewGuid().ToString("N")
$p = Join-Path $Inbox ("request-" + $id + ".json")
@{action="subscribe"; market_no=$MarketNo; symbol=$Symbol; requested_at=(Get-Date).ToUniversalTime().ToString("o")} |
  ConvertTo-Json | Set-Content -Path $p -Encoding UTF8
Write-Host "YUANTA_QUOTE_REQUEST_QUEUED $p"
