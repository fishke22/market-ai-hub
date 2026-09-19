"""V1 remediation manual acceptance test（Phase 17）— 透過 MCP stdio 真實呼叫。"""
from __future__ import annotations

import asyncio
import json
import sys

SYMBOLS = ["^N225", "3706.TW"]
HORIZONS = ["1d", "2d", "5d", "10d"]


async def call(session, name, args):
    res = await session.call_tool(name, args)
    if not res.content:
        return {"__mcp_error__": "empty content", "__is_error__": res.is_error}
    text = res.content[0].text or ""
    try:
        d = json.loads(text)
    except json.JSONDecodeError:
        d = {"__raw__": text[:200]}
    if res.is_error:
        d["__is_error__"] = True
    return d


async def run() -> dict:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    params = StdioServerParameters(
        command=r"D:\MARKET_AI_HUB\.venv\Scripts\market-ai-mcp.exe", args=[]
    )
    report: dict = {}
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()

            for tool in ("predict_chronos", "predict_timesfm", "predict_ensemble"):
                for sym in SYMBOLS:
                    for h in HORIZONS:
                        d = await call(s, tool, {"symbol": sym, "period": "6mo", "horizon": h})
                        key = f"{tool}/{sym}/{h}"
                        if d.get("__is_error__") or "error" in d:
                            report[key] = {"PASS": False, "detail": str(d)[:200]}
                        elif d.get("status") == "UNSUPPORTED_WITH_CURRENT_DATA":
                            report[key] = {"PASS": False, "detail": d.get("reason")}
                        else:
                            req = d.get("requested_horizon")
                            steps = d.get("effective_horizon_steps")
                            path_len = len(d.get("forecast_path") or [])
                            term = d.get("terminal_forecast")
                            expected_steps = int(h.replace("d", ""))
                            report[key] = {
                                "PASS": req == h and steps == expected_steps and path_len == steps and term is not None,
                                "detail": {"requested_horizon": req, "effective_steps": steps, "path_len": path_len},
                            }
                            if "ensemble" in d:
                                ens = d["ensemble"]
                                report[key]["ensemble_detail"] = {
                                    "component_models": ens.get("model_metadata", {}).get("component_models"),
                                    "weighting_method": ens.get("model_metadata", {}).get("weighting_method"),
                                    "experimental": ens.get("model_metadata", {}).get("experimental"),
                                    "role": ens.get("model_role"),
                                }

            perf = await call(s, "get_model_performance", {})
            report["get_model_performance"] = {"has_baseline_note": "baseline_note" in perf}

            osaka = await call(s, "analyze_osaka_nikkei", {"horizon": "1d"})
            report["analyze_osaka_nikkei"] = {
                "PASS": osaka.get("role") == "ANALYSIS_WRAPPER",
                "role": osaka.get("role"),
                "analysis_direction": osaka.get("analysis_direction"),
                "independent_model_count": osaka.get("independent_model_count"),
                "used_base_models": osaka.get("used_base_models"),
                "used_ensemble": osaka.get("used_ensemble"),
                "status": osaka.get("status"),
            }

            tw = await call(s, "analyze_taiwan_stock", {"stock": "3706.TW", "horizon": "2d"})
            report["analyze_taiwan_stock/3706.TW"] = {
                "PASS": tw.get("role") == "ANALYSIS_WRAPPER",
                "role": tw.get("role"),
                "status": tw.get("status"),
                "xgb_status": tw.get("xgb", {}).get("status"),
                "lgbm_status": tw.get("lgbm", {}).get("status"),
                "ensemble_direction": tw.get("ensemble", {}).get("direction") if isinstance(tw.get("ensemble"), dict) else tw.get("ensemble"),
                "warnings": tw.get("warnings"),
            }

            gates = await call(s, "get_research_gates", {})
            report["get_research_gates"] = {k: v.get("status") for k, v in gates.get("gates", {}).items()}

            info = await call(s, "get_system_info", {})
            report["get_system_info"] = {
                "has_models": "models" in info,
                "has_gates": "research_gates" in info,
                "has_tools": "mcp_tools" in info,
                "ensemble_method": info.get("ensemble_composition", {}).get("method"),
            }
    return report


if __name__ == "__main__":
    report = asyncio.run(run())
    out = r"D:\MARKET_AI_HUB\reports\v1_remediation_acceptance.json"
    import os

    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)

    fails = [k for k, v in report.items() if isinstance(v, dict) and v.get("PASS") is False]
    n_pass = sum(1 for k, v in report.items() if isinstance(v, dict) and v.get("PASS") is True)
    print(f"checks pass: {n_pass}, fail: {len(fails)}")
    for k in fails:
        print("FAIL:", k, report[k].get("detail"))
    print("osaka:", json.dumps(report.get("analyze_osaka_nikkei"), ensure_ascii=False, default=str))
    print("tw:", json.dumps(report.get("analyze_taiwan_stock/3706.TW"), ensure_ascii=False, default=str))
    print("gates:", json.dumps(report.get("get_research_gates"), ensure_ascii=False))
    print("ACCEPTANCE:", "PASS" if not fails else "FAIL")
