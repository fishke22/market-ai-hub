"""Phase 2Y-A — OrderApiExposureGuard（靜態掃描，禁止 order/trade/broker action 暴露）。"""
from __future__ import annotations

import re
from pathlib import Path


def _project_root() -> Path:
    # 不 import config.settings（其 import yaml/dotenv，會破壞 x86 sidecar minimal 依賴）
    return Path(__file__).resolve().parents[4]

# 禁止實作的下單/trading method pattern
ORDER_PATTERNS = [
    r"\bSendStockOrder\b", r"\bSendFutureOrder\b", r"\bSendFutureCombined\b",
    r"\bSendFutureApart\b", r"\bCancelOrder\b", r"\bModifyOrder\b",
    r"\bplace_order\b", r"\bbroker_order\b", r"\bdef\s+send_order\b",
    r"\bdef\s+cancel\b", r"\bdef\s+modify\b", r"\bSendOrder\b",
]

SCAN_PATHS = [
    "src/market_ai_hub/integrations/yuanta",
    "src/market_ai_hub/mcp/server.py",
    "skills",
    "examples",
]


class OrderApiExposureGuard:
    """掃描 integrations/yuanta、mcp、skills、examples；發現 order/trade method → FAIL。"""

    def __init__(self, root: Path | None = None) -> None:
        self.root = root or _project_root()

    def scan(self) -> dict:
        findings: list[dict] = []
        for rel in SCAN_PATHS:
            base = self.root / rel
            if not base.exists():
                continue
            files = base.rglob("*.py") if base.is_dir() and rel.endswith(".py") is False else ([base] if base.is_file() else base.rglob("*"))
            for f in files:
                if f.is_file() and f.suffix in (".py", ".md"):
                    try:
                        text = f.read_text(encoding="utf-8", errors="replace")
                    except Exception:
                        continue
                    for pat in ORDER_PATTERNS:
                        for m in re.finditer(pat, text):
                            # 允許文件中提到 "NO ORDER" 等文字，但不得是實作 def
                            line = text[:m.start()].count("\n") + 1
                            context = text.splitlines()[line - 1] if 0 <= line - 1 < len(text.splitlines()) else ""
                            if re.search(r"\bdef\s+\w*" + pat.replace(r"\b", "").split("def ")[-1] + r"\w*\s*\(", context) or pat.startswith(r"\bdef"):
                                findings.append({"path": str(f.relative_to(self.root)), "line": line, "pattern": pat})
        return {"gate": "FAIL" if findings else "PASS", "findings": findings}
