"""Phase 2Q-B — failure injection tests（§11/§12）：degrade/reject/skip，不 fabricate、不 crash。"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, "src")
ROOT = Path(__file__).resolve().parents[1]


def _empty_direct(monkeypatch):
    """讓 Direct settlement 讀不到（monkeypatch _load_latest_micro_settlement）。"""
    import market_ai_hub.packet.builder as b

    monkeypatch.setattr(b, "_load_latest_micro_settlement", lambda: None)


def test_packet_degrades_when_direct_and_proxy_unavailable(monkeypatch):
    import market_ai_hub.packet.builder as b
    from market_ai_hub.packet.builder import build_analysis_packet

    _empty_direct(monkeypatch)
    monkeypatch.setattr(b, "_proxy_reference", lambda: None)  # proxy down
    p = build_analysis_packet(market="osaka", target="OSE_NIKKEI225_MICRO_FUTURES",
                              detail_level="compact", save_analysis=False)
    assert p["target_data_status"] == "MISSING"  # 誠實標缺失，不 fabricate
    assert p["reference_price"] is None


def test_packet_degrades_when_regime_provider_fails(monkeypatch):
    import market_ai_hub.packet.builder as b
    from market_ai_hub.packet.builder import build_analysis_packet

    _empty_direct(monkeypatch)
    monkeypatch.setattr(b, "_regime_panel", lambda: None)  # cross-asset panel down
    p = build_analysis_packet(market="osaka", target="OSE_NIKKEI225_MICRO_FUTURES",
                              detail_level="compact", save_analysis=False)
    assert p["regime"]["status"] == "INSUFFICIENT_DATA"  # 不 crash


def test_ensemble_excludes_failed_model_not_fake_success():
    from market_ai_hub.ensemble.ensemble import ensemble_equal_weight
    from market_ai_hub.schemas.market_data import DataGrade, ForecastOutput, EngineeringStatus

    def _fo(model, direction):
        return ForecastOutput(
            model=model, symbol="X", as_of=datetime.now(timezone.utc), horizon="1d",
            point_forecast=100.0, expected_return=0.0,
            quantiles={"p10": 99.0, "p50": 100.0, "p90": 101.0},
            direction=direction, confidence=0.5, data_grade=DataGrade.RESEARCH_PROXY,
            model_task="PRICE_FORECAST", quantile_type="PREDICTIVE", quantile_valid=True,
            eligible_for_price_reference=True, eligible_for_ensemble_weighting=True,
        )

    ok = _fo("chronos-2", "up")
    bad = _fo("timesfm-3.0", "down")
    bad.engineering_status = EngineeringStatus.FAIL.value
    ens = ensemble_equal_weight([ok, bad], "X", "1d")
    assert ens.model_metadata["component_models"] == ["chronos-2"]  # failed 被排除
    assert "excluded_components" in " ".join(ens.warnings)


def test_duplicate_timestamp_not_crash():
    """malformed input（duplicate/unsorted）不應 crash forecast_anchor。"""
    import pandas as pd

    from market_ai_hub.services.calendar import forecast_anchor

    anchor = forecast_anchor("^N225", pd.Timestamp("2026-09-18T12:00:00", tz="UTC"), 3)
    assert len(anchor["forecast_target_dates"]) == 3
    assert anchor["forecast_origin"]


def test_negative_price_quantile_rejected():
    """違反 quantile contract（單調性）→ validate_quantiles 回 invalid，不進 ensemble。"""
    from market_ai_hub.schemas.market_data import validate_quantiles

    ok, msg = validate_quantiles({"p10": 105.0, "p50": 100.0, "p90": 95.0})
    assert not ok  # p10 > p50 違反單調性
    assert "monotonicity" in msg
