# Phase 2V-E — Register forward shadow Windows Task Scheduler task (OPT-IN ONLY)
# 預設 DISABLED。只有使用者明確執行本 script 才註冊。
# setup_windows.ps1 不得自動啟用。本 script 只建立「手動/按需」觸發的 task，不設自動 daily 觸發。
param(
    [switch]$DryRun,
    [switch]$PreserveExisting
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$scriptPath = (Resolve-Path (Join-Path $root "scripts\run_daily_forward_cycle.ps1")).Path
$taskName = "MARKET_AI_HUB_ForwardShadow_Manual"
$arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`""

if ($DryRun) {
    [pscustomobject]@{
        schema = "MARKET_AI_TASK_PLAN_V1"
        repo_root = $root
        task_name = $taskName
        execute = "powershell.exe"
        arguments = $arguments
        trigger = "ON_DEMAND_ONLY"
    } | ConvertTo-Json -Depth 4
    exit 0
}

Write-Host "[register_task] This registers an ON-DEMAND (manual-trigger) task only."
Write-Host "  It does NOT auto-run daily. Auto-schedule requires explicit user opt-in."

$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing -and $PreserveExisting) {
    Write-Host "[register_task] task already exists: $taskName (preserved by request)"
    exit 0
}

$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $arguments -WorkingDirectory $root
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date)   # on-demand; not recurring
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -Settings $settings -Description "MARKET_AI_HUB forward shadow (research-only, manual trigger, no trading)" -Force | Out-Null

Write-Host "[register_task] registered/refreshed on-demand task: $taskName"
Write-Host "  Run manually via: Start-ScheduledTask -TaskName $taskName"
Write-Host "  To auto-schedule daily, user must explicitly edit the trigger (NOT done here)."
