"""MCP server 整合測試：啟動 stdio server，驗證 tools + health_check。"""
import asyncio
import json

import pytest

from pathlib import Path
_REPO = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.integration


async def _call_tool(name, args=None):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=str(_REPO / ".venv" / "Scripts" / "market-ai-mcp.exe"), args=[]
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            res = await session.call_tool(name, args or {})
            return json.loads(res.content[0].text) if res.content else {}


def test_tools_list():
    async def run():
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        params = StdioServerParameters(
            command=str(_REPO / ".venv" / "Scripts" / "market-ai-mcp.exe"), args=[]
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                return [t.name for t in tools.tools]

    names = asyncio.run(run())
    expected = {
        "health_check", "get_system_info", "get_data_source_status", "get_market_data",
        "predict_chronos", "predict_timesfm", "predict_ensemble", "get_model_performance",
        "backtest", "analyze_osaka_nikkei", "analyze_taiwan_stock",
    }
    assert expected <= set(names)


def test_health_check():
    hc = asyncio.run(_call_tool("health_check"))
    assert hc["service"] == "market-ai-hub"
    assert hc["status"] == "ok"
    for key in ("python", "cuda_available", "gpu", "chronos", "timesfm", "fincast",
                "twse", "finmind", "fred", "yfinance", "duckdb", "timestamp"):
        assert key in hc, key


def test_get_system_info():
    info = asyncio.run(_call_tool("get_system_info"))
    assert info["python"]
    assert info["project_path"]  # non-empty (portable)


def test_get_data_source_status():
    st = asyncio.run(_call_tool("get_data_source_status"))
    # Phase 2B：J-Quants 改為 Free-tier 支援（無 key → needs_config）
    assert st["jquants"]["status"] in ("needs_config", "ok")
    assert st["broker"]["status"] == "disabled"
    assert st["tradingview"]["status"] == "disabled"
