from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from market_ai_hub.integrations.open_source_research import export_isolated_research_dataset
from market_ai_hub.research.accuracy_v2_p2_engine import P2Sample
from market_ai_hub.research.accuracy_v2_p4 import load_p4_protocol
from market_ai_hub.research.accuracy_v2_p4_engine import (
    _higher_quantile,
    _fit_quantile_challenger,
    development_conformal_diagnostic,
    development_quantile_diagnostic,
    ewma_return_volatility,
)


FEATURES = [
    "lag_return_1", "lag_return_2", "lag_return_3", "lag_return_4", "lag_return_5",
    "rolling_mean_return_5", "rolling_volatility_5", "rolling_volatility_20",
    "publication_day_of_week", "days_to_contract_expiry",
]


def _sample(i: int, *, partition: str = "DEVELOPMENT") -> P2Sample:
    origin = date(2026, 1, 2) + timedelta(days=i)
    decision = datetime(2026, 1, 2, 0, 5, tzinfo=timezone.utc) + timedelta(days=i)
    ret = 0.002 * np.sin(i / 3.0) + (0.0002 if i % 2 else -0.0001)
    features = {
        "lag_return_1": 0.001 * np.sin(i),
        "lag_return_2": 0.001 * np.cos(i),
        "lag_return_3": 0.0005 * np.sin(i / 2),
        "lag_return_4": -0.0004 * np.cos(i / 2),
        "lag_return_5": 0.0003 * np.sin(i / 4),
        "rolling_mean_return_5": 0.0001 * np.sin(i / 5),
        "rolling_volatility_5": 0.004 + i * 0.00001,
        "rolling_volatility_20": 0.006 + i * 0.00001,
        "publication_day_of_week": float(i % 5),
        "days_to_contract_expiry": float(90 - i),
    }
    return P2Sample(
        origin_date=origin,
        target_date=origin + timedelta(days=1),
        contract_month="202612",
        partition=partition,
        decision_time=decision,
        label_available_at=decision + timedelta(hours=20),
        origin_price=60000.0,
        actual_price=60000.0 * (1.0 + ret),
        target_return=float(ret),
        features=features,
        source_hash=f"s{i}",
        target_source_hash=f"t{i}",
    )


def test_higher_quantile_and_ewma_are_finite():
    assert _higher_quantile([1, 2, 3, 4], 0.75) == 4.0
    vol = ewma_return_volatility(pd.Series([0.01, -0.01, 0.02]), 0.94)
    assert np.isfinite(vol) and vol > 0


def test_conformal_diagnostic_is_development_only_and_causal():
    samples = [_sample(i) for i in range(45)]
    samples += [_sample(100 + i, partition="EXPOSED_QUARANTINE") for i in range(5)]
    out = development_conformal_diagnostic(samples)
    assert out["status"] == "OK"
    assert out["development_origin_count"] == 45
    assert out["quarantine_used"] is False
    assert out["final_forward_used"] is False
    assert out["static"]["0.90"]["n"] > 0
    assert 0.0 <= out["static"]["0.90"]["empirical_coverage"] <= 1.0
    assert out["not_calibrated_probability"] is True


def test_fixed_quantile_challenger_uses_only_development_and_does_not_promote():
    development = [_sample(i) for i in range(45)]
    quarantine = [_sample(100 + i, partition="EXPOSED_QUARANTINE") for i in range(5)]
    current = dict(development[-1].features)
    out = _fit_quantile_challenger(
        development + quarantine,
        current,
        protocol=load_p4_protocol(),
    )
    assert out["status"] in {"CHALLENGER_UNVALIDATED", "QUANTILE_CROSSING_BLOCKED"}
    assert out["fit_origin_count"] == 45
    assert out["not_validated"] is True
    if out["status"] == "CHALLENGER_UNVALIDATED":
        assert out["model_fits"] == 3
        assert out["may_replace_point_champion"] is False


def test_quantile_oof_diagnostic_excludes_quarantine_and_reports_proper_scores():
    development = [_sample(i) for i in range(75)]
    quarantine = [_sample(100 + i, partition="EXPOSED_QUARANTINE") for i in range(5)]
    out = development_quantile_diagnostic(development + quarantine)
    assert out["status"] == "OK"
    assert out["development_origin_count"] == 75
    assert out["oof_origin_count"] > 0
    assert out["quarantine_used"] is False
    assert out["final_forward_used"] is False
    assert set(out["pinball_loss"]) == {"q10", "q50", "q90"}
    assert all(v >= 0 for v in out["pinball_loss"].values())
    assert 0.0 <= out["p10_p90_empirical_coverage"] <= 1.0
    assert 0.0 <= out["quantile_crossing_rate"] <= 1.0
    assert out["not_point_champion_selection"] is True


def test_jnu_direct_falls_back_to_baseline_analysis_when_price_models_unavailable(monkeypatch):
    import market_ai_hub.services.jnu_direct as direct
    import market_ai_hub.research.accuracy_v2_p4_engine as p4e

    idx = pd.date_range("2026-08-01", periods=50, freq="D", tz="UTC")
    series = pd.Series(np.linspace(60000.0, 61000.0, 50), index=idx, name="settlement")
    meta = {
        "status": "OK",
        "contract_month": "202610",
        "quote_code": "JNU2610",
        "sample_count": 50,
        "first_date": "2026-08-01",
        "latest_date": "2026-09-19",
        "latest_settlement": 61000.0,
        "source": "unit",
        "series_semantics": "EXACT_CONTRACT",
        "price_semantics": "SETTLEMENT",
    }
    robust = {
        "status": "OK",
        "point_reference": {"price": 61000.0},
        "empirical_interval": {"lower_price": 59000.0, "upper_price": 63000.0},
        "volatility": {"ewma_return_volatility": 0.01, "regime": "LOW_VOLATILITY"},
        "lightgbm_quantile_challenger": {"status": "CHALLENGER_UNVALIDATED", "price_quantiles": {}},
        "decision_support": {
            "strong_direction_allowed": False,
            "calibrated_probability_available": False,
            "not_trading_edge": True,
        },
    }
    monkeypatch.setattr(direct, "load_direct_micro_settlements", lambda month="": (series, meta))
    monkeypatch.setattr(p4e, "analyze_no_new_forward_outcome", lambda **kwargs: robust)

    class Broken:
        def predict(self, *args, **kwargs):
            raise RuntimeError("no weights")

    monkeypatch.setattr(direct, "get_chronos", lambda: Broken())
    monkeypatch.setattr(direct, "get_timesfm", lambda: Broken())
    out = direct.analyze_jnu_direct("1d", validate_history=False)
    assert out["status"] == "OK"
    assert out["direct_model_available"] is False
    assert out["ensemble"]["p50"] == 61000.0
    assert out["ensemble"]["method"] == "zero_return_naive_with_development_interval"
    assert out["research_stance"] == "NEUTRAL"
    assert out["not_trading_edge"] is True

    summary = direct.jnu_user_summary(out, calibration_status={"settled_samples": 0})
    assert "無新前向資料時的穩健分析" in summary
    assert "沒有新的真實前向結果" in summary["無新前向資料時的穩健分析"]["證據限制"]


def test_isolated_dataset_export_has_content_hash_and_no_execution(tmp_path):
    frame = pd.DataFrame({"x": [1.0, 2.0], "y": [0.1, -0.1]})
    out = export_isolated_research_dataset(
        "qlib",
        frame,
        tmp_path,
        dataset_id="unit",
        source_hash="source123",
        protocol_hash="protocol123",
        task="RETURN_REGRESSION",
    )
    assert Path(out["parquet_path"]).exists()
    assert Path(out["manifest_path"]).exists()
    assert len(out["parquet_sha256"]) == 64
    assert out["live_execution_allowed"] is False
    assert out["orders_allowed"] is False
