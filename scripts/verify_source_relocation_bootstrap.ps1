param(
    [string]$Destination,
    [string]$PythonExe,
    [switch]$KeepCopy
)

$ErrorActionPreference = "Stop"

function Assert-NativeSuccess($Step) {
    if ($LASTEXITCODE -ne 0) { throw "$Step failed (exit $LASTEXITCODE)" }
}

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $Destination) {
    $Destination = Join-Path ([System.IO.Path]::GetTempPath()) ("MARKET_AI_HUB relocation 測試\" + [guid]::NewGuid().ToString("N"))
}
if (Test-Path -LiteralPath $Destination) {
    throw "Destination already exists; refusing to overwrite: $Destination"
}
New-Item -ItemType Directory -Path $Destination -Force | Out-Null
$Destination = (Resolve-Path -LiteralPath $Destination).Path

try {
    Write-Host "== copy tracked source =="
    $tracked = & git -C $Root ls-files
    Assert-NativeSuccess "git ls-files"
    foreach ($relative in $tracked) {
        if (-not $relative) { continue }
        $source = Join-Path $Root $relative
        $target = Join-Path $Destination $relative
        $parent = Split-Path -Parent $target
        if ($parent) { New-Item -ItemType Directory -Path $parent -Force | Out-Null }
        Copy-Item -LiteralPath $source -Destination $target -Force
    }

    Write-Host "== bootstrap relocated venv from non-repo cwd =="
    $setup = Join-Path $Destination "scripts\setup_windows.ps1"
    Push-Location ([System.IO.Path]::GetTempPath())
    try {
        if ($PythonExe) {
            & powershell -NoProfile -ExecutionPolicy Bypass -File $setup -BootstrapOnly -PythonExe $PythonExe
        } else {
            & powershell -NoProfile -ExecutionPolicy Bypass -File $setup -BootstrapOnly
        }
        Assert-NativeSuccess "relocated bootstrap"
    } finally {
        Pop-Location
    }

    $newPython = Join-Path $Destination ".venv\Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $newPython)) { throw "Relocated venv python missing: $newPython" }

    Write-Host "== probe relocated source identity =="
    $oldPythonPath = $env:PYTHONPATH
    $oldOriginalRoot = $env:MARKET_AI_RELOCATION_ORIGINAL_ROOT
    try {
        $env:PYTHONPATH = Join-Path $Destination "src"
        $env:MARKET_AI_RELOCATION_ORIGINAL_ROOT = $Root
        $json = & $newPython -B -c "import json,os,sys,struct; from pathlib import Path; from market_ai_hub.services.build_info import build_fingerprint; fp=build_fingerprint(); old=str(Path(os.environ['MARKET_AI_RELOCATION_ORIGINAL_ROOT']).resolve()).lower(); print(json.dumps({'exe':sys.executable,'prefix':sys.prefix,'bits':struct.calcsize('P')*8,'version':sys.version.split()[0],'source_root':fp['source_root'],'build_id':fp['build_id'],'old_repo_in_syspath':any(str(p).lower().startswith(old) for p in sys.path)},ensure_ascii=False))"
        Assert-NativeSuccess "relocated source probe"
    } finally {
        $env:PYTHONPATH = $oldPythonPath
        $env:MARKET_AI_RELOCATION_ORIGINAL_ROOT = $oldOriginalRoot
    }

    $probe = $json | ConvertFrom-Json
    $expectedPrefix = (Resolve-Path -LiteralPath (Join-Path $Destination ".venv")).Path
    if ($probe.bits -ne 64) { throw "Relocated venv is not 64-bit" }
    if ($probe.version -notmatch '^3\.(11|12)\.') { throw "Relocated venv uses unsupported Python $($probe.version)" }
    if ([System.IO.Path]::GetFullPath([string]$probe.prefix).TrimEnd("\") -ne $expectedPrefix.TrimEnd("\")) {
        throw "Relocated venv prefix mismatch: $($probe.prefix)"
    }
    if ([System.IO.Path]::GetFullPath([string]$probe.source_root).TrimEnd("\") -ne $Destination.TrimEnd("\")) {
        throw "Relocated source_root mismatch: $($probe.source_root)"
    }
    if ($probe.old_repo_in_syspath) { throw "Relocated process still depends on original repo path" }
    if ([string]$probe.build_id -notmatch '^[0-9a-f]{16}$') { throw "Relocated build_id invalid: $($probe.build_id)" }

    Write-Host $json
    Write-Host "RESULT: SOURCE_RELOCATION_BOOTSTRAP_PASS"
} finally {
    if (-not $KeepCopy -and (Test-Path -LiteralPath $Destination)) {
        Remove-Item -LiteralPath $Destination -Recurse -Force
    } elseif ($KeepCopy) {
        Write-Host "kept_copy: $Destination"
    }
}
