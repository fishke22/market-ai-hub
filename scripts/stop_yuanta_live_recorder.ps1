$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$PreflightScript = Join-Path $PSScriptRoot "check_yuanta_recorder_owner.ps1"
$PreflightRaw = & $PreflightScript
if ($LASTEXITCODE -ne 0) { throw "YUANTA_LIVE_PREFLIGHT_FAILED" }
$Preflight = ($PreflightRaw -join [Environment]::NewLine) | ConvertFrom-Json
if ($Preflight.classification -eq "NO_RUNNING_OWNER") {
  Write-Host "YUANTA_LIVE_NOT_RUNNING"
  exit 0
}
if ($Preflight.classification -in @("BLOCKED_DUPLICATE_OWNER_RISK", "BLOCKED_OWNER_UNVERIFIED")) {
  throw "YUANTA_LIVE_STOP_BLOCKED_$($Preflight.classification)"
}
$Base = & $Python -B -c "from market_ai_hub.integrations.yuanta.live_quote_recorder import recorder_root, _load_config, CONFIG_PATH, _within; c=_load_config(CONFIG_PATH); print(_within(recorder_root(), c['dynamic_requests'].get('inbox','control/inbox')))"
if ($LASTEXITCODE -ne 0) { throw "Cannot resolve recorder inbox" }
New-Item -ItemType Directory -Force -Path $Base | Out-Null
$id = [guid]::NewGuid().ToString("N")
$request = Join-Path $Base ("shutdown-" + $id + ".json")
$temp = $request + ".partial"
@{
  action = "shutdown"
  reason = "MAINTENANCE_WINDOW"
  requested_at = (Get-Date).ToUniversalTime().ToString("o")
} | ConvertTo-Json | Set-Content -Path $temp -Encoding UTF8
Move-Item -LiteralPath $temp -Destination $request

$RecorderRoot = & $Python -B -c "from market_ai_hub.integrations.yuanta.live_quote_recorder import recorder_root; print(recorder_root())"
$Status = Join-Path $RecorderRoot "status.json"
$deadline = (Get-Date).AddSeconds(30)
do {
  Start-Sleep -Milliseconds 250
  if (Test-Path $Status) {
    try {
      $s = Get-Content $Status -Encoding utf8 -Raw | ConvertFrom-Json
      if ($s.status -in @("STOPPED", "STOPPED_WITH_UNFLUSHED_DATA")) {
        Write-Host "YUANTA_LIVE_STOPPED status=$($s.status) pid=$($s.pid)"
        if ($s.status -eq "STOPPED_WITH_UNFLUSHED_DATA") { exit 2 }
        exit 0
      }
    } catch {}
  }
} while ((Get-Date) -lt $deadline)
throw "YUANTA_LIVE_STOP_TIMEOUT"
