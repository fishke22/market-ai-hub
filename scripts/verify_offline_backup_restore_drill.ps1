param(
    [switch]$KeepArtifacts
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) {
    throw "repo Python not found: $Python"
}

function Assert-RobocopySuccess([string]$Step) {
    if ($LASTEXITCODE -gt 7) {
        throw "$Step failed with robocopy exit code $LASTEXITCODE"
    }
}

$scratch = Join-Path $env:TEMP ("market_ai_hub_restore_drill_" + [guid]::NewGuid().ToString("N"))
$backupBase = Join-Path $scratch "backup base"
$restoreRoot = Join-Path $scratch "restore path with spaces"
New-Item -ItemType Directory -Force -Path $backupBase | Out-Null

try {
    Write-Output "RESTORE_DRILL_START"
    & (Join-Path $PSScriptRoot "create_offline_backup.ps1") -Destination $backupBase
    $backup = Get-ChildItem -LiteralPath $backupBase -Directory |
        Sort-Object LastWriteTimeUtc -Descending |
        Select-Object -First 1
    if (-not $backup) { throw "backup directory was not created" }

    & (Join-Path $PSScriptRoot "verify_offline_backup.ps1") -BackupRoot $backup.FullName

    $source = Join-Path $backup.FullName "source"
    New-Item -ItemType Directory -Force -Path $restoreRoot | Out-Null
    robocopy $source $restoreRoot /E /NFL /NDL /NJH /NJS | Out-Null
    Assert-RobocopySuccess "restore copy"

    foreach ($excluded in @(".venv", ".venv-fincast", ".venv-yuanta-futures-x86", "data", "models", ".git")) {
        if (Test-Path -LiteralPath (Join-Path $restoreRoot $excluded)) {
            throw "excluded directory was restored: $excluded"
        }
    }
    $currentBuild = & $Python -B -c "from market_ai_hub.services.build_info import build_fingerprint; print(build_fingerprint()['build_id'])"
    if ($LASTEXITCODE -ne 0) { throw "current build probe failed" }

    $oldPythonPath = $env:PYTHONPATH
    $env:PYTHONPATH = Join-Path $restoreRoot "src"
    Push-Location $restoreRoot
    try {
        $probe = & $Python -B -c "import pathlib, market_ai_hub; from market_ai_hub.services.build_info import build_fingerprint; print(pathlib.Path(market_ai_hub.__file__).resolve()); print(build_fingerprint()['build_id'])"
        if ($LASTEXITCODE -ne 0) { throw "restored source import probe failed" }
    } finally {
        Pop-Location
        $env:PYTHONPATH = $oldPythonPath
    }

    $modulePath = [string]$probe[0]
    $restoredBuild = [string]$probe[1]
    $restorePrefix = $restoreRoot.TrimEnd('\') + '\'
    if (-not $modulePath.StartsWith($restorePrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "restored import escaped restored source: $modulePath"
    }
    if ($restoredBuild -ne $currentBuild) {
        throw "restored build mismatch: current=$currentBuild restored=$restoredBuild"
    }
    Write-Output "RESTORE_DRILL_PASS"
    Write-Output "restored_module=$modulePath"
    Write-Output "build_id=$restoredBuild"
    Write-Output "scratch=$scratch"
} finally {
    if (-not $KeepArtifacts -and (Test-Path -LiteralPath $scratch)) {
        $fullScratch = [IO.Path]::GetFullPath($scratch)
        $nativeScratch = if ($fullScratch.StartsWith('\\')) { '\\?\UNC\' + $fullScratch.Substring(2) } else { '\\?\' + $fullScratch }
        [IO.Directory]::Delete($nativeScratch, $true)
    }
}
