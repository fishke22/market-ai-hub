# MARKET_AI_HUB — check 元大期貨 COM（唯讀，不登入、不需密碼）
$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
$sidePy = Join-Path $Root ".venv-yuanta-futures-x86\Scripts\python.exe"

if (-not (Test-Path $sidePy)) { Write-Host "RESULT: SIDECAR_NOT_SETUP (run setup_yuanta_futures_x86.ps1)"; exit 1 }

$env:PYTHONPATH = Join-Path $Root "src"

$bits = & $sidePy -c "import struct; print(struct.calcsize('P')*8)" 2>$null
Write-Host "bitness: $bits (expect 32)"

$deps = & $sidePy -c "import comtypes, win32cred, pythoncom, win32gui; print('ok')" 2>$null
Write-Host "comtypes/pywin32: $deps"

$reg = & $sidePy -c "import winreg; k=winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, 'CLSID\{8E7FB42A-1137-467E-98C6-830C9B02EA82}\InprocServer32', 0, winreg.KEY_READ|winreg.KEY_WOW64_32KEY); print(winreg.QueryValue(k, None))" 2>$null
Write-Host "OCX InprocServer32: $reg"

$imp = & $sidePy -c "import sys; sys.path.insert(0, r'D:\MARKET_AI_HUB\src'); import market_ai_hub.integrations.yuanta.futures_com; print('ok')" 2>$null
Write-Host "sidecar import: $imp"

$sta = & $sidePy -m market_ai_hub.integrations.yuanta.futures_com_smoke 2>$null
Write-Host "STA/ActiveX/event-sink smoke: $sta"

if ($bits -eq "32" -and $deps -eq "ok" -and $reg -like "*.ocx" -and $imp -eq "ok" -and $sta -eq "SMOKE_OK") {
  Write-Host "RESULT: READY_FOR_AUTH"
} else {
  Write-Host "RESULT: BLOCKED (see above)"
}
