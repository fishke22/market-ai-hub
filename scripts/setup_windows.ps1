# MARKET_AI_HUB — Windows 安裝腳本
# 用法（PowerShell，於 repo 根目錄）：
#   powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1
#   powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1 -WithDev
#
# 本腳本不會安裝任何來路不明的 binary；缺少系統依賴時會顯示官方下載位置。

param(
    [switch]$WithDev,
    [switch]$SkipDeps
)

$ErrorActionPreference = "Stop"
function Assert-NativeSuccess($Step) {
    if ($LASTEXITCODE -ne 0) { throw "$Step failed (exit $LASTEXITCODE)" }
}
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "=== MARKET_AI_HUB setup (Windows) ===" -ForegroundColor Cyan
Write-Host "repo: $Root"

# 1. 檢查 Python
$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    Write-Host "[FAIL] 找不到 Python。請至官方安裝 Python 3.12 x64：https://www.python.org/downloads/windows/" -ForegroundColor Red
    exit 1
}
$ver = (& python -c "import sys;print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')").Trim()
Assert-NativeSuccess "Python version"
$arch = (& python -c "import platform;print(platform.machine())").Trim()
Assert-NativeSuccess "Python architecture"
Write-Host "[OK] Python $ver ($arch)"
if ($ver -notmatch '^3\.(11|12)\.') {
    Write-Host "[WARN] 建議 Python 3.11 或 3.12（V1 Freeze 為 3.12.13）。3.14 可能與 AI/ML 套件不相容。" -ForegroundColor Yellow
}
if ($arch -ne "AMD64") {
    Write-Host "[WARN] 偵測到非 x64 架構（$arch）。V1 Freeze 為 x64。" -ForegroundColor Yellow
}

# 2. 建立 .venv
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "[..] 建立 .venv"
    & python -m venv .venv
    Assert-NativeSuccess "Create venv"
} else {
    Write-Host "[OK] .venv 已存在"
}
$venvPy = Join-Path $Root ".venv\Scripts\python.exe"

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
