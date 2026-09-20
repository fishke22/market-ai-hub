"""Ensemble 測試（不載入模型）。"""
from datetime import datetime, timezone

from market_ai_hub.ensemble.ensemble import (
    ensemble_equal_weight,
    ensemble_performance_weighted,
    model_agreement,
)
from market_ai_hub.schemas.market_data import DataGrade, ForecastOutput


def _fo(model, direction, point=100.0):
    return ForecastOutput(
        model=model, symbol="X", as_of=datetime.now(timezone.utc), horizon="1d",
        point_forecast=point, expected_return=0.01,
        quantiles={"p10": 99.0, "p50": point, "p90": 101.0},
        direction=direction, confidence=0.8, data_grade=DataGrade.RESEARCH_PROXY,
    )


def test_equal_weight_basic():
    fs = [_fo("a", "up", 101), _fo("b", "up", 103), _fo("c", "down", 99), _fo("d", "up", 102)]
    out = ensemble_equal_weight(fs, "X", "1d")
    assert out.model == "ensemble"
    assert out.point_forecast == pytest.approx((101 + 103 + 99 + 102) / 4)
    assert out.direction == "up"
    assert any("model_agreement=HIGH" in w for w in out.warnings)  # 3/4=0.75


def test_empty_raises():
    import pytest as pt

    with pt.raises(ValueError):
        ensemble_equal_weight([], "X", "1d")


def test_performance_weighted_fallback_to_equal_when_insufficient():
    fs = [_fo("a", "up", 101), _fo("b", "up", 103)]
    perf = {"a": 0.9}
    out = ensemble_performance_weighted(fs, "X", "1d", perf)
    assert out.point_forecast == pytest.approx(102)  # fallback equal


def test_performance_weighted_used_when_enough():
    fs = [_fo("a", "up", 100), _fo("b", "up", 110), _fo("c", "up", 120), _fo("d", "up", 130)]
    perf = {"a": 0.1, "b": 0.2, "c": 0.3, "d": 0.4}
    out = ensemble_performance_weighted(fs, "X", "1d", perf)
    assert out.point_forecast == pytest.approx(120.0)


def test_agreement_levels():
    assert model_agreement([_fo("a", "up"), _fo("b", "up"), _fo("c", "up"), _fo("d", "up")]) == "HIGH"
    assert model_agreement([_fo("a", "up"), _fo("b", "down")]) == "MEDIUM"
    assert model_agreement([_fo("a", "up"), _fo("b", "down"), _fo("c", "flat")]) == "LOW"


import pytest  # noqa: E402  (配合上方 local import 的替代)
