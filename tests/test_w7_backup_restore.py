import hashlib
import os
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
BACKUP_SCRIPT = ROOT / "scripts" / "create_offline_backup.ps1"
VERIFY_SCRIPT = ROOT / "scripts" / "verify_offline_backup.ps1"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def _make_fixture(root: Path) -> Path:
    required = [
        "source/README.md",
        "source/pyproject.toml",
        "source/config/system_manifest.yaml",
        "source/scripts/reconstruct_verify.ps1",
    ]
    for rel in required:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(rel, encoding="utf-8")
    extra = root / "source" / "src" / "market_ai_hub" / "data" / "timezones.py"
    extra.parent.mkdir(parents=True, exist_ok=True)
    extra.write_text("UTC = 'UTC'\n", encoding="utf-8")
    lines = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        if path.name == "SHA256SUMS.txt":
            continue
        rel = path.relative_to(root).as_posix().replace("/", "\\")
        lines.append(f"{_sha256(path)}  {rel}")
    (root / "SHA256SUMS.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return extra


@pytest.mark.skipif(os.name != "nt", reason="PowerShell backup verifier")
def test_backup_excludes_only_top_level_runtime_dirs():
    text = BACKUP_SCRIPT.read_text(encoding="utf-8-sig")
    assert '(Join-Path $Root "data")' in text
    assert '(Join-Path $Root "models")' in text
    assert '(Join-Path $Root "reports")' in text
    assert '"__pycache__"' in text
    assert 'Assert-RobocopySuccess "source snapshot"' in text
    assert 'Assert-NativeSuccess "pip wheelhouse download"' in text


@pytest.mark.skipif(os.name != "nt", reason="PowerShell backup verifier")
def test_backup_verifier_detects_tamper_and_unchecksummed_files(tmp_path):
    tracked = _make_fixture(tmp_path)
    ok = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
         str(VERIFY_SCRIPT), "-BackupRoot", str(tmp_path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert "BACKUP_VERIFY_PASS" in ok.stdout

    tracked.write_text("tampered\n", encoding="utf-8")
    bad = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
         str(VERIFY_SCRIPT), "-BackupRoot", str(tmp_path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert bad.returncode != 0
    assert "checksum mismatch" in (bad.stdout + bad.stderr)


    tracked.write_text("UTC = 'UTC'\n", encoding="utf-8")
    (tmp_path / "untracked.txt").write_text("extra", encoding="utf-8")
    extra = subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
         str(VERIFY_SCRIPT), "-BackupRoot", str(tmp_path)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert extra.returncode != 0
    assert "unchecksummed files found" in (extra.stdout + extra.stderr)
