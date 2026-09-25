param(
    [Parameter(Mandatory=$true)][string]$BackupRoot
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path -LiteralPath $BackupRoot).Path
$sumsPath = Join-Path $root "SHA256SUMS.txt"
if (-not (Test-Path -LiteralPath $sumsPath)) {
    throw "SHA256SUMS.txt not found: $root"
}

$required = @(
    "source\README.md",
    "source\pyproject.toml",
    "source\config\system_manifest.yaml",
    "source\scripts\reconstruct_verify.ps1"
)
foreach ($rel in $required) {
    if (-not (Test-Path -LiteralPath (Join-Path $root $rel))) {
        throw "required backup file missing: $rel"
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

$expected = @{}
$lineNo = 0
foreach ($raw in Get-Content -LiteralPath $sumsPath -Encoding UTF8) {
    $lineNo++
    $line = $raw.TrimStart([char]0xFEFF)
    if (-not $line) { continue }
    if ($line -notmatch '^([0-9A-Fa-f]{64})  (.+)$') {
        throw "invalid checksum line $lineNo"
    }
    $hash = $Matches[1].ToUpperInvariant()
    $rel = $Matches[2]
    if ($expected.ContainsKey($rel)) {
        throw "duplicate checksum entry: $rel"
    }
    $full = [IO.Path]::GetFullPath((Join-Path $root $rel))
    $prefix = $root.TrimEnd('\') + '\'
    if (-not $full.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "checksum path escapes backup root: $rel"
    }
    $nativeFull = if ($full.StartsWith('\\')) { '\\?\UNC\' + $full.Substring(2) } else { '\\?\' + $full }
    if (-not [IO.File]::Exists($nativeFull)) {
        throw "checksummed file missing: $rel"
    }
    $actual = (Get-Sha256Hex $full).ToUpperInvariant()
    if ($actual -ne $hash) {
        throw "checksum mismatch: $rel"
    }
    $expected[$rel] = $hash
}
$actualFiles = Get-ChildItem -LiteralPath $root -Recurse -File |
    Where-Object { $_.FullName -ne $sumsPath } |
    ForEach-Object { $_.FullName.Substring($root.Length + 1) }

$extra = @($actualFiles | Where-Object { -not $expected.ContainsKey($_) })
if ($extra.Count -gt 0) {
    throw "unchecksummed files found: $($extra -join ', ')"
}

if ($expected.Count -eq 0) {
    throw "checksum manifest is empty"
}

Write-Output "BACKUP_VERIFY_PASS"
Write-Output "backup_root=$root"
Write-Output "verified_files=$($expected.Count)"
