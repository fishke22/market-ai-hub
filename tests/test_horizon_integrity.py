"""Horizon integrity：requested→effective→path→terminal 一致性（用 fake adapters，不載模型）。"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


def _closes(n=200):
    idx = pd.date_range("2026-01-01", periods=n, freq="B", tz="UTC")
    return pd.Series(100 + np.sin(np.arange(n) / 8) * 5, index=idx)


class FakeChronosAdapter:
    def predict(self, series, horizon=7, quantiles=None):
        # 每步路徑值隨 horizon 不同而不同（模擬真實多步輸出）
        base = float(np.asarray(series)[-1])
        return {"path": {
            "p10": [base * (1 - 0.01 * i) for i in range(1, horizon + 1)],
            "p50": [base * (1 + 0.005 * i) for i in range(1, horizon + 1)],
            "p90": [base * (1 + 0.02 * i) for i in range(1, horizon + 1)],
        }}


@pytest.mark.parametrize("horizon,steps", [("1d", 1), ("2d", 2), ("5d", 5), ("10d", 10)])
def test_chronos_path_horizon_integrity(horizon, steps):
    from market_ai_hub.models.chronos_model import chronos_forecast

    fo = chronos_forecast(FakeChronosAdapter(), "^N225", _closes(), horizon=horizon, horizon_steps=steps)
    assert fo.requested_horizon == horizon
    assert fo.effective_horizon_steps == steps
    assert fo.horizon_applied is True
    assert len(fo.forecast_path) == steps
    assert len(fo.forecast_dates) == steps
    assert fo.forecast_path[-1]["p50"] == pytest.approx(fo.terminal_forecast)
    assert fo.point_forecast == pytest.approx(fo.terminal_forecast)


def test_different_horizons_have_different_paths():
    from market_ai_hub.models.chronos_model import chronos_forecast

    closes = _closes()
    f1 = chronos_forecast(FakeChronosAdapter(), "^N225", closes, horizon="1d", horizon_steps=1)
    f5 = chronos_forecast(FakeChronosAdapter(), "^N225", closes, horizon="5d", horizon_steps=5)
    f10 = chronos_forecast(FakeChronosAdapter(), "^N225", closes, horizon="10d", horizon_steps=10)
    # 計算路徑不同：終值隨步數成長；且 metadata 不同
    assert f1.effective_horizon_steps != f5.effective_horizon_steps != f10.effective_horizon_steps
    assert f5.forecast_path[-1]["step"] == 5
    assert f10.forecast_path[-1]["step"] == 10


def test_wrapper_passes_horizon_down(monkeypatch):
    """Wrapper 必須把 horizon 傳給 base forecast builder（不再全跑 7）。"""
    from market_ai_hub.services import analysis

    calls = {}

    class FakeAdapter:
        def __init__(self, *a, **k):
            pass

    def fake_chronos(adapter, symbol, closes, horizon="1d", horizon_steps=7, data_grade="RESEARCH_PROXY", data_frequency="1d"):
        calls["chronos_steps"] = horizon_steps
        from market_ai_hub.models.chronos_model import chronos_forecast
        from tests.test_horizon_integrity import FakeChronosAdapter as FC

        return chronos_forecast(FC(), symbol, closes, horizon=horizon, horizon_steps=horizon_steps)

    monkeypatch.setattr(analysis, "chronos_forecast", fake_chronos)
    monkeypatch.setattr(analysis, "timesfm_forecast", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("skip")))
    monkeypatch.setattr(analysis, "baseline_forecast", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("skip")))
    monkeypatch.setattr(analysis, "YFinanceProvider", lambda: _FakeYF())
    monkeypatch.setattr(analysis, "get_chronos", lambda: FakeAdapter())
    monkeypatch.setattr(analysis, "get_timesfm", lambda: FakeAdapter())
    monkeypatch.setattr(analysis, "BaselineClassifier", lambda n: None)

    r = analysis.analyze_osaka_nikkei(horizon="5d")
    assert calls["chronos_steps"] == 5
    assert r["horizon"] == "5d"


class _FakeYF:
    def fetch(self, sym, period="1y", interval="1d"):
        import pandas as pd

        n = 200
        ts = pd.date_range("2026-01-01", periods=n, freq="B", tz="UTC")
        return pd.DataFrame({
            "timestamp_utc": ts, "timestamp_local": ts, "symbol": sym,
            "open": 100.0, "high": 101.0, "low": 99.0,
            "close": 100 + np.sin(np.arange(n) / 8) * 5, "volume": 1000.0,
            "provider": "yfinance", "data_grade": "RESEARCH_PROXY",
        })
