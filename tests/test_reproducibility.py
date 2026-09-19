"""V1.3 forecast reproducibility tests。"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from market_ai_hub.services.reproducibility import (
    DEFAULT_SEED,
    forecast_config_hash,
    input_hash,
    model_revision_local,
    sampling_metadata,
)


def test_input_hash_stable_and_sensitive():
    a = pd.Series(np.linspace(100, 110, 64))
    b = pd.Series(np.linspace(100, 110, 64))
    assert input_hash(a) == input_hash(b)
    c = pd.Series(np.linspace(100, 111, 64))
    assert input_hash(a) != input_hash(c)


def test_config_hash_changes_with_seed_and_horizon():
    h1 = forecast_config_hash("m", "1d", 1, [0.1, 0.5, 0.9], 42, "1d")
    h2 = forecast_config_hash("m", "1d", 1, [0.1, 0.5, 0.9], 43, "1d")
    h3 = forecast_config_hash("m", "5d", 5, [0.1, 0.5, 0.9], 42, "1d")
    assert h1 != h2
    assert h1 != h3
    assert forecast_config_hash("m", "1d", 1, [0.1, 0.5, 0.9], 42, "1d") == h1


def test_model_revision_from_cache(tmp_path):
    snap = tmp_path / "models--amazon--chronos-2" / "snapshots" / "29ec3766d36d"
    snap.mkdir(parents=True)
    assert model_revision_local("amazon/chronos-2", tmp_path) == "29ec3766d36d"


def test_model_revision_unknown_when_no_cache(tmp_path):
    assert model_revision_local("amazon/chronos-2", tmp_path) == "unknown"


def test_sampling_metadata_deterministic_vs_mc():
    det = sampling_metadata(deterministic=True)
    assert det["method"] == "none"
    assert det["n_samples"] is None
    assert det["deterministic_quantiles"] is True

    mc = sampling_metadata(deterministic=False, method="monte_carlo", n_samples=100)
    assert mc["method"] == "monte_carlo"
    assert mc["n_samples"] == 100
    assert mc["deterministic_quantiles"] is False


class _FakeAdapter:
    def predict(self, series, horizon=7, quantiles=None):
        base = float(np.asarray(series)[-1])
        return {"path": {
            "p10": [base * (1 - 0.01 * i) for i in range(1, horizon + 1)],
            "p50": [base * (1 + 0.005 * i) for i in range(1, horizon + 1)],
            "p90": [base * (1 + 0.02 * i) for i in range(1, horizon + 1)],
        }}


def _closes():
    idx = pd.date_range("2026-09-01", periods=200, freq="B", tz="UTC")
    return pd.Series(100 + np.sin(np.arange(200) / 8) * 5, index=idx)


def test_chronos_forecast_reproducible_10x():
    from market_ai_hub.models.chronos_model import chronos_forecast

    closes = _closes()
    outs = [chronos_forecast(_FakeAdapter(), "^N225", closes, horizon="5d", horizon_steps=5, seed=42) for _ in range(10)]
    assert all(o.deterministic_mode for o in outs)
    assert all(o.forecast_stochastic is False for o in outs)
    # 所有輸出 bit-identical
    base = outs[0]
    for o in outs[1:]:
        assert o.point_forecast == base.point_forecast
        assert o.forecast_path == base.forecast_path
        assert o.input_data_hash == base.input_data_hash
        assert o.forecast_config_hash == base.forecast_config_hash
        assert o.inference_seed == 42
        assert o.sampling_config == base.sampling_config


def test_forecast_carries_repro_metadata():
    from market_ai_hub.models.chronos_model import chronos_forecast

    closes = _closes()
    fo = chronos_forecast(_FakeAdapter(), "^N225", closes, horizon="2d", horizon_steps=2, seed=7)
    d = fo.model_dump()
    assert d["inference_seed"] == 7
    assert d["input_data_hash"]
    assert d["forecast_config_hash"]
    assert d["deterministic_mode"] is True
    assert d["model_build_id"]
    assert d["model_revision"] in ("unknown", "29ec3766d36d6f73f0696f85560a422f50e8498c") or d["model_revision"]
    assert d["sampling_config"]["method"] == "none"
