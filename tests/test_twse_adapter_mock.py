"""TWSE adapter mock 測試。"""
import pandas as pd
import pytest

from market_ai_hub.providers.twse import TWSEProvider, _validate_day_all


def _sample_payload():
    return [
        {"Code": "2330", "Name": "台積電", "TradeVolume": "123456", "TradeValue": "9.9e9",
         "OpeningPrice": "1000.00", "HighestPrice": "1010.00",
         "LowestPrice": "990.00", "ClosingPrice": "1005.00", "Date": "20260102"},
        {"Code": "2317", "Name": "鴻海", "TradeVolume": "98765", "TradeValue": "2e9",
         "OpeningPrice": "180.00", "HighestPrice": "182.00",
         "LowestPrice": "179.00", "ClosingPrice": "181.00", "Date": "20260102"},
    ]


def test_validate_day_all_ok():
    df = _validate_day_all(_sample_payload())
    assert list(df["Code"]) == ["2330", "2317"]
    assert df["Close"].dtype.kind == "f"


def test_validate_day_all_missing_column():
    payload = _sample_payload()
    for row in payload:
        row.pop("ClosingPrice")
    with pytest.raises(Exception):
        _validate_day_all(payload)


def test_twse_fetch_symbol_daily_mocked(monkeypatch, tmp_path):
    provider = TWSEProvider()
    provider._cache_dir = tmp_path
    got = []

    def fake_get(path, params, cache=True):
        got.append(params["date"])
        return _sample_payload()

    monkeypatch.setattr(provider, "_get_json", fake_get)
    df = provider.fetch_symbol_daily("2330", "20260102", "20260102")
    assert len(df) == 1
    assert df.iloc[0]["symbol"] == "2330"
    assert df.iloc[0]["data_grade"] == "OFFICIAL_DAILY"
    assert df.iloc[0]["timestamp_utc"].tzinfo is not None
