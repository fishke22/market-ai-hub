"""model_role / ensemble metadata / wrapper role / independent votes / backcompat（V1 remediation）。"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def _fo(model, direction="up", role="BASE_MODEL", eligible_vote=False, path_len=1, point=101.0):
    from datetime import datetime, timezone

    from market_ai_hub.schemas.market_data import DataGrade, ForecastOutput

    dates = ["2026-01-01"] * path_len
    return ForecastOutput(
        model=model, symbol="X", as_of=datetime.now(timezone.utc), horizon="1d",
        point_forecast=point, expected_return=0.01,
        quantiles={"p10": 99.0, "p50": point, "p90": 103.0},
        direction=direction, confidence=0.8, data_grade=DataGrade.RESEARCH_PROXY,
        requested_horizon="1d", effective_horizon_steps=1, data_frequency="1d",
        horizon_applied=True,
        forecast_path=[{"step": 1, "date": d, "p10": 99.0, "p50": point, "p90": 103.0} for d in dates],
        forecast_dates=dates, terminal_forecast=point,
        model_role=role,
        eligible_for_direction_vote=eligible_vote,
        eligible_for_ensemble_weighting=True,
    )


def test_model_roles_from_catalog():
    from market_ai_hub.services.model_catalog import MODEL_ROLES

    assert MODEL_ROLES["chronos-2"] == "BASE_MODEL"
    assert MODEL_ROLES["timesfm-3.0"] == "BASE_MODEL"
    assert MODEL_ROLES["xgboost"] == "BASE_MODEL"
    assert MODEL_ROLES["lightgbm"] == "BASE_MODEL"
    assert MODEL_ROLES["ensemble"] == "ENSEMBLE"
    assert MODEL_ROLES["analysis_wrapper"] == "ANALYSIS_WRAPPER"


def test_forecast_carries_role():
    assert _fo("chronos-2").model_role == "BASE_MODEL"


def test_ensemble_component_metadata():
    from market_ai_hub.ensemble.ensemble import ensemble_equal_weight

    fs = [
        _fo("chronos-2", "up", point=101),
        _fo("timesfm-3.0", "up", point=103),
        _fo("xgboost", "down", point=99),
        _fo("lightgbm", "up", point=102),
    ]
    ens = ensemble_equal_weight(fs, "X", "1d")
    assert ens.model_role == "ENSEMBLE"
    mm = ens.model_metadata
    assert mm["component_models"] == ["chronos-2", "timesfm-3.0", "xgboost", "lightgbm"]
    assert mm["weighting_method"] == "EQUAL_WEIGHT_RESEARCH"
    assert mm["experimental"] is True
    assert set(mm["weights"].keys()) == {"chronos-2", "timesfm-3.0", "xgboost", "lightgbm"}
    assert sum(mm["weights"].values()) == pytest.approx(1.0)
    assert "experimental=True" in ens.warnings


def test_ensemble_not_counted_as_independent():
    from market_ai_hub.ensemble.ensemble import ensemble_equal_weight, independent_vote_summary

    fs = [_fo("chronos-2", "up"), _fo("timesfm-3.0", "up")]
    ens = ensemble_equal_weight(fs, "X", "1d")
    vote = independent_vote_summary(fs + [ens])  # ensemble 混入也不得當 base model
    assert vote["independent_base_model_count"] == 2  # 模型存在數
    assert vote["eligible_direction_vote_count"] == 0  # 投票資格數（全 UNVALIDATED）
    assert vote["independent_model_agreement"] == "N/A"


def test_independent_votes_only_eligible_base_models():
    from market_ai_hub.ensemble.ensemble import independent_vote_summary

    fs = [
        _fo("xgboost", "up", eligible_vote=True),
        _fo("lightgbm", "down", eligible_vote=True),
        _fo("chronos-2", "up", eligible_vote=False),
    ]
    vote = independent_vote_summary(fs)
    assert vote["independent_base_model_count"] == 3
    assert vote["eligible_direction_vote_count"] == 2
    assert vote["independent_direction_votes"] == {"xgboost": "up", "lightgbm": "down"}
    assert vote["independent_model_agreement"] == "MEDIUM"


def test_ensemble_excludes_failed_components():
    from market_ai_hub.ensemble.ensemble import ensemble_equal_weight

    ok = [_fo("chronos-2", "up", point=101), _fo("timesfm-3.0", "up", point=103)]
    bad = _fo("lightgbm", "down", point=50)
    bad.engineering_status = "FAIL"
    ens = ensemble_equal_weight(ok + [bad], "X", "1d")
    assert ens.model_metadata["component_models"] == ["chronos-2", "timesfm-3.0"]
    assert any("excluded_components" in w for w in ens.warnings)


def test_wrapper_role_and_fields(monkeypatch):
    from market_ai_hub.services import analysis
    from tests.test_horizon_integrity import _FakeYF

    class FA:
        pass

    from market_ai_hub.models.chronos_model import chronos_forecast
    from tests.test_horizon_integrity import FakeChronosAdapter as FC

    def fake_chronos(adapter, symbol, closes, horizon="1d", horizon_steps=7, data_grade="RESEARCH_PROXY", data_frequency="1d"):
        return chronos_forecast(FC(), symbol, closes, horizon=horizon, horizon_steps=horizon_steps)

    monkeypatch.setattr(analysis, "chronos_forecast", fake_chronos)
    monkeypatch.setattr(analysis, "timesfm_forecast", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("skip")))
    monkeypatch.setattr(analysis, "baseline_forecast", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("skip")))
    monkeypatch.setattr(analysis, "YFinanceProvider", lambda: _FakeYF())
    monkeypatch.setattr(analysis, "get_chronos", lambda: FA())
    monkeypatch.setattr(analysis, "get_timesfm", lambda: FA())
    monkeypatch.setattr(analysis, "BaselineClassifier", lambda n: None)

    r = analysis.analyze_osaka_nikkei(horizon="2d")
    assert r["role"] == "ANALYSIS_WRAPPER"
    assert "analysis_direction" in r
    assert "integrated_market_view" in r
    assert r["used_base_models"] == ["chronos-2"]
    assert r["used_ensemble"] is True
    assert "independent_base_model_count" in r
    assert "^N225" in r["used_market_data"]
    assert r["rule_inputs"]
    assert "confidence_inputs" in r
    assert "target_calendar" in r
    # backward-compat legacy keys
    for k in ("symbol", "horizon", "status", "data_grade", "warnings", "cross_market", "ensemble", "chronos"):
        assert k in r, k


def test_backcompat_forecast_fields():
    fo = _fo("chronos-2")
    d = fo.model_dump()
    for k in ("model", "symbol", "as_of", "horizon", "point_forecast", "expected_return",
              "quantiles", "direction", "confidence", "data_grade", "warnings"):
        assert k in d
    assert set(d["quantiles"].keys()) == {"p10", "p50", "p90"}
