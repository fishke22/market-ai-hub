"""Phase 2Q-B — MCP E2E stability test（§17/§18/§19）。

實際啟動 MCP stdio process，連續執行 health / system info / 10 quick Osaka /
10 quick Taiwan / status / forward status，確認 no crash / no pipe close。
記錄 RSS（若 psutil 可用）。
"""
from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]


def _rss_mb() -> float | None:
    try:
        import psutil

        return round(psutil.Process().memory_info().rss / (1024 ** 2), 1)
    except Exception:
        return None


async def run() -> int:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=str(_REPO / ".venv" / "Scripts" / "market-ai-mcp.exe"),
        args=[], env=None,
    )
    t0 = time.perf_counter()
    n_calls = 0
    errors: list[str] = []

    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = await session.list_tools()
            names = sorted(t.name for t in tools.tools)

            async def call(name, args=None):
                nonlocal n_calls
                n_calls += 1
                r = await session.call_tool(name, args or {})
                return json.loads(r.content[0].text) if r.content else {}

            hc = await call("health_check")
            si = await call("get_system_info")
            for _ in range(10):
                await call("get_analysis_packet", {"market": "osaka", "target": "OSE_NIKKEI225_MICRO_FUTURES", "detail_level": "compact"})
            for _ in range(10):
                await call("get_analysis_packet", {"market": "taiwan", "target": "3706.TW", "detail_level": "compact"})
            st = await call("get_research_gates")
            fwd = await call("get_forward_test_status")

    elapsed = time.perf_counter() - t0
    result = {
        "tool_count": len(names),
        "tools": names,
        "total_calls": n_calls,
        "elapsed_sec": round(elapsed, 2),
        "health_status": hc.get("status"),
        "health_build_id": (hc.get("build") or {}).get("build_id"),
        "sysinfo_build_id": (si.get("build") or {}).get("build_id"),
        "gates": {k: v.get("status") for k, v in st.get("gates", {}).items()} if isinstance(st, dict) else None,
        "forward_evidence_n": fwd.get("forward_evidence_n"),
        "registry_records_total": fwd.get("registry_records_total"),
        "rss_mb": _rss_mb(),
        "errors": errors,
    }

    out = _REPO / "MCP_E2E_STABILITY.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    ok = (
        len(names) == 21
        and result["health_status"] == "ok"
        and result["health_build_id"] == result["sysinfo_build_id"]
        and result["total_calls"] == 24
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    print("MCP E2E STABILITY:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
