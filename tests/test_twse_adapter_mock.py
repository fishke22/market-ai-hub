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

    def fake_stock_day(symbol, roc_month):
        got.append(roc_month)
        # STOCK_DAY 回傳格式：每列 [日期(ROC), 成交股數, 成交金額, 開, 高, 低, 收, 漲跌, 筆數]
        return {"stat": "OK", "data": [
            ["115/01/02", "1,000", "1,000,000", "100.00", "101.00", "99.00", "100.50", "+1.0", "100"],
        ]}

    monkeypatch.setattr(provider, "_get_stock_day_json", fake_stock_day)
    df = provider.fetch_symbol_daily("2330", "20260102", "20260102")
    assert len(df) == 1
    assert df.iloc[0]["symbol"] == "2330"
    assert df.iloc[0]["data_grade"] == "OFFICIAL_DAILY"
    assert df.iloc[0]["timestamp_utc"].tzinfo is not None
    assert df.iloc[0]["close"] == 100.5
