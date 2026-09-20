"""Phase 2Q-F.2 — capture safe MCP structured payloads for the 5 UAT cases.

只抓 safe MCP structured payload（health/packet/gates），不得抓 Cherry private conversation /
credential / account / token。目的：回答錯誤時比較「MCP payload 正確 vs LLM 解讀錯」。

用法：python scripts/capture_uat_payloads.py [--out <dir>]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _capture() -> dict:
    from market_ai_hub.mcp import server as s
    from market_ai_hub.packet.builder import build_analysis_packet

    return {
        "health": {k: s.health_check()[k] for k in ("status", "chronos", "timesfm", "fincast")},
        "gates": {k: v.get("status") for k, v in s.get_research_gates().get("gates", {}).items()},
        "osaka_packet": build_analysis_packet(market="osaka", detail_level="compact", save_analysis=False),
        "taiwan_stock_packet": build_analysis_packet(market="taiwan", target="2330.TW", detail_level="compact", save_analysis=False),
        "taiwan_index_packet": build_analysis_packet(market="taiwan_index", target="TAIEX", detail_level="compact", save_analysis=False),
    }


def main() -> int:
    from market_ai_hub.config.runtime_paths import diagnostics_root

    out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[1] == "--out" else diagnostics_root() / "uat"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "uat_payloads.json"
    out.write_text(json.dumps(_capture(), ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"written -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
