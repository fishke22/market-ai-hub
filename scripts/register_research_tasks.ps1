# MARKET_AI_HUB — 註冊研究循環排程（不自動註冊；由使用者執行一次）
# 建立 2 個 Windows Scheduled Task。每週一 09:00 tick + 每週一 08:30 資料同步。
param([switch]$DryRun)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$OutputEncoding = [Console]::OutputEncoding
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Py = (Resolve-Path (Join-Path $Root ".venv\Scripts\python.exe")).Path
$WorkDir = $Root

$plans = @(
  [pscustomobject]@{ task_name="MARKET_AI_HUB_ResearchTick"; execute=$Py; arguments="-m market_ai_hub.automation tick"; working_directory=$WorkDir; trigger="WEEKLY_MONDAY_09:00" },
  [pscustomobject]@{ task_name="MARKET_AI_HUB_DataSync"; execute=$Py; arguments="-m market_ai_hub.automation run-job sync_market_data"; working_directory=$WorkDir; trigger="WEEKLY_MONDAY_08:30" }
)

if ($DryRun) {
  [pscustomobject]@{ schema="MARKET_AI_TASK_PLAN_V1"; repo_root=$Root; tasks=$plans } | ConvertTo-Json -Depth 5
  exit 0
}

function New-MarketTask($Plan, $Time) {
  $action = New-ScheduledTaskAction -Execute $Plan.execute -Argument $Plan.arguments -WorkingDirectory $Plan.working_directory
  $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At $Time
  $principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
  Register-ScheduledTask -TaskName $Plan.task_name -Action $action -Trigger $trigger -Principal $principal -Force | Out-Null
  Write-Host "registered/refreshed: $($Plan.task_name)"
}

New-MarketTask $plans[0] "09:00"
New-MarketTask $plans[1] "08:30"
Write-Host "done. 檢查：Get-ScheduledTask -TaskName 'MARKET_AI_HUB_*'"
