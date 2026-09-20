"""Phase 2Q-B — secret / privacy audit（§22）。只掃 git-tracked 檔案，避免 venv 誤報。"""
from __future__ import annotations

import pathlib
import re
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[1]

PATTERNS = [
    re.compile(r"(?i)(password|passwd|pwd)\s*[:=]\s*[\"'][^\"']{4,}"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"(?i)(api[_-]?key|apikey|client_secret)\s*[:=]\s*[\"'][A-Za-z0-9._-]{12,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._-]{20,}"),
    re.compile(r"(?i)(investorid|brokerid)\s*[:=]\s*[\"']?[A-Z0-9]{6,}"),
]

# 已知測試 fixture / 範例假值（非真 secret）
ALLOWED = {"hunter2", "FAKE_PASSWORD", "FAKE_USER", "REAL123456", "INV-1"}


def tracked_files() -> list[str]:
    r = subprocess.run(["git", "ls-files"], cwd=str(ROOT), capture_output=True, text=True)
    return r.stdout.splitlines()


def scan() -> list[tuple[str, int, str]]:
    hits = []
    for rel in tracked_files():
        p = ROOT / rel
        if not p.exists() or p.stat().st_size > 2_000_000:
            continue
        try:
            txt = p.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        for pat in PATTERNS:
            for m in pat.finditer(txt):
                val = m.group(0)
                if any(a in val for a in ALLOWED):
                    continue
                line = txt[: m.start()].count("\n") + 1
                hits.append((rel, line, val[:60]))
    return hits


if __name__ == "__main__":
    hits = scan()
    print(f"tracked-file real-secret hits: {len(hits)}")
    for h in hits[:60]:
        print(h)
