"""FRED adapter mock 測試。"""
import httpx
import pandas as pd
import pytest

from market_ai_hub.providers.fred import FredProvider


def test_status_without_key_needs_config(monkeypatch):
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    assert FredProvider().status().status.value == "needs_config"


def test_status_with_key_ok(monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", "test-key")
    assert FredProvider().status().status.value == "ok"


def test_fetch_series_mocked(monkeypatch):
    monkeypatch.setenv("FRED_API_KEY", "test-key")
    p = FredProvider()

    class Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"observations": [
                {"date": "2026-01-01", "value": "4.5"},
                {"date": "2026-01-02", "value": "4.4"},
                {"date": "2026-01-03", "value": "."},  # 缺值
            ]}

    monkeypatch.setattr(httpx, "get", lambda *a, **k: Resp())
    df = p.fetch_series("DGS10", limit=10)
    assert len(df) == 2  # '.' 被丟棄
    assert df["observation_timestamp"].dt.tz is not None
    assert "retrieved_at" in df.columns  # 防 leakage
    assert (df["data_grade"] == "OFFICIAL_DAILY").all()


def test_fetch_series_no_key_raises(monkeypatch):
    monkeypatch.delenv("FRED_API_KEY", raising=False)
    p = FredProvider()
    with pytest.raises(Exception):
        p.fetch_series("DGS10")
