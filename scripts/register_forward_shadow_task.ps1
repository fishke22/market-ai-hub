# Phase 2V-E — Register forward shadow Windows Task Scheduler task (OPT-IN ONLY)
# 預設 DISABLED。只有使用者明確執行本 script 才註冊。
# setup_windows.ps1 不得自動啟用。本 script 只建立「手動/按需」觸發的 task，不設自動 daily 觸發。

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$scriptPath = Join-Path $root "scripts\run_daily_forward_cycle.ps1"
$taskName = "MARKET_AI_HUB_ForwardShadow_Manual"

Write-Host "[register_task] This registers an ON-DEMAND (manual-trigger) task only."
Write-Host "  It does NOT auto-run daily. Auto-schedule requires explicit user opt-in."

$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "[register_task] task already exists: $taskName (leaving unchanged)"
    exit 0
}

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`""
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date)   # on-demand; not recurring
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description "MARKET_AI_HUB forward shadow (research-only, manual trigger, no trading)" | Out-Null

Write-Host "[register_task] registered on-demand task: $taskName"
Write-Host "  Run manually via: Start-ScheduledTask -TaskName $taskName"
Write-Host "  To auto-schedule daily, user must explicitly edit the trigger (NOT done here)."
