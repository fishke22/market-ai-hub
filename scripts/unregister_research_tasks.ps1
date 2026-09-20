# MARKET_AI_HUB — 移除研究循環排程
$ErrorActionPreference = "Continue"
foreach ($t in @("MARKET_AI_HUB_ResearchTick", "MARKET_AI_HUB_DataSync")) {
  Unregister-ScheduledTask -TaskName $t -Confirm:$false -ErrorAction SilentlyContinue
  Write-Host "unregistered: $t"
}
