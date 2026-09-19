"""V1.3 real-model reproducibility smoke（integration）：deterministic_mode=true 10x 一致。"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

pytestmark = pytest.mark.integration


def _closes():
    idx = pd.date_range("2026-09-01", periods=160, freq="B", tz="UTC")
    return pd.Series(100 + np.sin(np.arange(160) / 8) * 5, index=idx)


@pytest.mark.parametrize("builder,adapter_factory", [
    pytest.param("chronos", lambda: __import__("market_ai_hub.models.chronos_model", fromlist=["ChronosAdapter"]).ChronosAdapter(), id="chronos-2"),
    pytest.param("timesfm", lambda: __import__("market_ai_hub.models.timesfm_model", fromlist=["TimesFM3Adapter"]).TimesFM3Adapter(), id="timesfm-3.0"),
])
def test_real_model_reproducible_10x(builder, adapter_factory):
    if builder == "chronos":
        from market_ai_hub.models.chronos_model import chronos_forecast
    else:
        from market_ai_hub.models.timesfm_model import timesfm_forecast

    adapter = adapter_factory()
    adapter.load()
    closes = _closes()

    outs = []
    for _ in range(10):
        if builder == "chronos":
            fo = chronos_forecast(adapter, "^N225", closes, horizon="3d", horizon_steps=3, seed=42)
        else:
            fo = timesfm_forecast(adapter, "^N225", closes, horizon="3d", horizon_steps=3, seed=42)
        outs.append(fo)

    base = outs[0]
    for o in outs[1:]:
        assert o.deterministic_mode is True
        assert o.forecast_stochastic is False
        assert o.point_forecast == base.point_forecast, f"{builder} point_forecast not reproducible"
        assert o.forecast_path == base.forecast_path, f"{builder} forecast_path not reproducible"
        assert o.input_data_hash == base.input_data_hash
        assert o.forecast_config_hash == base.forecast_config_hash
