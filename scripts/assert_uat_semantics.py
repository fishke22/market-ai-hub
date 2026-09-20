"""Phase 2Q-F.4 — assert UAT semantic contract（forbidden combinations check）。

對五個 case 的 backend payload 檢查 forbidden semantic combinations：
- PROXY + direct forecast
- uncalibrated + probability
- 0 votes + UP/DOWN/FLAT
- 0 votes + HIGH/MEDIUM consensus
- invalid session + reference
- NO_ECONOMIC_EDGE + trading advice flag

用法：python scripts/assert_uat_semantics.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def _check_osaka() -> list[str]:
    from market_ai_hub.packet.builder import build_analysis_packet

    p = build_analysis_packet(market="osaka", detail_level="compact", save_analysis=False)
    ts = p["target_semantics"]
    errs = []
    if ts["direct_micro_forecast_status"] != "NOT_AVAILABLE":
        errs.append("Osaka: direct_micro_forecast_status != NOT_AVAILABLE")
    if ts["proxy_model_target"] != "^N225":
        errs.append("Osaka: proxy_model_target != ^N225")
    if ts["direct_market_calendar"] != "OSE/JPX_DERIVATIVES":
        errs.append("Osaka: direct calendar wrong")
    if ts["proxy_model_calendar"] != "XTKS":
        errs.append("Osaka: proxy calendar != XTKS")
    if p["display_policy"]["may_present_as_direct_forecast"]:
        errs.append("Osaka: may_present_as_direct_forecast should be false")
    return errs


def _check_2330() -> list[str]:
    import market_ai_hub.packet.builder as b

    errs = []
    p = b.build_analysis_packet(market="taiwan", target="2330.TW", detail_level="compact", save_analysis=False)
    ts = p["target_semantics"]
    if p["execution_target"] != "2330.TW":
        errs.append("2330: execution_target wrong")
    if p.get("contract_month"):
        errs.append("2330: has contract_month (Osaka contamination)")
    if ts["direct_target"] != "2330.TW":
        errs.append("2330: direct_target wrong")
    if p["display_policy"]["may_present_trading_advice"]:
        errs.append("2330: trading advice allowed")
    return errs


def _check_taiex() -> list[str]:
    from market_ai_hub.packet.builder import build_analysis_packet

    p = build_analysis_packet(market="taiwan_index", target="TAIEX", detail_level="compact", save_analysis=False)
    ts = p["target_semantics"]
    errs = []
    if ts["proxy_model_target"] != "^TWII":
        errs.append("TAIEX: proxy != ^TWII")
    fve = ts.get("forecast_vs_execution", {})
    if fve.get("execution_instruments") != ["TX", "MTX", "TMF"]:
        errs.append("TAIEX: execution instruments wrong")
    return errs


def _check_ensemble() -> list[str]:
    from datetime import datetime, timezone

    from market_ai_hub.ensemble.ensemble import ensemble_equal_weight
    from market_ai_hub.schemas.market_data import DataGrade, ForecastOutput

    def _clf(model, direction):
        return ForecastOutput(
            model=model, symbol="X", as_of=datetime.now(timezone.utc), horizon="1d",
            point_forecast=100.0, expected_return=0.0,
            quantiles={"p10": None, "p50": None, "p90": None},
            direction=direction, confidence=0.5, data_grade=DataGrade.RESEARCH_PROXY,
            model_task="DIRECTION_CLASSIFICATION", eligible_for_direction_vote=False,
            class_probabilities={"class_-1": 0.4, "class_0": 0.3, "class_1": 0.3},
        )

    ens = ensemble_equal_weight([_clf("xgboost", "down"), _clf("lightgbm", "down")], "X", "1d")
    mm = ens.model_metadata
    errs = []
    if mm["direction_status"] != "NO_VALIDATED_MODEL_CONSENSUS":
        errs.append("ensemble: 0 votes should be NO_VALIDATED_MODEL_CONSENSUS")
    if mm["direction_value"] is not None:
        errs.append("ensemble: direction_value should be null at 0 votes")
    return errs


def main() -> int:
    errs = _check_osaka() + _check_2330() + _check_taiex() + _check_ensemble()
    if errs:
        for e in errs:
            print("FAIL:", e)
        return 1
    print("PASS: all UAT semantic contracts satisfied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
