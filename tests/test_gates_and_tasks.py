"""V1.1 gate freshness + model task separation tests。"""
from __future__ import annotations

import pytest


@pytest.mark.integration
def test_gates_have_evaluated_at_build_id_evidence():
    from market_ai_hub.services.model_catalog import compute_research_gates, live_model_cards

    gates = compute_research_gates(live_model_cards())
    for name, g in gates.items():
        assert g["evaluated_at"], f"{name} missing evaluated_at"
        assert g["build_id"], f"{name} missing build_id"
        assert "evidence" in g, f"{name} missing evidence"
        assert g["status"] in ("PASS", "PARTIAL", "UNPROVEN", "FAIL")


def test_gate_uses_current_runtime_not_history(monkeypatch):
    """ENGINEERING_GATE 基於 current runtime：模型 load 成功 → PASS（不受舊歷史影響）。"""
    from market_ai_hub.services import model_catalog

    class FakeAdapter:
        def status(self):
            return "ready"

    class FakeFin:
        def status(self):
            return "ready"

    monkeypatch.setattr(model_catalog, "get_chronos", lambda: FakeAdapter())
    monkeypatch.setattr(model_catalog, "get_timesfm", lambda: FakeAdapter())
    monkeypatch.setattr(model_catalog, "_ts_validation_status", lambda m, s="^N225": ("UNVALIDATED", {}))
    import market_ai_hub.models.fincast_model as fm_mod

    monkeypatch.setattr(fm_mod, "FinCastAdapter", lambda: FakeFin())
    cards = model_catalog.live_model_cards()
    gates = model_catalog.compute_research_gates(cards)
    assert gates["ENGINEERING_GATE"]["status"] == "PASS"


def test_model_tasks_in_catalog():
    from market_ai_hub.services.model_catalog import MODEL_TASKS

    assert MODEL_TASKS["chronos-2"] == "PRICE_FORECAST"
    assert MODEL_TASKS["timesfm-3.0"] == "PRICE_FORECAST"
    assert MODEL_TASKS["xgboost"] == "DIRECTION_CLASSIFICATION"
    assert MODEL_TASKS["lightgbm"] == "DIRECTION_CLASSIFICATION"


def test_classifier_forecast_task_metadata(monkeypatch):
    """分類器輸出 model_task=DIRECTION_CLASSIFICATION、quantile NOT_AVAILABLE、class probs 存在。"""
    import numpy as np
    import pandas as pd

    from market_ai_hub.features.features import build_features
    from market_ai_hub.models.baseline_ml import BaselineClassifier, baseline_forecast

    n = 300
    ts = pd.date_range("2026-01-01", periods=n, freq="B", tz="UTC")
    # 價格級 ±2.5 單位 → 日報酬 ±2.5%，確保 up/flat/down 三類都存在
    close = 100 + np.cumsum(np.random.default_rng(0).normal(0.0, 2.5, n))
    df = pd.DataFrame({
        "timestamp_utc": ts, "timestamp_local": ts, "symbol": "X",
        "open": close, "high": close + 1, "low": close - 1, "close": close,
        "volume": 1000.0, "provider": "t", "data_grade": "RESEARCH_PROXY",
    })
    feat = build_features(df)
    fo = baseline_forecast(BaselineClassifier("lgbm"), "X", feat, horizon="1d")
    d = fo.model_dump()
    assert d["model_task"] == "DIRECTION_CLASSIFICATION"
    assert d["quantile_type"] == "NOT_AVAILABLE"
    assert d["quantiles"] == {"p10": None, "p50": None, "p90": None}
    assert d["lower_reference"] is not None and d["upper_reference"] is not None
    assert d["class_probabilities"] is not None
    assert d["class_probabilities_calibrated"] is False
    assert d["model_metadata"]["task_type"] == "classification"


def test_price_forecast_task_metadata():
    import numpy as np
    import pandas as pd

    from market_ai_hub.models.chronos_model import chronos_forecast
    from tests.test_horizon_integrity import FakeChronosAdapter as FC

    closes = pd.Series(100 + np.sin(np.arange(50) / 8), index=pd.date_range("2026-09-01", periods=50, freq="B", tz="UTC"))
    fo = chronos_forecast(FC(), "^N225", closes, horizon="2d", horizon_steps=2)
    d = fo.model_dump()
    assert d["model_task"] == "PRICE_FORECAST"
    assert d["quantile_type"] == "PREDICTIVE"
    assert d["quantile_valid"] is True
    assert d["forecast_path"], "price model must have path"
    assert d["target_calendar"] == "XTKS"
