# MARKET_AI_HUB — 檢查元大期貨行情 endpoint TCP connectivity（NO-AUTH，不送 ID/password/login）
$ErrorActionPreference = "Continue"
$hostname = "apiquote.yuantafutures.com.tw"

$endpoints = @(
  @{ name = "T (reqType=1) port 80";  port = 80 },
  @{ name = "T (reqType=1) port 443"; port = 443 },
  @{ name = "T+1 (reqType=2) port 82"; port = 82 },
  @{ name = "T+1 (reqType=2) port 442"; port = 442 }
)

foreach ($ep in $endpoints) {
  $r = Test-NetConnection -ComputerName $hostname -Port $ep.port -WarningAction SilentlyContinue
  if ($r.TcpTestSucceeded) {
    Write-Host "$($ep.name): REACHABLE"
  } else {
    Write-Host "$($ep.name): UNREACHABLE"
  }
}

Write-Host "note: TCP reachable 不代表 authentication success；不含任何 credential。"
