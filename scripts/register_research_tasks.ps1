# MARKET_AI_HUB — 註冊研究循環排程（不自動註冊；由使用者執行一次）
# 建立 2 個 Windows Scheduled Task。每週一 09:00 tick + 每週一 08:30 資料同步。
$ErrorActionPreference = "Stop"
$Py = Join-Path $PSScriptRoot "..\.venv\Scripts\python.exe"
$Py = (Resolve-Path $Py).Path
$Pkg = Join-Path $PSScriptRoot "..\src"

$argTick = "-m market_ai_hub.automation tick"
$argSync = "-m market_ai_hub.automation run-job sync_market_data"

function New-MarketTask($Name, $Time, $Arg) {
  $action = New-ScheduledTaskAction -Execute $Py -Argument $Arg -WorkingDirectory $Pkg
  $trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At $Time
  $principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
  Register-ScheduledTask -TaskName $Name -Action $action -Trigger $trigger -Principal $principal -Force | Out-Null
  Write-Host "registered: $Name"
}

New-MarketTask "MARKET_AI_HUB_ResearchTick" "09:00" $argTick
New-MarketTask "MARKET_AI_HUB_DataSync" "08:30" $argSync
Write-Host "done. 檢查：Get-ScheduledTask -TaskName 'MARKET_AI_HUB_*'"
