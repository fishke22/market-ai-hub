"""Provider adapter 單元測試 — 全 mock，不依賴網路。"""
from datetime import datetime, timezone

import pandas as pd
import pytest

from market_ai_hub.providers.base import ProviderError
from market_ai_hub.providers.yfinance_provider import YFinanceProvider


class FakeTicker:
    def __init__(self, symbol):
        self.symbol = symbol

    def history(self, period, interval, auto_adjust=False):
        n = 30
        ts = pd.date_range("2026-01-01", periods=n, freq="D", tz="America/New_York")
        df = pd.DataFrame(
            {"Open": [100.0] * n, "High": [101.0] * n, "Low": [99.0] * n,
             "Close": [100.5] * n, "Volume": [1000] * n}, index=ts
        )
        df.index.name = "Date"  # yfinance 原生格式：Date column after reset_index
        return df


class FakeTickerEmpty(FakeTicker):
    def history(self, period, interval, auto_adjust=False):
        return pd.DataFrame()


class FakeYF:
    def Ticker(self, symbol):
        return FakeTicker(symbol)


class FakeYFEmpty:
    def Ticker(self, symbol):
        return FakeTickerEmpty(symbol)


def test_yfinance_fetch_uniform_schema():
    p = YFinanceProvider()
    p._yf = FakeYF()
    df = p.fetch("^N225", period="1mo")
    assert set(df.columns) >= {
        "timestamp_utc", "timestamp_local", "symbol", "open", "high", "low", "close", "volume", "provider", "data_grade"
    }
    assert df["timestamp_utc"].dt.tz is not None
    assert (df["data_grade"] == "RESEARCH_PROXY").all()


def test_yfinance_empty_raises():
    p = YFinanceProvider()
    p._yf = FakeYFEmpty()
    with pytest.raises(ProviderError):
        p.fetch("^N225", period="1mo")


def test_yfinance_status_ok():
    p = YFinanceProvider()
    assert p.status().status.value == "ok"
