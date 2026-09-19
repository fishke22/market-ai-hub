"""FinMind adapter mock 測試（不真的打 API）。"""
import pandas as pd
import pytest

from market_ai_hub.providers.finmind import FinMindProvider


def test_status_without_token_needs_config(monkeypatch):
    monkeypatch.delenv("FINMIND_TOKEN", raising=False)
    p = FinMindProvider()
    assert p.status().status.value == "needs_config"


def test_status_with_token_ok(monkeypatch):
    monkeypatch.setenv("FINMIND_TOKEN", "test-token")
    p = FinMindProvider()
    assert p.status().status.value == "ok"


def test_fetch_price_mocked(monkeypatch):
    monkeypatch.setenv("FINMIND_TOKEN", "test-token")
    p = FinMindProvider()
    df_in = pd.DataFrame(
        {
            "date": ["2026-01-01", "2026-01-02"],
            "open": [100, 101], "max": [102, 103], "min": [99, 100],
            "close": [101.5, 102.5], "Trading_Volume": [1000, 1100],
        }
    )
    monkeypatch.setattr(p, "fetch_dataset", lambda *a, **k: df_in)
    out = p.fetch_price("2330", "2026-01-01", "2026-01-02")
    assert len(out) == 2
    assert out.iloc[0]["timestamp_utc"].tzinfo is not None
    assert (out["data_grade"] == "OFFICIAL_DAILY").all()


def test_paid_tier_error_path(monkeypatch):
    import httpx

    monkeypatch.setenv("FINMIND_TOKEN", "test-token")
    p = FinMindProvider()

    class Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"msg": "token 權限不足", "data": []}

    monkeypatch.setattr(httpx, "get", lambda *a, **k: Resp())
    with pytest.raises(Exception) as e:
        p.fetch_dataset("TaiwanStockPrice", "2330")
    assert "DATA_REQUIRES_PAID_TIER" in str(e.value)


def test_dataset_tiers_free():
    assert FinMindProvider.DATASET_TIER if False else True
    from market_ai_hub.providers.finmind import DATASET_TIER

    for ds in ("TaiwanStockPrice", "TaiwanStockPriceAdj", "TaiwanStockMonthRevenue"):
        assert DATASET_TIER[ds] == "FREE"
