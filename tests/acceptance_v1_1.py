"""V1.1 manual acceptance（Phase 15）— 用 Cherry Studio 完全相同啟動方式。

檢查：
1. build fingerprint（build_id / source_root / python_executable）出現在重要 response
2. 3706.TW：chronos/timesfm 1d/2d/5d/10d horizon integrity + xgb 不 crash
3. ^N225：quantile contract（p10<=p50<=p90 或 NOT_AVAILABLE）
4. ^N225 holiday calendar：requested_dates=2026-09-21..2026-09-25 → CALENDAR_TARGET_MISMATCH
5. ensemble：price/direction 分層、component table、no invalid quantile
"""
from __future__ import annotations

import asyncio
import json
import os

from pathlib import Path
_REPO = Path(__file__).resolve().parents[1]

HORIZONS = ["1d", "2d", "5d", "10d"]


async def call(session, name, args):
    res = await session.call_tool(name, args)
    if not res.content:
        return {"__mcp_error__": "empty", "__is_error__": res.is_error}
    text = res.content[0].text or ""
    try:
        d = json.loads(text)
    except json.JSONDecodeError:
        d = {"__raw__": text[:300]}
    if res.is_error:
        d["__is_error__"] = True
    return d


async def run() -> dict:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    # 與 Cherry Studio mcp_server 表內完全相同：market-ai-mcp.exe 無 args
    params = StdioServerParameters(
        command=str(_REPO / ".venv" / "Scripts" / "market-ai-mcp.exe"), args=[]
    )
    report: dict = {}
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()

            # 1. build fingerprint
            info = await call(s, "get_system_info", {})
            b = info.get("build", {})
            report["build_fingerprint"] = {
                "PASS": bool(b.get("build_id") and b.get("source_root") and b.get("python_executable")),
                "detail": {k: b.get(k) for k in ("build_id", "market_ai_version", "source_root", "schema_version")},
            }
            hc = await call(s, "health_check", {})
            report["health_build"] = {"PASS": bool(hc.get("build", {}).get("build_id"))}
            gates = await call(s, "get_research_gates", {})
            eg = gates.get("gates", {}).get("ENGINEERING_GATE", {})
            report["gates"] = {
                "PASS": eg.get("status") == "PASS" and bool(eg.get("evaluated_at")) and bool(eg.get("build_id")),
                "status": eg.get("status"),
                "evidence_models": list((eg.get("evidence") or {}).keys()),
            }

            # 2. 3706.TW horizon integrity + xgb
            for tool in ("predict_chronos", "predict_timesfm"):
                for h in HORIZONS:
                    d = await call(s, tool, {"symbol": "3706.TW", "period": "6mo", "horizon": h})
                    key = f"3706.TW/{tool}/{h}"
                    if d.get("__is_error__") or "error" in d:
                        report[key] = {"PASS": False, "detail": str(d)[:200]}
                    elif d.get("status") == "UNSUPPORTED_WITH_CURRENT_DATA":
                        report[key] = {"PASS": False, "detail": d.get("reason")}
                    else:
                        steps = d.get("effective_horizon_steps")
                        plen = len(d.get("forecast_path") or [])
                        q = d.get("quantiles") or {}
                        q_ok = (q.get("p10") is None) or (
                            q.get("p10") is not None and q.get("p50") is not None and q.get("p90") is not None
                            and q["p10"] <= q["p50"] <= q["p90"]
                        )
                        report[key] = {
                            "PASS": d.get("requested_horizon") == h and steps == int(h.replace("d", ""))
                                    and plen == steps and d.get("build_id"),
                            "quantile_ok": q_ok,
                            "detail": {"steps": steps, "path_len": plen, "build_id": d.get("build_id")},
                        }
            ens_tw = await call(s, "predict_ensemble", {"symbol": "3706.TW", "period": "6mo", "horizon": "5d"})
            mm = (ens_tw.get("ensemble") or {}).get("model_metadata") or {}
            used = ens_tw.get("used_base_models") or []
            # xgb/lgbm 在短視窗可能合法 unavailable（單一類別）；核心要求 = 不 crash + price 層完整
            report["3706.TW/ensemble/5d"] = {
                "PASS": ens_tw.get("requested_horizon") == "5d"
                        and ens_tw.get("effective_horizon_steps") == 5
                        and "chronos-2" in used and "timesfm-3.0" in used
                        and len(mm.get("component_table") or []) == 4,
                "used_base_models": used,
                "component_table_entries": len(mm.get("component_table") or []),
                "price_components": (mm.get("price_ensemble") or {}).get("components"),
                "direction_components": (mm.get("direction_ensemble") or {}).get("components"),
                "legacy_research_only": mm.get("legacy_research_only"),
            }
            bt = await call(s, "backtest", {"symbol": "3706.TW", "period": "1y", "n_splits": 3, "model": "xgb"})
            report["3706.TW/xgb_backtest_no_crash"] = {
                "PASS": not bt.get("__is_error__") and bt.get("balanced_accuracy") is not None,
                "balanced_accuracy": bt.get("balanced_accuracy"),
            }

            # 3. ^N225 quantile contract
            q_checks = {}
            for tool in ("predict_chronos", "predict_timesfm"):
                for h in ("1d", "5d"):
                    d = await call(s, tool, {"symbol": "^N225", "period": "6mo", "horizon": h})
                    q = d.get("quantiles") or {}
                    if q.get("p10") is None and q.get("p50") is None and q.get("p90") is None:
                        ok = d.get("quantile_type") == "NOT_AVAILABLE"
                    else:
                        ok = (q.get("p10") <= q.get("p50") <= q.get("p90"))
                    q_checks[f"{tool}/{h}"] = ok
            report["^N225/quantile_contract"] = {"PASS": all(q_checks.values()), "detail": q_checks}

            # 4. holiday calendar mismatch
            osaka = await call(s, "analyze_osaka_nikkei", {"horizon": "5d", "requested_dates": "2026-09-21..2026-09-25"})
            mismatch = osaka.get("calendar_mismatch")
            mismatch_detail = osaka.get("mismatch_detail", "")
            target_dates = osaka.get("target_trading_dates") or []
            report["^N225/holiday_calendar"] = {
                "PASS": mismatch is True and "CALENDAR_TARGET_MISMATCH" in mismatch_detail
                        and "2026-09-21" not in target_dates
                        and osaka.get("target_calendar") == "XTKS",
                "calendar_mismatch": mismatch,
                "target_trading_dates": target_dates[:5],
                "role": osaka.get("role"),
                "confidence_inputs_keys": list((osaka.get("confidence_inputs") or {}).keys()),
            }

            # 5. ensemble semantics on ^N225
            ens = await call(s, "predict_ensemble", {"symbol": "^N225", "period": "6mo", "horizon": "5d"})
            emm = (ens.get("ensemble") or {}).get("model_metadata") or {}
            pe = emm.get("price_ensemble") or {}
            de = emm.get("direction_ensemble") or {}
            report["^N225/ensemble_semantics"] = {
                "PASS": set(pe.get("components") or []) == {"chronos-2", "timesfm-3.0"}
                        and set(de.get("components") or []) == {"xgboost", "lightgbm"}
                        and emm.get("validation_level") == "RESEARCH"
                        and ens.get("legacy_research_only") is True,
                "price_components": pe.get("components"),
                "direction_components": de.get("components"),
                "validation_level": emm.get("validation_level"),
                "counts": {
                    "independent_base_model_count": ens.get("independent_base_model_count"),
                    "eligible_direction_vote_count": ens.get("eligible_direction_vote_count"),
                    "eligible_price_reference_count": ens.get("eligible_price_reference_count"),
                },
            }
    return report


if __name__ == "__main__":
    report = asyncio.run(run())
    out = str(_REPO / "reports" / "v1_1_acceptance.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    fails = [k for k, v in report.items() if isinstance(v, dict) and v.get("PASS") is False]
    print(f"checks: {sum(1 for v in report.values() if isinstance(v, dict) and v.get('PASS') is True)} pass, {len(fails)} fail")
    for k in fails:
        print("FAIL:", k, str(report[k])[:220])
    print("gates:", report.get("gates"))
    print("calendar:", report.get("^N225/holiday_calendar"))
    print("ensemble:", report.get("^N225/ensemble_semantics"))
    print("ACCEPTANCE:", "PASS" if not fails else "FAIL")
