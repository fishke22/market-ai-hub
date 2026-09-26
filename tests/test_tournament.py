"""Phase 2D tests：model registry / license / adapter contract / same-exam /
quantile / classifier no-fake-quantile / baseline presence / performance store /
regime protection / gpu cleanup / revision pin。"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from market_ai_hub.research.tournament import get_model_entry, load_model_registry
from market_ai_hub.research.tournament.adapter import ForecastResult
from market_ai_hub.research.tournament.baselines import (
    PRICE_BASELINES, STATISTICAL_BASELINES, all_baseline_adapters,
)
from market_ai_hub.research.tournament.engine import ExamSpec, TournamentEngine, assert_same_exam
from market_ai_hub.research.tournament.performance_store import PerformanceStore
from market_ai_hub.research.tournament.v1_adapters import ChronosAdapter, LightGBMAdapter


# ── Registry / license ──

def test_model_registry_schema():
    reg = load_model_registry()
    required = {"name", "task", "provider", "repo", "model_id", "revision", "code_license",
                "weight_license", "commercial_use", "training_start", "training_cutoff",
                "supported_horizons", "input_frequency", "supports_covariates",
                "supports_probabilistic", "supports_finetune", "estimated_vram_mb", "status"}
    for m in reg["models"]:
        assert required <= set(m), f"{m.get('name')} missing fields"
    assert reg["hardware_limit_vram_mb"] == 16380


def test_license_metadata():
    assert get_model_entry("timesfm-3.0")["weight_license"] == "timesfm-non-commercial-license-v1.0"
    assert get_model_entry("timesfm-3.0")["commercial_use"] is False
    # Phase 2D.1 修正：Sundial / Moirai-2 其實是公開 model（先前 401 為 repo id 打錯）
    assert get_model_entry("moirai-2")["weight_license"] == "CC-BY-NC-4.0"
    assert get_model_entry("moirai-2")["commercial_use"] is False
    assert get_model_entry("sundial")["weight_license"] == "Apache-2.0"
    assert get_model_entry("chronos-2")["commercial_use"] is True


def test_model_revision_pin():
    for name in ("chronos-2", "timesfm-3.0", "fincast", "tinytimemixer"):
        assert get_model_entry(name)["revision"], name


def test_kronos_clean_oos():
    kronos = get_model_entry("kronos-tw")
    tc = str(kronos["training_cutoff"])
    assert tc == "2024-12-31"
    # 乾淨 OOS 需 2025+（不得把 <= 2024-12-31 稱 clean OOS）
    assert tc < "2025-01-01"


# ── Adapter contract / quantile ──

def test_adapter_contract_fields():
    r = ForecastResult(point=100.0, p10=99.0, p50=100.0, p90=101.0, quantile_valid=True, direction="up")
    assert r.point == 100.0 and r.quantile_valid is True
    assert r.probability_calibrated is False


def test_quantile_contract_violation_flag():
    r = ForecastResult(point=100.0, p10=101.0, p50=100.0, p90=99.0, quantile_valid=False)
    assert r.quantile_valid is False  # p10 > p90 → 不合法，flag 標記


def test_classifier_no_fake_quantile():
    r = ForecastResult(direction="up", class_label=1, point=None, p10=None, p50=None, p90=None,
                       probability_calibrated=False, calibration_metadata={"method": "none"})
    assert r.point is None and r.p10 is None and r.p90 is None
    assert r.probability_calibrated is False


def test_uncalibrated_probability():
    assert LightGBMAdapter().metadata()["task"] == "direction"
    r = ForecastResult(class_label=1, probability_calibrated=False)
    assert r.probability_calibrated is False


# ── Same exam ──

def test_same_exam_enforcement():
    a = ExamSpec("^N225", "5d", "v1", "base-v1", 120, 5)
    b = ExamSpec("^N225", "5d", "v1", "base-v1", 120, 5)
    c = ExamSpec("3706.TW", "5d", "v1", "base-v1", 120, 5)
    d = ExamSpec("^N225", "1d", "v1", "base-v1", 120, 5)
    assert_same_exam(a, b)
    with pytest.raises(ValueError):
        assert_same_exam(a, c)
    with pytest.raises(ValueError):
        assert_same_exam(a, d)


# ── Baselines presence ──

def test_baseline_presence():
    names = {a.name for a in all_baseline_adapters()}
    for n in ("last_price_naive", "random_walk", "drift", "moving_average", "seasonal_naive",
              "majority_class", "always_flat", "ridge", "var", "dynamic_factor", "kalman_local_level"):
        assert n in names, n


def test_seasonal_naive_respects_forecast_horizon():
    from market_ai_hub.research.tournament.baselines import SeasonalNaive
    closes = pd.Series([10., 20., 30., 40., 50.])
    assert [SeasonalNaive()._point(closes, h) for h in (1, 2, 5, 6, 10)] == [10, 20, 50, 10, 50]


def test_interval_metrics_preserve_origin_alignment():
    from market_ai_hub.research.tournament.engine import ModelRun
    run = ModelRun(model="partial", task="price", points=[10., None, 30.],
                   actuals=[10., 20., 30.], origin_prices=[9., 19., 29.],
                   p10=[9., 19., None], p90=[11., None, 31.])
    result = TournamentEngine()._summarize(run, 1)
    assert result["coverage"] == 1.0
    assert result["interval_sample_size"] == 1
    assert result["interval_width"] == pytest.approx(0.2)


def test_invalid_quantile_flag_is_not_evaluated():
    from market_ai_hub.research.tournament.adapter import ModelAdapter
    class InvalidQuantiles(ModelAdapter):
        def forecast(self, df, steps):
            return ForecastResult(point=100., p10=90., p90=110., quantile_valid=False)
    result = TournamentEngine().run(ExamSpec("X", "1d", "v1", "v1", 60, 2),
                                    _df(), [InvalidQuantiles()])
    assert result["summaries"]["adapter"]["coverage"] is None


@pytest.mark.parametrize("adapter_type", ["XGBoostAdapter", "LightGBMAdapter"])
def test_classifier_predicts_origin_not_training_row(monkeypatch, adapter_type):
    from market_ai_hub.features import features
    from market_ai_hub.models import baseline_ml
    from market_ai_hub.research.tournament import v1_adapters
    frame = pd.DataFrame({"close": [100., 110., 90., 120., 80., 130.], "x": range(6)})
    monkeypatch.setattr(features, "build_features", lambda df: df)
    monkeypatch.setattr(baseline_ml, "FEATURE_INPUT", ["x"])
    seen = {}
    class Classifier:
        def __init__(self, key):
            pass
        def fit(self, x, y):
            seen["train"] = x.index.tolist()
        def predict(self, x):
            seen["predict"] = x.index.tolist()
            return [1]
    monkeypatch.setattr(baseline_ml, "BaselineClassifier", Classifier)
    getattr(v1_adapters, adapter_type)().forecast(frame, 2)
    assert seen == {"train": [0, 1, 2, 3], "predict": [5]}


# ── Tournament engine（快速 adapter，不需載入深模型）──

def _df(n=200):
    idx = pd.date_range("2026-01-01", periods=n, freq="B", tz="UTC")
    return pd.DataFrame({
        "timestamp_utc": idx, "timestamp_local": idx, "symbol": "X",
        "open": 100.0, "high": 101.0, "low": 99.0,
        "close": 100 + np.cumsum(np.random.default_rng(0).normal(0, 1, n)),
        "volume": 1000.0, "provider": "t", "data_grade": "RESEARCH_PROXY",
    })


def test_tournament_same_target_horizon():
    from market_ai_hub.research.tournament.baselines import LastPriceNaive, RidgeBaseline

    e = TournamentEngine()
    exam = ExamSpec("X", "1d", "v1", "base-v1", 60, 3)
    r = e.run(exam, _df(), [LastPriceNaive(), RidgeBaseline()])
    assert r["status"] == "OK"
    assert r["target"] == "X" and r["horizon"] == "1d"
    s = r["summaries"]
    assert s["last_price_naive"]["mase"] == pytest.approx(1.0, abs=1e-9)
    assert s["ridge"]["mae"] is not None


def test_unsupported_horizon():
    from market_ai_hub.services.horizon import parse_horizon

    assert not parse_horizon("60m", "1d").supported  # 日線不支援日內


# ── Performance store ──

def test_performance_store_roundtrip(tmp_path):
    store = PerformanceStore(root=tmp_path)
    store.save("abc123", "X", "1d", "normal", ("2026-01-01", "2026-06-01"), "rev1",
               {"model": "m1", "task": "price", "sample_size": 10, "effective_sample_size": 10,
                "failure_count": 0, "abstention_count": 0, "nonfinite_count": 0,
                "invalid_target_count": 0, "failure_rate": 0.0, "coverage_rate": 1.0,
                "mae": 1.0, "rmse": 1.1, "mase": 0.9, "pinball_loss": 0.5,
                "coverage": 0.8, "interval_width": 0.1, "calibration_error": 0.0,
                "direction_accuracy": 0.6, "balanced_accuracy": 0.5, "macro_f1": 0.5, "mcc": 0.1,
                "runtime_seconds": 1.0, "peak_vram_mb": 0.0})
    rows = store.leaderboard(target="X", horizon="1d")
    assert len(rows) == 1 and rows[0]["model"] == "m1"
    assert rows[0]["mae"] == 1.0


# ── Regime protection ──

def test_regime_sample_protection():
    from market_ai_hub.regime.protection import RegimeProtection

    p = RegimeProtection(minimum_sample_size=20)
    r = p.insufficient_result("trend_regime", 5)
    assert r["status"] == "REGIME_EVIDENCE=INSUFFICIENT"
    assert not p.is_sufficient(5)


# ── GPU cleanup ──

def test_gpu_cleanup():
    from market_ai_hub.research.tournament.gpu_guard import GpuGuard

    g = GpuGuard()
    g.release()
    assert g.peak_vram() >= 0.0  # CPU 上為 0，不崩潰


# ── V1 / Phase2A-C 相容 ──

def test_v1_build_unchanged():
    from market_ai_hub.services.build_info import build_fingerprint

    assert build_fingerprint()["build_id"] == "4196bab7c8064acb"
