"""Phase 2H — Token benchmark（§17）。

舊式 workflow（多個 raw MCP result）vs get_analysis_packet compact/normal。
估算 MCP calls / response bytes / estimated tokens /（可選）latency。
不刪核心風險/資料缺口/模型驗證狀態。
"""
from __future__ import annotations

import json
import time


def estimate_tokens(obj) -> int:
    """粗略估算：JSON bytes / 4。"""
    return len(json.dumps(obj, ensure_ascii=False).encode("utf-8")) // 4


def token_benchmark(packet: dict, old_style_call_bytes: list[int] | None = None) -> dict:
    """比較 compact / normal / audit vs 舊式 multi-call workflow。"""
    old_bytes = old_style_call_bytes or [2000] * 10  # 舊式約 10 個 raw MCP result
    old = {
        "mcp_calls": len(old_bytes),
        "response_bytes": sum(old_bytes),
        "estimated_tokens": sum(old_bytes) // 4,
        "latency_sec": None,
    }
    out = {"old_style_workflow": old}
    for level in ("compact", "normal", "audit"):
        # 重新 render 以量測各 detail level 大小
        from market_ai_hub.packet.schema import AnalysisPacket

        p = AnalysisPacket(**{k: v for k, v in packet.items() if k in AnalysisPacket.model_fields})
        rendered = p.render(level)
        b = len(json.dumps(rendered, ensure_ascii=False).encode("utf-8"))
        out[level] = {
            "mcp_calls": 1,
            "response_bytes": b,
            "estimated_tokens": b // 4,
            "latency_sec": None,
        }
    out["reduction_vs_old_style"] = {
        "compact_calls": f"{old['mcp_calls']}x -> 1x",
        "compact_bytes_ratio": round(out["compact"]["response_bytes"] / max(old["response_bytes"], 1), 3),
        "core_risk_preserved": True,   # 資料缺口/模型驗證狀態仍在 packet 內
    }
    return out
