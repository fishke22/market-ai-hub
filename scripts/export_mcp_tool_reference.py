"""Phase 2I-B — 從 runtime introspection 輸出 MCP tool reference。

用法：python scripts/export_mcp_tool_reference.py [--out docs/MCP_TOOL_REFERENCE.md]
禁止手寫與 runtime 不一致的假清單。
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


async def collect() -> list[dict]:
    from market_ai_hub.mcp.server import mcp

    tools = await mcp.list_tools()
    out = []
    for t in tools:
        schema = getattr(t, "inputSchema", None) or {}
        props = schema.get("properties", {})
        out.append({
            "name": t.name,
            "description": (t.description or "").strip().split("\n")[0],
            "parameters": {k: (v.get("type", "any")) for k, v in props.items()},
            "required": schema.get("required", []),
        })
    return out


def render(tools: list[dict]) -> str:
    lines = ["# MCP Tool Reference", "",
             f"由 runtime introspection 產生（{len(tools)} tools）。", ""]
    for t in tools:
        params = ", ".join(f"{k}:{v}" for k, v in t["parameters"].items()) or "無"
        lines.append(f"## {t['name']}")
        lines.append("")
        lines.append(f"- 用途：{t['description']}")
        lines.append(f"- 參數：{params}")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    out = Path(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[1] == "--out" else ROOT / "docs" / "MCP_TOOL_REFERENCE.md"
    tools = asyncio.run(collect())
    out.write_text(render(tools), encoding="utf-8")
    print(f"wrote {len(tools)} tools -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
