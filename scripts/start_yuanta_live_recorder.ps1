param([switch]$Foreground, [switch]$EnableTickDetailMeasurements)
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Base = & $Python -B -c "from market_ai_hub.integrations.yuanta.live_quote_recorder import recorder_root; print(recorder_root())"
if ($LASTEXITCODE -ne 0) { throw "Cannot resolve recorder data root" }
$Status = Join-Path $Base "status.json"
if (Test-Path $Status) {
  try {
    $s = Get-Content $Status -Encoding utf8 -Raw | ConvertFrom-Json
    if ($s.status -in @("RUNNING", "DEGRADED") -and (Get-Process -Id $s.pid -ErrorAction SilentlyContinue)) {
      Write-Host "YUANTA_LIVE_ALREADY_RUNNING pid=$($s.pid)"
      exit 0
    }
  } catch {}
}
Set-Location $Root
$RecorderArgs = @("-m", "market_ai_hub.integrations.yuanta.live_quote_recorder")
if ($EnableTickDetailMeasurements) {
  $RecorderArgs += "--enable-tick-detail-measurements"
}
if ($Foreground) {
  & $Python @RecorderArgs
  exit $LASTEXITCODE
}
$LogDir = Join-Path $Base "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Out = Join-Path $LogDir "recorder.out.log"
$Err = Join-Path $LogDir "recorder.err.log"
$ExpectedBuild = & $Python -B -c "from market_ai_hub.services.build_info import build_fingerprint; print(build_fingerprint()['build_id'])"
if ($LASTEXITCODE -ne 0) { throw "Cannot resolve recorder build id" }
$StartedAt = (Get-Date).ToUniversalTime()
$p = Start-Process -FilePath $Python -ArgumentList $RecorderArgs -WorkingDirectory $Root -WindowStyle Hidden -RedirectStandardOutput $Out -RedirectStandardError $Err -PassThru
Write-Host "YUANTA_LIVE_STARTING pid=$($p.Id)"
$deadline = (Get-Date).AddSeconds(60)
do {
  Start-Sleep -Milliseconds 250
  if (Test-Path $Status) {
    try {
      $s = Get-Content $Status -Encoding utf8 -Raw | ConvertFrom-Json
      $fresh = $false
      foreach ($field in @("heartbeat_at", "started_at", "stopped_at")) {
        $value = $s.$field
        if ($value) {
          $ts = [datetimeoffset]::Parse($value).UtcDateTime
          if ($ts -ge $StartedAt.AddSeconds(-2)) {
            $fresh = $true
            break
          }
        }
      }
      if ($fresh -and $s.status -eq "START_FAILED") {
        throw "YUANTA_LIVE_START_FAILED stage=$($s.startup_stage) error=$($s.fatal_error) login_msg_code=$($s.login_msg_code)"
      }
      if ($fresh -and $s.status -in @("RUNNING", "DEGRADED")) {
        if ($s.runtime_build_id -ne $ExpectedBuild) {
          throw "YUANTA_LIVE_RUNTIME_BUILD_MISMATCH expected=$ExpectedBuild actual=$($s.runtime_build_id)"
        }
        if ($EnableTickDetailMeasurements -and -not $s.tick_detail_measurements_runtime_enabled) {
          throw "YUANTA_LIVE_MEASUREMENT_GATE_NOT_ENABLED"
        }
        Write-Host "YUANTA_LIVE_RUNNING pid=$($s.pid) status=$($s.status) build=$($s.runtime_build_id)"
        exit 0
      }
    } catch {
      if ($_.Exception.Message -like "YUANTA_LIVE_*") { throw }
    }
  }
} while ((Get-Date) -lt $deadline)
throw "YUANTA_LIVE_START_TIMEOUT_NO_FRESH_STATUS"
