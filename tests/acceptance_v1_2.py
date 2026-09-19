"""V1.2 manual acceptance（Cherry Studio 相同啟動方式）。"""
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

    params = StdioServerParameters(
        command=str(_REPO / ".venv" / "Scripts" / "market-ai-mcp.exe"), args=[]
    )
    report: dict = {}
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()

            info = await call(s, "get_system_info", {})
            build_id = info.get("build", {}).get("build_id")
            report["build_id"] = build_id

            # 1. 3706.TW temporal anchors
            for tool in ("predict_chronos", "predict_timesfm"):
                for h in HORIZONS:
                    d = await call(s, tool, {"symbol": "3706.TW", "period": "6mo", "horizon": h})
                    key = f"3706.TW/{tool}/{h}"
                    last_obs = d.get("last_observed_trading_date")
                    targets = d.get("forecast_target_dates") or []
                    origin = d.get("forecast_origin")
                    tz = d.get("exchange_timezone")
                    steps = d.get("effective_horizon_steps")
                    plen = len(d.get("forecast_path") or [])
                    future_ok = all(t > last_obs for t in targets)
                    no_hist = last_obs not in targets
                    report[key] = {
                        "PASS": (d.get("requested_horizon") == h and steps == int(h.replace("d", ""))
                                 and plen == steps and future_ok and no_hist
                                 and bool(origin) and tz == "Asia/Taipei"
                                 and d.get("calendar_verified") is True),
                        "detail": {"last_observed": last_obs, "targets": targets[:5], "tz": tz,
                                   "future_only": future_ok, "no_hist": no_hist},
                    }

            # 2. ^N225 requested OSE window
            osaka = await call(s, "analyze_osaka_nikkei", {"horizon": "5d", "requested_dates": "2026-09-21..2026-09-25"})
            targets = osaka.get("forecast_target_dates") or []
            last_obs = osaka.get("last_observed_trading_date")
            report["^N225/holiday_calendar"] = {
                "PASS": (osaka.get("calendar_mismatch") is True
                         and set(osaka.get("unmapped_sessions") or []) == {"2026-09-21", "2026-09-22", "2026-09-23"}
                         and all(t > last_obs for t in targets)
                         and all(h not in targets for h in ("2026-09-21", "2026-09-22", "2026-09-23"))),
                "targets": targets,
                "unmapped_sessions": osaka.get("unmapped_sessions"),
                "proxy_target_calendar": osaka.get("proxy_target_calendar"),
                "calendar_verified": osaka.get("calendar_verified"),
            }

            # 3. direction ensemble + calibration via analyze_osaka_nikkei (xgb/lgbm 在 ^N225 1y 成功)
            osaka2 = await call(s, "analyze_osaka_nikkei", {"horizon": "1d"})
            de = osaka2.get("direction_classification_ensemble") or {}
            report["direction_ensemble_semantics"] = {
                "PASS": ("vote_direction" in de and "probability_argmax_direction" in de
                         and "final_direction" in de and "direction_resolution_method" in de
                         and "direction_disagreement" in de
                         and osaka2.get("final_direction") == de.get("final_direction")),
                "detail": {k: de.get(k) for k in ("vote_direction", "probability_argmax_direction",
                                                   "final_direction", "direction_resolution_method",
                                                   "direction_disagreement")},
            }

            # 4. XGB calibration flag（^N225）
            xgb = osaka2.get("xgb") or {}
            report["xgb_calibration_metadata"] = {
                "PASS": xgb.get("probability_available") is True and xgb.get("probability_calibrated") is False
                        and xgb.get("calibration_method") == "none",
                "detail": {k: xgb.get(k) for k in ("probability_available", "probability_calibrated",
                                                    "calibration_method", "calibration_sample_size")},
            }

            # 5. gates include sub-gates
            gates = await call(s, "get_research_gates", {})
            g = gates.get("gates", {})
            report["gates"] = {
                "PASS": all(k in g for k in ("MARKET_DATA_GATE", "CALENDAR_GATE", "TEMPORAL_ALIGNMENT_GATE", "DATA_GATE"))
                        and all(g[k].get("build_id") and g[k].get("evaluated_at") for k in g),
                "statuses": {k: g[k].get("status") for k in g},
            }
    return report


if __name__ == "__main__":
    report = asyncio.run(run())
    out = str(_REPO / "reports" / "v1_2_acceptance.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)
    fails = [k for k, v in report.items() if isinstance(v, dict) and v.get("PASS") is False]
    print(f"build_id: {report.get('build_id')}")
    print(f"checks: {sum(1 for v in report.values() if isinstance(v, dict) and v.get('PASS') is True)} pass, {len(fails)} fail")
    for k in fails:
        print("FAIL:", k, str(report[k])[:260])
    print("calendar:", report.get("^N225/holiday_calendar"))
    print("direction:", report.get("direction_ensemble_semantics"))
    print("xgb_calib:", report.get("xgb_calibration_metadata"))
    print("gates:", report.get("gates", {}).get("statuses"))
    print("ACCEPTANCE:", "PASS" if not fails else "FAIL")
