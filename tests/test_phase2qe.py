"""Phase 2Q-E — repository professionalization tests（root allowlist + doc style）。"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, "src")
ROOT = Path(__file__).resolve().parents[1]

ALLOWED_ROOT_FILES = {
    "README.md", "LICENSE", "SECURITY.md", "DISCLAIMER.md", "THIRD_PARTY_NOTICES.md",
    "CHANGELOG.md", "CONTRIBUTING.md", "pyproject.toml", "AGENTS.md",
    "requirements-runtime.txt", "requirements-dev.txt", "requirements-lock-windows-x64.txt",
    ".env.example", ".gitattributes", ".gitignore",
}

ALLOWED_ROOT_DIRS = {
    ".github", "config", "docs", "research", "examples", "external", "scripts",
    "skills", "cherry_skills", "src", "tests", "vendor",
    "data",  # 預設 DATA_ROOT（僅 .gitkeep tracked，runtime data 皆 gitignored）
}


def _root_tracked():
    out = subprocess.run(["git", "-C", str(ROOT), "ls-files"], capture_output=True, text=True).stdout.splitlines()
    root_entries = set()
    for f in out:
        top = f.split("/")[0]
        root_entries.add(top)
    return root_entries


def test_root_allowlist():
    entries = _root_tracked()
    files = {e for e in entries if (ROOT / e).is_file()}
    dirs = entries - files
    unexpected_files = files - ALLOWED_ROOT_FILES
    unexpected_dirs = dirs - ALLOWED_ROOT_DIRS
    assert not unexpected_files, f"unexpected root files: {sorted(unexpected_files)}"
    assert not unexpected_dirs, f"unexpected root dirs: {sorted(unexpected_dirs)}"


def test_root_file_count_reasonable():
    entries = _root_tracked()
    files = [e for e in entries if (ROOT / e).is_file()]
    assert len(files) <= 25, f"too many root files: {len(files)}"


def test_primary_docs_professional_style():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    # primary README 不得出現幼稚化/宣傳式語氣
    for bad in ("小白", "BEGINNER", "必勝", "最強", "最準", "賺錢"):
        assert bad not in readme, f"unprofessional term in README: {bad}"


def test_three_families_in_readme():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    for fam in ("OSAKA_MICRO", "TAIWAN_STOCK", "TAIWAN_INDEX"):
        assert fam in readme, f"missing family in README: {fam}"
