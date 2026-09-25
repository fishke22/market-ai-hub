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
$p = Start-Process -FilePath $Python -ArgumentList $RecorderArgs -WorkingDirectory $Root -WindowStyle Hidden -RedirectStandardOutput $Out -RedirectStandardError $Err -PassThru
Write-Host "YUANTA_LIVE_STARTING pid=$($p.Id)"
