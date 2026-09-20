"""Phase 2Y-A — Yuanta secret scan（只顯示 path + rule + masked match，不打印秘密）。"""
from __future__ import annotations

import re
from pathlib import Path

from market_ai_hub.config.settings import project_root

# 偵測規則（pattern, rule name）
RULES = [
    (r"[A-Z]\d{9,}", "yuanta_account_like"),            # 大寫字母 + 9+ 數字（元大帳號近似）
    (r"(?i)(password|passwd|pwd)\s*=\s*['\"][^'\"]{3,}", "password_assignment"),
    (r"(?i)investor\s*id\s*[:=]", "investor_id"),
    (r"-----BEGIN (RSA |EC |ENCRYPTED )?PRIVATE KEY-----", "private_key"),
    (r"\.pfx\b", "pfx_reference"),
    (r"(?i)certificate\s*=\s*['\"][^'\"]{3,}", "certificate_assignment"),
]

SCAN_DIRS = ["src", "tests", "docs", "examples", "scripts", "skills"]


def scan(root: Path | None = None) -> list[dict]:
    root = root or project_root()
    findings: list[dict] = []
    for rel in SCAN_DIRS:
        base = root / rel
        if not base.exists():
            continue
        for f in base.rglob("*"):
            if not f.is_file() or f.suffix not in (".py", ".md", ".json", ".yaml", ".yml", ".txt", ".example"):
                continue
            try:
                text = f.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            for pat, rule in RULES:
                for m in re.finditer(pat, text):
                    findings.append({
                        "path": str(f.relative_to(root)),
                        "rule": rule,
                        "masked": mask(m.group(0)),
                    })
    return findings


def mask(s: str) -> str:
    if len(s) <= 6:
        return "*" * len(s)
    return s[:3] + "*" * (len(s) - 6) + s[-3:]


def report(findings: list[dict]) -> str:
    if not findings:
        return "PASS: no secret patterns found"
    lines = ["FINDINGS (path | rule | masked):"]
    for f in findings:
        lines.append(f"  {f['path']} | {f['rule']} | {f['masked']}")
    return "\n".join(lines)
