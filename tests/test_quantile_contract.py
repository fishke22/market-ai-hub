"""V1.1 quantile contract tests：p10<=p50<=p90 或 NOT_AVAILABLE；invalid 不進 ensemble。"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from market_ai_hub.schemas.market_data import DataGrade, ForecastOutput, validate_quantiles


def test_validate_quantiles_monotonic():
    ok, msg = validate_quantiles({"p10": 1.0, "p50": 2.0, "p90": 3.0})
    assert ok and msg == "valid"


def test_validate_quantiles_violation():
    ok, msg = validate_quantiles({"p10": 3.0, "p50": 2.0, "p90": 1.0})
    assert not ok
    assert "monotonicity" in msg


def test_validate_quantiles_violation_p10_gt_p90():
    ok, _ = validate_quantiles({"p10": 5.0, "p50": 2.0, "p90": 3.0})
    assert not ok


def test_validate_quantiles_missing_is_not_available():
    ok, msg = validate_quantiles({"p10": None, "p50": None, "p90": None})
    assert ok and msg == "NOT_AVAILABLE (missing quantiles)"


def _fo(model, task, quantiles, quantile_valid=None, quantile_type="PREDICTIVE", path=True):
    point = quantiles.get("p50") if isinstance(quantiles.get("p50"), float) else 100.0
    return ForecastOutput(
        model=model, symbol="X", as_of=datetime.now(timezone.utc), horizon="1d",
        point_forecast=point, expected_return=0.0, quantiles=quantiles,
        direction="up", confidence=0.5, data_grade=DataGrade.RESEARCH_PROXY,
        model_task=task, quantile_type=quantile_type, quantile_valid=quantile_valid,
        forecast_path=[{"step": 1, "date": "2026-09-24", "p10": quantiles["p10"], "p50": quantiles["p50"], "p90": quantiles["p90"]}] if path else [],
        forecast_dates=["2026-09-24"] if path else [],
        terminal_forecast=point,
        eligible_for_ensemble_weighting=True,
        eligible_for_price_reference=(task == "PRICE_FORECAST"),
    )


def test_classifier_quantiles_are_not_available():
    from market_ai_hub.models.baseline_ml import baseline_forecast  # noqa: F401

    fo = _fo("xgboost", "DIRECTION_CLASSIFICATION", {"p10": None, "p50": None, "p90": None},
             quantile_type="NOT_AVAILABLE", quantile_valid=None)
    d = fo.model_dump()
    assert d["quantile_type"] == "NOT_AVAILABLE"
    assert d["quantiles"] == {"p10": None, "p50": None, "p90": None}


def test_invalid_quantile_excluded_from_price_ensemble():
    from market_ai_hub.ensemble.ensemble import ensemble_equal_weight

    good = _fo("chronos-2", "PRICE_FORECAST", {"p10": 99.0, "p50": 100.0, "p90": 101.0}, quantile_valid=True)
    bad = _fo("timesfm-3.0", "PRICE_FORECAST", {"p10": 105.0, "p50": 100.0, "p90": 95.0}, quantile_valid=False)
    ens = ensemble_equal_weight([good, bad], "X", "1d")
    mm = ens.model_metadata
    pe = mm["price_ensemble"]
    # bad 的 invalid quantile 不得進入 price quantile 聚合
    assert pe["components"] == ["chronos-2"]
    if pe["quantile_valid"]:
        assert pe["quantiles"]["p10"] <= pe["quantiles"]["p50"] <= pe["quantiles"]["p90"]


def test_price_ensemble_not_contaminated_by_classifier():
    from market_ai_hub.ensemble.ensemble import ensemble_equal_weight

    ts = _fo("chronos-2", "PRICE_FORECAST", {"p10": 99.0, "p50": 100.0, "p90": 101.0}, quantile_valid=True)
    clf = _fo("xgboost", "DIRECTION_CLASSIFICATION", {"p10": None, "p50": None, "p90": None},
              quantile_type="NOT_AVAILABLE", quantile_valid=None, path=False)
    ens = ensemble_equal_weight([ts, clf], "X", "1d")
    pe = ens.model_metadata["price_ensemble"]
    de = ens.model_metadata["direction_ensemble"]
    assert pe["components"] == ["chronos-2"]  # 分類器不進價格層
    # V2：分類器未 eligible_for_direction_vote → 不進正式方向層，只進 raw research view
    assert de["components"] == []
    assert de["final_direction"] == "NO_VALIDATED_MODEL_CONSENSUS"
    assert de["raw_direction_research"]["unvalidated_components"] == ["xgboost"]
    assert ens.model_metadata["legacy_research_only"] is True


def test_ensemble_marks_validation_level_research():
    from market_ai_hub.ensemble.ensemble import ensemble_equal_weight

    ts = _fo("chronos-2", "PRICE_FORECAST", {"p10": 99.0, "p50": 100.0, "p90": 101.0}, quantile_valid=True)
    ens = ensemble_equal_weight([ts], "X", "1d")
    assert ens.model_metadata["validation_level"] == "RESEARCH"
    assert "validation_level=RESEARCH" in ens.warnings
