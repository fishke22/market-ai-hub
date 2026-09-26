"""Phase 2D.1 tests：license correction / frozen-target detection / 3706 data /
NHITS/NBEATSx adapters / best-baseline rule。"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from market_ai_hub.research.tournament import get_model_entry
from market_ai_hub.research.tournament.data_quality import TargetDataQualityValidator
from market_ai_hub.research.tournament.challengers import NBEATSxAdapter, NHITSAdapter
from market_ai_hub.research.tournament.cli import MODEL_NAMES, _best_baseline_and_model, build_adapters


# ── License correction ──

def test_kronos_tw_license():
    m = get_model_entry("kronos-tw")
    assert m["weight_license"] == "MIT"
    assert m["code_license"] == "MIT"
    assert str(m["training_start"]) == "2010-01-01"
    assert str(m["training_cutoff"]) == "2024-12-31"


def test_kronos_tw_tokenizer_license():
    m = get_model_entry("kronos-tw-tokenizer")
    assert m["weight_license"] == "MIT"


def test_sundial_public_not_gated():
    m = get_model_entry("sundial")
    assert m["model_id"] == "thuml/sundial-base-128m"
    assert m["weight_license"] == "Apache-2.0"
    assert m["status"] != "BLOCKED_LICENSE"


def test_moirai_noncommercial_flag():
    m = get_model_entry("moirai-2")
    assert m["weight_license"] == "CC-BY-NC-4.0"
    assert m["commercial_use"] is False
    assert "NONCOMMERCIAL" in m.get("note", "")


def test_ttm_license():
    m = get_model_entry("tinytimemixer")
    assert m["weight_license"] == "Apache-2.0"
    assert "DEFERRED_DEPENDENCY_CONFLICT" in m.get("note", "")


# ── Frozen target detection ──

def _df(closes, n=None):
    n = n or len(closes)
    idx = pd.date_range(end="2026-09-18", periods=n, freq="B", tz="UTC")
    closes = list(closes)
    return pd.DataFrame({
        "timestamp_utc": idx, "timestamp_local": idx, "symbol": "X",
        "open": closes, "high": (np.asarray(closes) + 1).tolist(), "low": (np.asarray(closes) - 1).tolist(),
        "close": closes, "volume": 1000.0, "provider": "t", "data_grade": "RESEARCH_PROXY",
    })


def test_frozen_target_detection():
    v = TargetDataQualityValidator()
    r = v.validate(_df([80.5] * 100))
    assert r["status"] == "FROZEN_TARGET"
    assert r["eligible_for_evaluation"] is False
    assert r["evaluation_gate"] == "TARGET_DATA_INVALID_FOR_EVALUATION"
    assert r["metrics"]["unique_price_count"] == 1


def test_constant_price_rejection():
    v = TargetDataQualityValidator()
    r = v.validate(_df([100.0] * 80))
    assert r["status"] == "FROZEN_TARGET"
    assert not r["eligible_for_evaluation"]


def test_low_variance_warning():
    v = TargetDataQualityValidator()
    # 幾乎不變但有微小變動
    closes = [100.0] * 79 + [100.01]
    r = v.validate(_df(closes))
    assert r["status"] in ("LOW_VARIANCE", "FROZEN_TARGET")


def test_valid_target():
    v = TargetDataQualityValidator()
    closes = 100 + np.cumsum(np.random.default_rng(0).normal(0, 1, 100))
    r = v.validate(_df(closes.tolist()))
    assert r["status"] == "VALID"
    assert r["eligible_for_evaluation"] is True


# ── 3706 data trace（資料層修正後應有真實 OHLC 變動）──

@pytest.mark.live
def test_3706_data_not_frozen():
    from market_ai_hub.research.forward import _fetch_frame

    df = _fetch_frame("3706.TW")
    v = TargetDataQualityValidator()
    r = v.validate(df)
    # 修正後：唯一收盤價應 > 1（不再是凍結 80.5）
    assert r["metrics"]["unique_price_count"] > 1
    assert r["metrics"]["price_std"] > 0


# ── NHITS / NBEATSx adapters ──

def test_nhits_nbeatsx_adapters_in_tournament():
    names = {a.name for a in build_adapters()}
    assert "nhits" in names and "nbeatsx" in names


def test_missing_optional_models_do_not_break_construction(monkeypatch):
    import builtins
    original = builtins.__import__
    attempts = []
    def without_neuralforecast(name, *args, **kwargs):
        if name == "neuralforecast" or name.startswith("neuralforecast."):
            attempts.append(name)
            raise ModuleNotFoundError(name)
        return original(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", without_neuralforecast)
    adapters = [a for a in build_adapters() if a.name in ("nhits", "nbeatsx")]
    assert len(adapters) == 2 and not attempts
    for adapter in adapters:
        result = adapter.forecast(_df(range(40)), 1)
        assert result.point is None and "import failed" in result.warnings[0]


def test_optional_forecast_dispatch_preserves_model_parameters(monkeypatch):
    import sys
    from types import SimpleNamespace
    calls = []
    def init(self, **kwargs):
        calls.append((type(self).__name__, kwargs))
    models = SimpleNamespace(NHITS=type("NHITS", (), {"__init__": init}),
                             NBEATSx=type("NBEATSx", (), {"__init__": init}))
    class FakeForecast:
        def __init__(self, models, freq):
            self.column = type(models[0]).__name__
        def fit(self, frame):
            assert len(frame) == 40
        def predict(self):
            return pd.DataFrame({"unique_id": ["1"], self.column: [101.]})
    monkeypatch.setitem(sys.modules, "neuralforecast", SimpleNamespace(NeuralForecast=FakeForecast))
    monkeypatch.setitem(sys.modules, "neuralforecast.models", models)
    for adapter in (NHITSAdapter(), NBEATSxAdapter()):
        result = adapter.forecast(_df(range(40)), 1)
        assert result.point == 101. and result.direction == "up"
    assert [name for name, _ in calls] == ["NHITS", "NBEATSx"]
    assert calls[0][1] == {"h": 1, "input_size": 39, "max_steps": 100}
    assert calls[1][1]["stack_types"] == ["identity"]


@pytest.mark.live
@pytest.mark.optional_model
def test_nhits_nbeatsx_smoke():
    from market_ai_hub.research.forward import _fetch_frame

    df = _fetch_frame("^N225").iloc[:120]
    for a in (NHITSAdapter(), NBEATSxAdapter()):
        r = a.forecast(df, 1)
        assert r.point is not None, f"{a.name} point None: {r.warnings}"
        assert r.quantile_valid is None  # point-only，不假造 quantile


# ── Multiple baseline rule ──

def test_best_baseline_comparison():
    summaries = {
        "last_price_naive": {"model": "last_price_naive", "mae": 1.0, "coverage_rate": 1.0},
        "seasonal_naive": {"model": "seasonal_naive", "mae": 0.58, "coverage_rate": 1.0},
        "chronos-2": {"model": "chronos-2", "mae": 0.96, "coverage_rate": 1.0},
    }
    bm = _best_baseline_and_model(summaries)
    assert bm["best_baseline"] == "seasonal_naive"
    assert bm["best_model"] == "chronos-2"
    assert bm["model_vs_best_baseline_delta"] is not None
    assert bm["model_vs_best_baseline_delta"] > 0  # 模型輸給 best baseline


def test_sample_size_report():
    from market_ai_hub.research.tournament.engine import ExamSpec, TournamentEngine
    from market_ai_hub.research.tournament.baselines import LastPriceNaive

    idx = pd.date_range("2026-01-01", periods=150, freq="B", tz="UTC")
    df = pd.DataFrame({
        "timestamp_utc": idx, "timestamp_local": idx, "symbol": "X",
        "open": 100.0, "high": 101.0, "low": 99.0,
        "close": 100 + np.cumsum(np.random.default_rng(0).normal(0, 1, 150)),
        "volume": 1000.0, "provider": "t", "data_grade": "RESEARCH_PROXY",
    })
    r = TournamentEngine().run(ExamSpec("X", "1d", "v1", "base-v1", 60, 3), df, [LastPriceNaive()])
    assert r["n_origins"] == 3  # 樣本大小必須可見


def test_v1_build_unchanged():
    from market_ai_hub.services.build_info import build_fingerprint

    assert build_fingerprint()["build_id"] == "0c5dc8e58d8e76c5"
