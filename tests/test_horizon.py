"""Horizon 解析與 integrity 單元測試（V1 remediation Phase 2/3）。"""
import pytest

from market_ai_hub.services.horizon import (
    HorizonUnsupportedError,
    forecast_dates_from_series,
    parse_horizon,
)


@pytest.mark.parametrize("h,steps", [("1d", 1), ("2d", 2), ("5d", 5), ("10d", 10)])
def test_daily_horizon_steps(h, steps):
    spec = parse_horizon(h, "1d")
    assert spec.supported
    assert spec.effective_horizon_steps == steps
    assert spec.horizon_applied


def test_intraday_unsupported_on_daily():
    for h in ("5m", "15m", "30m", "60m"):
        spec = parse_horizon(h, "1d")
        assert not spec.supported
        assert "UNSUPPORTED_WITH_CURRENT_DATA" in spec.reason


def test_malformed_horizon():
    assert not parse_horizon("foo", "1d").supported
    assert not parse_horizon("", "1d").supported
    assert not parse_horizon("0d", "1d").supported


def test_forecast_dates_trading_days():
    import pandas as pd

    last = pd.Timestamp("2026-09-18", tz="UTC")  # 週五
    dates = forecast_dates_from_series(last, 3)
    assert len(dates) == 3
    assert dates[0] == "2026-09-21"  # 週一（跳過週末）


def test_horizon_error_raised_by_forecast_builders():
    import numpy as np
    import pandas as pd

    from market_ai_hub.models.chronos_model import ChronosAdapter, chronos_forecast
    from market_ai_hub.models.timesfm_model import TimesFM3Adapter, timesfm_forecast

    closes = pd.Series(np.linspace(100, 110, 130))
    with pytest.raises(HorizonUnsupportedError):
        chronos_forecast(ChronosAdapter(), "X", closes, horizon="5m")
    with pytest.raises(HorizonUnsupportedError):
        timesfm_forecast(TimesFM3Adapter(), "X", closes, horizon="60m")
