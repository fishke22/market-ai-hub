# MARKET_AI_HUB — read-only external relocation gate preflight
# No package install, no credential write, no certificate import/export, no COM registration, no broker login.
param(
  [switch]$Json
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $Root

function Invoke-Capture([string]$File, [string[]]$ArgumentList) {
  $out = & $File @ArgumentList 2>&1
  return [pscustomobject]@{
    exit_code = $LASTEXITCODE
    output = @($out | ForEach-Object { "$_" })
  }
}

$windows = [System.Environment]::OSVersion.Platform -eq [System.PlatformID]::Win32NT
$py = Join-Path $Root ".venv\Scripts\python.exe"
$verifyInstall = Join-Path $Root "scripts\verify_install.ps1"
$certCheck = Join-Path $Root "scripts\check_yuanta_certificate.ps1"
$comCheck = Join-Path $Root "scripts\check_yuanta_futures_com.ps1"

$credential = [pscustomobject]@{ exit_code = 1; output = @("main venv unavailable") }
if (Test-Path -LiteralPath $py) {
  $credential = Invoke-Capture -File $py -ArgumentList @("-B", "scripts\setup_yuanta_credentials.py", "--status")
}
$cert = Invoke-Capture -File "powershell" -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $certCheck)
$com = Invoke-Capture -File "powershell" -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $comCheck)

$credentialMap = @{}
foreach ($line in $credential.output) {
  if ($line -match '^([a-z_]+)=(CONFIGURED|NOT_CONFIGURED)$') { $credentialMap[$Matches[1]] = $Matches[2] }
}
$certMap = @{}
foreach ($line in $cert.output) {
  if ($line -match '^([a-z_]+):\s*(.+)$') { $certMap[$Matches[1]] = $Matches[2] }
}
$comReady = @($com.output | Where-Object { $_ -eq 'RESULT: READY_FOR_AUTH' }).Count -gt 0

$result = [ordered]@{
  schema = "EXTERNAL_RELOCATION_PREFLIGHT_V1"
  repo_root = $Root
  read_only = $true
  windows = $windows
  gates = [ordered]@{
    full_dependency_install_fresh_venv = [ordered]@{
      status = "UNVERIFIED_EXTERNAL_GATE"
      evidence_command = "powershell -ExecutionPolicy Bypass -File scripts\\verify_install.ps1"
      note = "This preflight does not install packages and does not run the full install verifier automatically."
      verifier_present = (Test-Path -LiteralPath $verifyInstall)
    }
    new_windows_clean_machine = [ordered]@{
      status = "UNVERIFIED_EXTERNAL_GATE"
      note = "Must be run on a separately provisioned clean Windows machine; current-machine success cannot close this cell."
    }
    yuanta_wincred_recreation = [ordered]@{
      status = "UNVERIFIED_EXTERNAL_GATE"
      local_probe = $credentialMap
      probe_exit_code = $credential.exit_code
      note = "Configured means a local WinCred target is readable; no credential secret value is emitted. New-machine recreation still requires explicit local setup."
    }
    yuanta_certificate_reimport = [ordered]@{
      status = "UNVERIFIED_EXTERNAL_GATE"
      store_access = $certMap["store_access"]
      certificate_store_nonempty = $certMap["certificate_store_nonempty"]
      certificate_store_has_unexpired = $certMap["certificate_store_has_unexpired"]
      yuanta_certificate_identity_verified = $false
      yuanta_official_signature_verified = $false
      note = "Generic Windows store state is not Yuanta identity proof. Official Yuanta certificate-center signature verification is required."
    }
    yuanta_com_registration_new_machine = [ordered]@{
      status = "UNVERIFIED_EXTERNAL_GATE"
      local_read_only_com_ready_for_auth = $comReady
      probe_exit_code = $com.exit_code
      note = "READY_FOR_AUTH is only a read-only local COM/sidecar smoke. It does not certify registration on a different machine."
    }
  }
}

if ($Json) {
  $result | ConvertTo-Json -Depth 8
} else {
  $result.gates.GetEnumerator() | ForEach-Object { Write-Host ("{0}: {1}" -f $_.Key, $_.Value.status) }
  Write-Host "RESULT: EXTERNAL_GATES_REMAIN_UNVERIFIED"
}
exit 0
