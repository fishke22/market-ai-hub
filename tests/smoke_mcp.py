"""MCP stdio smoke check：啟動 market-ai-mcp 並呼叫 tools/list + health_check。"""
from __future__ import annotations

import asyncio
import json
import sys

from pathlib import Path
_REPO = Path(__file__).resolve().parents[1]


async def run() -> int:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=str(_REPO / ".venv" / "Scripts" / "market-ai-mcp.exe"),
        args=[],
        env=None,
    )
    results: dict = {}
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = [t.name for t in tools.tools]
            results["tools"] = names
            expected = {
                "health_check", "get_system_info", "get_data_source_status", "get_market_data",
                "predict_chronos", "predict_timesfm", "predict_ensemble", "get_model_performance",
                "backtest", "analyze_osaka_nikkei", "analyze_taiwan_stock",
            }
            missing = expected - set(names)
            results["missing_tools"] = sorted(missing)
            hc = await session.call_tool("health_check", {})
            results["health_check"] = json.loads(hc.content[0].text) if hc.content else None
            sysinfo = await session.call_tool("get_system_info", {})
            results["system_info"] = json.loads(sysinfo.content[0].text) if sysinfo.content else None

    out = str(_REPO / "reports" / "mcp_smoke.json")
    import os

    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)
    ok = not missing and results["health_check"] and results["health_check"].get("status") == "ok"
    print("tools:", len(names), "missing:", missing)
    print("health:", json.dumps(results["health_check"], ensure_ascii=False, default=str))
    print("MCP SMOKE:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
