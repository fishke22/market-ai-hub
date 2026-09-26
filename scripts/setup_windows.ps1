# MARKET_AI_HUB — Windows 安裝腳本
# 用法（PowerShell，於 repo 根目錄）：
#   powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1 -WithDev
#
# 本腳本不會安裝任何來路不明的 binary；缺少系統依賴時會顯示官方下載位置。

param(
    [switch]$WithDev,
    [switch]$SkipDeps,
    [switch]$BootstrapOnly,
    [string]$PythonExe
)

$ErrorActionPreference = "Stop"
function Assert-NativeSuccess($Step) {
    if ($LASTEXITCODE -ne 0) { throw "$Step failed (exit $LASTEXITCODE)" }
}

function Get-PythonInfo([string]$Exe) {
    try {
        $json = & $Exe -c "import json,sys,struct; print(json.dumps({'executable':sys.executable,'version':f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}','major':sys.version_info.major,'minor':sys.version_info.minor,'bits':struct.calcsize('P')*8}))" 2>$null
        if ($LASTEXITCODE -ne 0 -or -not $json) { return $null }
        return ($json | ConvertFrom-Json)
    } catch {
        return $null
    }
}

function Resolve-SupportedPython([string]$Requested) {
    if ($Requested) {
        if (-not (Test-Path -LiteralPath $Requested)) { throw "Configured Python not found: $Requested" }
        $resolved = (Resolve-Path -LiteralPath $Requested).Path
        $info = Get-PythonInfo $resolved
        if (-not $info) { throw "Configured Python is not executable: $resolved" }
        if ($info.major -ne 3 -or $info.minor -notin @(11, 12) -or $info.bits -ne 64) {
            throw "Configured Python must be CPython 3.11/3.12 64-bit; got $($info.version) $($info.bits)-bit at $resolved"
        }
        return $info
    }

    $launcher = Get-Command py -ErrorAction SilentlyContinue
    if ($launcher) {
        $entries = & py -0p 2>$null
        foreach ($preferredMinor in @(12, 11)) {
            foreach ($line in $entries) {
                if ($line -notmatch '^\s*(?<selector>-V:\S+)') { continue }
                $selector = $Matches.selector
                $json = & py $selector -c "import json,sys,struct; print(json.dumps({'executable':sys.executable,'version':f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}','major':sys.version_info.major,'minor':sys.version_info.minor,'bits':struct.calcsize('P')*8}))" 2>$null
                if ($LASTEXITCODE -ne 0 -or -not $json) { continue }
                $info = $json | ConvertFrom-Json
                if ($info.major -eq 3 -and $info.minor -eq $preferredMinor -and $info.bits -eq 64) { return $info }
            }
        }
    }

    $pathPython = Get-Command python -ErrorAction SilentlyContinue
    if ($pathPython) {
        $info = Get-PythonInfo $pathPython.Source
        if ($info -and $info.major -eq 3 -and $info.minor -in @(11, 12) -and $info.bits -eq 64) { return $info }
    }

    throw "No supported Python found. Install Python 3.12 x64 from python.org or pass -PythonExe <path>. Automatic installation is intentionally disabled."
}

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "=== MARKET_AI_HUB setup (Windows) ===" -ForegroundColor Cyan
Write-Host "repo: $Root"

# 1. 選擇並驗證 Python（只接受 3.11/3.12 64-bit）
$pyInfo = Resolve-SupportedPython $PythonExe
$pythonPath = [string]$pyInfo.executable
Write-Host "[OK] Python $($pyInfo.version) ($($pyInfo.bits)-bit): $pythonPath"

# 2. 建立 .venv
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "[..] 建立 .venv"
    & $pythonPath -m venv .venv
    Assert-NativeSuccess "Create venv"
} else {
    Write-Host "[OK] .venv 已存在"
}
$venvPy = Join-Path $Root ".venv\Scripts\python.exe"
$venvBits = (& $venvPy -c "import struct; print(struct.calcsize('P')*8)").Trim()
Assert-NativeSuccess "Venv architecture"
$venvVersion = (& $venvPy -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')").Trim()
Assert-NativeSuccess "Venv version"
if ($venvBits -ne "64" -or $venvVersion -notmatch '^3\.(11|12)\.') {
    throw "Existing .venv is incompatible: Python $venvVersion $venvBits-bit. Rebuild it with a supported 64-bit interpreter."
}
if ($BootstrapOnly) {
    Write-Host "RESULT: BOOTSTRAP_ONLY_PASS (no dependency install performed)"
    exit 0
}

# 3. 更新 pip / setuptools / wheel
Write-Host "[..] 更新 pip / setuptools / wheel"
& $venvPy -m pip install --upgrade pip setuptools wheel
Assert-NativeSuccess "Install packaging tools"

# 4. 安裝 runtime dependencies
if (-not $SkipDeps) {
    Write-Host "[..] 安裝 runtime dependencies（requirements-runtime.txt）"
    & $venvPy -m pip install -r requirements-runtime.txt
    Assert-NativeSuccess "Install runtime dependencies"
    Write-Host "[..] 以 editable 模式安裝本專案"
    & $venvPy -m pip install -e .
    Assert-NativeSuccess "Install project"
    if ($WithDev) {
        Write-Host "[..] 安裝 dev dependencies（requirements-dev.txt）"
        & $venvPy -m pip install -r requirements-dev.txt
        Assert-NativeSuccess "Install development dependencies"
    }
}

# 5. 檢查 Torch / CUDA
Write-Host "[..] 檢查 Torch / CUDA"
& $venvPy -c "import torch; print('torch', torch.__version__, 'cuda_available', torch.cuda.is_available()); print('gpu', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU only')"
Assert-NativeSuccess "Torch import"
Write-Host "    註：若 cuda_available=False 而你有 NVIDIA GPU，請改裝 CUDA wheel："
Write-Host "        .venv\Scripts\python.exe -m pip install torch==2.14.0 --index-url https://download.pytorch.org/whl/cu130"

# 6. 檢查 market-ai import
Write-Host "[..] 檢查 market_ai_hub import"
& $venvPy -c "import market_ai_hub; from market_ai_hub.services.build_info import build_fingerprint; print('build_id', build_fingerprint()['build_id'])"
Assert-NativeSuccess "Project import"

# 7. 提醒下載模型
Write-Host "[..] 檢查模型"
& $venvPy scripts\download_models.py --check
Assert-NativeSuccess "Model check"

Write-Host ""
Write-Host "=== 安裝完成 ===" -ForegroundColor Green
Write-Host "下一步："
Write-Host "  1) 下載模型：.venv\Scripts\python.exe scripts\download_models.py --download"
Write-Host "  2) 驗證安裝：powershell -ExecutionPolicy Bypass -File scripts\verify_install.ps1"
Write-Host "  3) 設定 Cherry Studio：docs\CHERRY_STUDIO_SETUP.md"
Write-Host ""
Write-Host "提醒：本系統為研究用途，無券商登入與自動下單。"
