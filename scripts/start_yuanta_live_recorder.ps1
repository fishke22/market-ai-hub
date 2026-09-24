param([switch]$Foreground)
$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Status = Join-Path $Root "data\live\yuanta\status.json"
$Python = Join-Path $Root ".venv\Scripts\python.exe"
if (Test-Path $Status) {
  try {
    $s = Get-Content $Status -Raw | ConvertFrom-Json
    if ($s.status -eq "RUNNING" -and (Get-Process -Id $s.pid -ErrorAction SilentlyContinue)) {
      Write-Host "YUANTA_LIVE_ALREADY_RUNNING pid=$($s.pid)"
      exit 0
    }
  } catch {}
}
Set-Location $Root
if ($Foreground) {
  & $Python -m market_ai_hub.integrations.yuanta.live_quote_recorder
  exit $LASTEXITCODE
}
$LogDir = Join-Path $Root "data\live\yuanta\logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Out = Join-Path $LogDir "recorder.out.log"
$Err = Join-Path $LogDir "recorder.err.log"
$p = Start-Process -FilePath $Python -ArgumentList "-m","market_ai_hub.integrations.yuanta.live_quote_recorder" -WorkingDirectory $Root -WindowStyle Hidden -RedirectStandardOutput $Out -RedirectStandardError $Err -PassThru
Write-Host "YUANTA_LIVE_STARTING pid=$($p.Id)"
