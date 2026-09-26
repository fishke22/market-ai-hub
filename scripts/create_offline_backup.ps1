# MARKET_AI_HUB — 離線備份腳本（可選，不會自動執行）
#
# 用途：GitHub 不適合放模型 weights / 大量 wheels / 市場資料。
# 本腳本把「本機合法擁有」的內容備份到使用者指定目錄，並產生 SHA256SUMS.txt。
#
# 用法：
#   powershell -ExecutionPolicy Bypass -File scripts\create_offline_backup.ps1 -Destination E:\MARKET_AI_BACKUP
#   ... -Destination E:\MARKET_AI_BACKUP -IncludePythonPackages
#   ... -Destination E:\MARKET_AI_BACKUP -IncludeModels
#
# ⚠️ 重要：本地私人備份 ≠ 公開重新散布。
#    若某第三方模型 license 不允許重新散布（如 TimesFM-3.0 非商業授權），
#    本備份僅供你自己在同一授權範圍內使用，禁止公開分享或上傳。

param(
    [Parameter(Mandatory=$true)][string]$Destination,
    [switch]$IncludePythonPackages,
    [switch]$IncludeModels
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Assert-NativeSuccess([string]$Step) {
    if ($LASTEXITCODE -ne 0) {
        throw "$Step failed with exit code $LASTEXITCODE"
    }
}

function Assert-RobocopySuccess([string]$Step) {
    if ($LASTEXITCODE -gt 7) {
        throw "$Step failed with robocopy exit code $LASTEXITCODE"
    }
}

function Get-Sha256Hex([string]$Path) {
    $full = [IO.Path]::GetFullPath($Path)
    $native = if ($full.StartsWith('\\')) { '\\?\UNC\' + $full.Substring(2) } else { '\\?\' + $full }
    $stream = [IO.File]::Open($native, [IO.FileMode]::Open, [IO.FileAccess]::Read, [IO.FileShare]::Read)
    try {
        $sha = [Security.Cryptography.SHA256]::Create()
        try { return ([BitConverter]::ToString($sha.ComputeHash($stream))).Replace('-', '') }
        finally { $sha.Dispose() }
    } finally { $stream.Dispose() }
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$dest = Join-Path $Destination "market_ai_hub_backup_$stamp"
New-Item -ItemType Directory -Force -Path $dest | Out-Null
Write-Host "=== MARKET_AI_HUB offline backup ===" -ForegroundColor Cyan
Write-Host "destination: $dest"

function Copy-ItemSafe($src, $dst) {
    if (Test-Path $src) { Copy-Item $src $dst -Recurse -Force; Write-Host "  + $src" }
}

# 1. Source snapshot（排除 gitignore 的內容）
Write-Host "[1/5] source snapshot"
$srcDst = Join-Path $dest "source"
New-Item -ItemType Directory -Force -Path $srcDst | Out-Null
$exclude = @(
    (Join-Path $Root ".venv"),
    (Join-Path $Root ".venv-fincast"),
    (Join-Path $Root ".venv-yuanta-futures-x86"),
    (Join-Path $Root "models"),
    (Join-Path $Root "logs"),
    (Join-Path $Root "reports"),
    (Join-Path $Root "data"),
    (Join-Path $Root ".pytest_cache"),
    (Join-Path $Root ".opencode"),
    (Join-Path $Root ".remediation_backup_20260919"),
    (Join-Path $Root "external"),
    (Join-Path $Root ".git"),
    "__pycache__"
)
robocopy $Root $srcDst /E /XD $exclude /XF "*.pyc" /NFL /NDL /NJH /NJS | Out-Null
Assert-RobocopySuccess "source snapshot"

# 2. Requirements / environment manifest
Write-Host "[2/5] requirements + environment manifest"
Copy-ItemSafe "requirements-runtime.txt" $dest
Copy-ItemSafe "requirements-dev.txt" $dest
Copy-ItemSafe "requirements-lock-windows-x64.txt" $dest
Copy-ItemSafe "config\model_manifest.yaml" $dest
Copy-ItemSafe "docs\environment" $dest
Copy-ItemSafe ".env.example" $dest

# 3. 可選：Python packages wheelhouse
if ($IncludePythonPackages) {
    Write-Host "[3/5] pip download wheelhouse（可能數 GB）"
    $wh = Join-Path $dest "wheelhouse"
    New-Item -ItemType Directory -Force -Path $wh | Out-Null
    & (Join-Path $Root ".venv\Scripts\python.exe") -m pip download -r requirements-lock-windows-x64.txt -d $wh
    Assert-NativeSuccess "pip wheelhouse download"
} else {
    Write-Host "[3/5] 略過 Python packages（-IncludePythonPackages 可啟用）"
}

# 4. 可選：本地模型 cache
if ($IncludeModels) {
    Write-Host "[4/5] 複製本地模型 cache（-IncludeModels）"
    $md = Join-Path $dest "model_cache"
    New-Item -ItemType Directory -Force -Path $md | Out-Null
    Copy-ItemSafe "models\cache" $md
    $hf = Join-Path $env:USERPROFILE ".cache\huggingface\hub"
    if (Test-Path $hf) {
        robocopy $hf (Join-Path $md "hf_hub") /E /NFL /NDL /NJH /NJS | Out-Null
        Assert-RobocopySuccess "HF hub cache backup"
        Write-Host "  + HF hub cache"
    }
    Write-Host "  ⚠️ 模型 weights 授權限制：本地備份僅供自用，禁止公開散布（見 THIRD_PARTY_NOTICES.md）"
} else {
    Write-Host "[4/5] 略過模型 cache（-IncludeModels 可啟用）"
}

# 5. SHA256SUMS.txt
Write-Host "[5/5] 產生 SHA256SUMS.txt"
$sums = Join-Path $dest "SHA256SUMS.txt"
Get-ChildItem $dest -Recurse -File | Where-Object { $_.Name -ne "SHA256SUMS.txt" } | ForEach-Object {
    $h = Get-Sha256Hex $_.FullName
    "$h  $($_.FullName.Substring($dest.Length+1))"
} | Set-Content -Encoding UTF8 $sums

Write-Host ""
Write-Host "備份完成：$dest" -ForegroundColor Green
Write-Host "驗證：Get-Content '$sums' 後逐一比對 SHA256。"
