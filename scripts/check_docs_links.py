"""Phase 2Q-E — check relative markdown links in primary docs（README/docs/research index）。

掃 README / docs/README.md / research/README.md 等 primary docs 的 relative markdown links。
不存在 → FAIL。external URL 與 # anchor 不檢查。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PRIMARY_DOCS = [
    "README.md",
    "docs/README.md",
    "research/README.md",
    "research/phase2/README.md",
    "research/releases/README.md",
    "research/history/v1/README.md",
    "docs/reference/current-status.md",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
]

LINK_RE = re.compile(r"\]\(([^)]+)\)")


def _check(doc: str) -> list[str]:
    p = ROOT / doc
    if not p.exists():
        return [f"{doc}: MISSING FILE"]
    text = p.read_text(encoding="utf-8")
    broken = []
    for m in LINK_RE.finditer(text):
        target = m.group(1).strip()
        if not target or target.startswith(("http://", "https://", "#", "mailto:")):
            continue
        path = target.split("#")[0].split("?")[0]
        if not path:
            continue
        resolved = (p.parent / path).resolve()
        if not resolved.exists():
            broken.append(f"{doc}: {target}")
    return broken


def main() -> int:
    broken = []
    for doc in PRIMARY_DOCS:
        broken.extend(_check(doc))
    if broken:
        for b in broken:
            print("BROKEN", b)
        return 1
    print(f"OK: {len(PRIMARY_DOCS)} primary docs, no broken relative links")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
