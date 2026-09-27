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


def test_twse_context_tables_use_official_current_endpoints_without_cache(monkeypatch, tmp_path):
    provider = TWSEProvider()
    provider._cache_dir = tmp_path
    calls = []

    payloads = {
        "/exchangeReport/BWIBBU_ALL": [
            {"Date": "1150924", "Code": "3706", "Name": "神達", "PEratio": "14.02", "DividendYield": "5.10", "PBratio": "1.37"}
        ],
        "/exchangeReport/MI_MARGN": [
            {"股票代號": "3706", "股票名稱": "神達", "融資買進": "215", "融資賣出": "405", "融資今日餘額": "26575", "融券買進": "5", "融券賣出": "1", "融券今日餘額": "41"}
        ],
        "/opendata/t187ap05_L": [
            {"出表日期": "1150917", "資料年月": "11508", "公司代號": "3706", "公司名稱": "神達", "營業收入-當月營收": "13557215", "營業收入-上月比較增減(%)": "5.638", "營業收入-去年同月增減(%)": "119.89"}
        ],
        "/opendata/t187ap14_L": [
            {"出表日期": "1150927", "年度": "115", "季別": "2", "公司代號": "3706", "公司名稱": "神達", "基本每股盈餘(元)": "2.58"}
        ],
    }

    def fake_get(path, params, cache=True):
        calls.append((path, params, cache))
        return payloads[path]

    monkeypatch.setattr(provider, "_get_json", fake_get)
    assert len(provider.fetch_context_valuation()) == 1
    assert len(provider.fetch_context_margin_short()) == 1
    assert len(provider.fetch_context_monthly_revenue()) == 1
    assert len(provider.fetch_context_eps_report()) == 1
    assert all(params == {} and cache is False for _, params, cache in calls)


def test_twse_context_table_schema_shift_fails_closed(monkeypatch):
    provider = TWSEProvider()
    monkeypatch.setattr(
        provider,
        "_get_json",
        lambda path, params, cache=False: [{"Code": "3706"}],
    )
    with pytest.raises(Exception, match="schema mismatch"):
        provider.fetch_context_valuation()


def test_twse_taiex_daily_official_ohlc_mocked(monkeypatch):
    provider = TWSEProvider()
    calls = []

    def fake_history(month_date):
        calls.append(month_date)
        return {
            "stat": "OK",
            "fields": ["日期", "開盤指數", "最高指數", "最低指數", "收盤指數"],
            "data": [
                ["115/09/23", "47,894.77", "48,341.56", "47,894.77", "48,157.29"],
                ["115/09/24", "48,075.39", "48,117.54", "47,754.72", "48,024.60"],
            ],
        }

    monkeypatch.setattr(provider, "_get_taiex_history_json", fake_history)
    df = provider.fetch_taiex_daily("20260923", "20260924")
    assert calls == ["20260901"]
    assert list(df["symbol"].unique()) == ["TAIEX"]
    assert list(df["close"]) == [48157.29, 48024.60]
    assert all(df["data_grade"] == "OFFICIAL_DAILY")
    assert df.iloc[-1]["timestamp_utc"].tzinfo is not None


def test_twse_taiex_daily_schema_shift_fails_closed(monkeypatch):
    provider = TWSEProvider()
    monkeypatch.setattr(
        provider,
        "_get_taiex_history_json",
        lambda month_date: {
            "stat": "OK",
            "fields": ["日期", "開盤指數", "收盤指數"],
            "data": [["115/09/24", "48,075.39", "48,024.60"]],
        },
    )
    with pytest.raises(Exception, match="schema mismatch"):
        provider.fetch_taiex_daily("20260924", "20260924")
