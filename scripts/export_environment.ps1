# MARKET_AI_HUB — 環境匯出腳本
# 用法：powershell -ExecutionPolicy Bypass -File scripts\export_environment.ps1
# 輸出到 environment_export/（預設不 commit；見 .gitignore）。

$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root
$out = Join-Path $Root "environment_export"
New-Item -ItemType Directory -Force -Path $out | Out-Null
$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$file = Join-Path $out "environment_$stamp.txt"
$venvPy = Join-Path $Root ".venv\Scripts\python.exe"

"MARKET_AI_HUB environment export" | Out-File $file -Encoding UTF8
"date: $(Get-Date -Format o)" | Out-File $file -Append -Encoding UTF8
"" | Out-File $file -Append -Encoding UTF8

"== Python ==" | Out-File $file -Append -Encoding UTF8
& $venvPy -c "import sys,platform; print(sys.version); print('arch', platform.machine())" | Out-File $file -Append -Encoding UTF8

"`n== OS ==" | Out-File $file -Append -Encoding UTF8
[System.Environment]::OSVersion.VersionString | Out-File $file -Append -Encoding UTF8

"`n== GPU / driver ==" | Out-File $file -Append -Encoding UTF8
try { nvidia-smi --query-gpu=name,driver_version,memory.total --format=csv,noheader | Out-File $file -Append -Encoding UTF8 } catch { "nvidia-smi unavailable" | Out-File $file -Append -Encoding UTF8 }

"`n== Torch / CUDA ==" | Out-File $file -Append -Encoding UTF8
& $venvPy -c "import torch; print('torch', torch.__version__); print('cuda_available', torch.cuda.is_available()); print('cuda', torch.version.cuda)" 2>&1 | Out-File $file -Append -Encoding UTF8

"`n== build_id ==" | Out-File $file -Append -Encoding UTF8
& $venvPy -c "from market_ai_hub.services.build_info import build_fingerprint; import json; print(json.dumps(build_fingerprint(), indent=2))" 2>&1 | Out-File $file -Append -Encoding UTF8

"`n== model revisions (cache) ==" | Out-File $file -Append -Encoding UTF8
& $venvPy scripts\download_models.py --check 2>&1 | Out-File $file -Append -Encoding UTF8

"`n== pip freeze ==" | Out-File $file -Append -Encoding UTF8
& $venvPy -m pip freeze 2>&1 | Out-File $file -Append -Encoding UTF8

Write-Host "exported -> $file" -ForegroundColor Green
Write-Host "注意：environment_export/ 預設不 commit（含本機路徑）；如需分享請只分享 sanitized 版本。"
