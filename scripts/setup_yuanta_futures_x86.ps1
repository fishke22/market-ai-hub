# MARKET_AI_HUB — setup 元大期貨 x86 sidecar（clean clone 後自動重建，不登入、不需密碼）
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
$fail = 0

function Ok($c, $m) { if ($c) { Write-Host "  [OK]   $m" } else { Write-Host "  [FAIL] $m"; $script:fail++ } }

Write-Host "== 1. find 32-bit Python =="
$py32 = $null
foreach ($cand in @(
  "C:\Users\fishk\AppData\Local\Programs\Python\Python311-32\python.exe",
  "C:\Python311-32\python.exe"
)) {
  if (Test-Path $cand) { $py32 = $cand; break }
}
if (-not $py32) {
  $found = Get-Command py -ErrorAction SilentlyContinue
  if ($found) {
    $py32 = (& py -0p 2>$null | Select-String "32-bit" | Select-Object -First 1)
    if ($py32) { $py32 = $py32.ToString().Split(" ")[0] }
  }
}
if (-not $py32) { Write-Host "  [FAIL] 32-bit Python not found (install 32-bit Python 3.11)"; exit 1 }
Ok ($py32 -ne $null) "32-bit Python: $py32"

Write-Host "== 2. create .venv-yuanta-futures-x86 =="
$venv = Join-Path $Root ".venv-yuanta-futures-x86"
if (-not (Test-Path (Join-Path $venv "Scripts\python.exe"))) {
  & $py32 -m venv $venv 2>&1 | Out-Null
}
$sidePy = Join-Path $venv "Scripts\python.exe"
Ok (Test-Path $sidePy) "sidecar python exists"

Write-Host "== 3. install minimal deps =="
& $sidePy -m pip install --quiet comtypes pywin32 2>&1 | Out-Null

Write-Host "== 4. verify bitness + deps =="
$bits = & $sidePy -c "import struct; print(struct.calcsize('P')*8)" 2>$null
Ok ($bits -eq 32) "sidecar bitness = $bits (expect 32)"
$deps = & $sidePy -c "import comtypes, win32cred, pythoncom, win32gui; print('ok')" 2>$null
Ok ($deps -eq "ok") "comtypes + pywin32 importable"

Write-Host "== 5. verify OCX registration =="
$reg = & $sidePy -c "import winreg; k=winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r'CLSID\{8E7FB42A-1137-467E-98C6-830C9B02EA82}\InprocServer32', 0, winreg.KEY_READ|winreg.KEY_WOW64_32KEY); print(winreg.QueryValue(k, None))" 2>$null
Ok ($reg -like "*.ocx") "OCX registered: $reg"

Write-Host "== 6. sidecar import smoke (no login) =="
$imp = & $sidePy -c "import sys; sys.path.insert(0, r'$Root\src'); import market_ai_hub.integrations.yuanta.futures_com as m; print('ok')" 2>$null
Ok ($imp -eq "ok") "futures_com importable in sidecar"

Write-Host ""
if ($fail -gt 0) { Write-Host "RESULT: FAIL ($fail)" ; exit 1 }
Write-Host "RESULT: READY_FOR_AUTH (no login, no password)"
