"""V1.2 direction ensemble semantics + probability calibration metadata tests。"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from market_ai_hub.schemas.market_data import DataGrade, ForecastOutput


def _clf(model, direction, probs, vote_eligible=False):
    return ForecastOutput(
        model=model, symbol="X", as_of=datetime.now(timezone.utc), horizon="1d",
        point_forecast=100.0, expected_return=0.0,
        quantiles={"p10": None, "p50": None, "p90": None},
        direction=direction, confidence=0.5, data_grade=DataGrade.RESEARCH_PROXY,
        model_task="DIRECTION_CLASSIFICATION", quantile_type="NOT_AVAILABLE", quantile_valid=None,
        class_probabilities=probs, class_probabilities_calibrated=False,
        eligible_for_direction_vote=vote_eligible, eligible_for_ensemble_weighting=True,
        forecast_path=[], terminal_forecast=100.0,
        probability_available=True, probability_calibrated=False,
        calibration_method="none", calibration_sample_size=None,
        calibration_metrics={"brier_score": None, "ece": None},
    )


def _price(model, direction):
    return ForecastOutput(
        model=model, symbol="X", as_of=datetime.now(timezone.utc), horizon="1d",
        point_forecast=101.0, expected_return=0.01,
        quantiles={"p10": 99.0, "p50": 101.0, "p90": 103.0},
        direction=direction, confidence=0.5, data_grade=DataGrade.RESEARCH_PROXY,
        model_task="PRICE_FORECAST", quantile_type="PREDICTIVE", quantile_valid=True,
        forecast_path=[{"step": 1, "date": "2026-09-24", "p10": 99.0, "p50": 101.0, "p90": 103.0}],
        forecast_dates=["2026-09-24"], terminal_forecast=101.0,
        eligible_for_ensemble_weighting=True, eligible_for_price_reference=True,
    )


def test_direction_vote_vs_argmax_disagreement():
    """vote=up 但 prob argmax=flat → direction_disagreement=true，final 依固定規則=vote。"""
    from market_ai_hub.ensemble.ensemble import ensemble_equal_weight

    # 兩分類器 vote 都 up；但 aggregated prob 的 argmax 是 flat（class_0 最高）
    a = _clf("xgboost", "up", {"class_-1": 0.2, "class_0": 0.5, "class_1": 0.3})
    b = _clf("lightgbm", "up", {"class_-1": 0.2, "class_0": 0.6, "class_1": 0.2})
    ens = ensemble_equal_weight([a, b], "X", "1d")
    de = ens.model_metadata["direction_ensemble"]
    assert de["vote_direction"] == "up"
    assert de["probability_argmax_direction"] == "flat"
    assert de["direction_disagreement"] is True
    assert de["direction_resolution_method"] == "vote_priority"
    assert de["final_direction"] == "up"  # 固定規則：vote 優先


def test_direction_agreement_when_same():
    from market_ai_hub.ensemble.ensemble import ensemble_equal_weight

    a = _clf("xgboost", "up", {"class_-1": 0.1, "class_0": 0.3, "class_1": 0.6})
    b = _clf("lightgbm", "up", {"class_-1": 0.1, "class_0": 0.2, "class_1": 0.7})
    ens = ensemble_equal_weight([a, b], "X", "1d")
    de = ens.model_metadata["direction_ensemble"]
    assert de["vote_direction"] == "up"
    assert de["probability_argmax_direction"] == "up"
    assert de["direction_disagreement"] is False


def test_direction_falls_back_to_price_when_no_classifier():
    from market_ai_hub.ensemble.ensemble import ensemble_equal_weight

    p = _price("chronos-2", "down")
    ens = ensemble_equal_weight([p], "X", "1d")
    mm = ens.model_metadata
    assert mm["final_direction"] == "down"
    assert mm["direction_resolution_method"] == "price_plurality"


def test_probability_calibration_metadata_classifier():
    import numpy as np
    import pandas as pd

    from market_ai_hub.features.features import build_features
    from market_ai_hub.models.baseline_ml import BaselineClassifier, baseline_forecast

    n = 300
    ts = pd.date_range("2026-01-01", periods=n, freq="B", tz="UTC")
    close = 100 + np.cumsum(np.random.default_rng(0).normal(0.0, 2.5, n))
    df = pd.DataFrame({
        "timestamp_utc": ts, "timestamp_local": ts, "symbol": "3706.TW",
        "open": close, "high": close + 1, "low": close - 1, "close": close,
        "volume": 1000.0, "provider": "t", "data_grade": "RESEARCH_PROXY",
    })
    feat = build_features(df)
    fo = baseline_forecast(BaselineClassifier("xgb"), "3706.TW", feat, horizon="1d")
    d = fo.model_dump()
    assert d["probability_available"] is True
    assert d["probability_calibrated"] is False
    assert d["calibration_method"] == "none"
    assert d["calibration_sample_size"] is None
    assert d["calibration_metrics"]["brier_score"] is None
    assert d["calibration_metrics"]["ece"] is None
    assert d["class_probabilities_calibrated"] is False
    # 不得把 0.84 當 84% 機率的語意線索：warning 明確標記 uncalibrated
    assert any("NOT calibrated" in w for w in d["warnings"])


def test_price_model_has_no_probability():
    import numpy as np
    import pandas as pd

    from market_ai_hub.models.chronos_model import chronos_forecast
    from tests.test_horizon_integrity import FakeChronosAdapter as FC

    closes = pd.Series(100 + np.sin(np.arange(50) / 8), index=pd.date_range("2026-09-01", periods=50, freq="B", tz="UTC"))
    fo = chronos_forecast(FC(), "^N225", closes, horizon="1d", horizon_steps=1)
    d = fo.model_dump()
    assert d["probability_available"] is False
    assert d["probability_calibrated"] is False
