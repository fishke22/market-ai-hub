"""Phase 2C — 大阪日經 cross-asset panel 定義。

16 個市場符號 + 事件排程（BOJ/FOMC/CPI/NFP/holiday/OSE holiday session/contract expiry）。

每個 symbol 標 provider / timezone / asset_class / data_grade，避免誤標：
- CME Nikkei = NKD=F（CME 期貨，非 OSE）
- ^N225 = 日經現貨指數（proxy）
- DXY = 美元指數 proxy（best-effort）
- US2Y/5Y/10Y/30Y 來自 U.S. Treasury（官方殖利率），非 yfinance
"""
from __future__ import annotations

from market_ai_hub.providers.contract import PROVIDER_SPECS, provider_spec

PANEL = [
    {"symbol": "^N225", "name": "Nikkei 225 Index", "provider": "yfinance", "timezone": "Asia/Tokyo",
     "asset_class": "index", "data_grade": "RESEARCH_PROXY"},
    {"symbol": "^TPX", "name": "TOPIX", "provider": "yfinance", "timezone": "Asia/Tokyo",
     "asset_class": "index", "data_grade": "RESEARCH_PROXY"},
    {"symbol": "NKD=F", "name": "CME Nikkei 225 Futures", "provider": "yfinance", "timezone": "America/Chicago",
     "asset_class": "futures", "data_grade": "RESEARCH_PROXY"},
    {"symbol": "NQ=F", "name": "Nasdaq futures", "provider": "yfinance", "timezone": "America/New_York",
     "asset_class": "futures", "data_grade": "RESEARCH_PROXY"},
    {"symbol": "ES=F", "name": "S&P 500 futures", "provider": "yfinance", "timezone": "America/New_York",
     "asset_class": "futures", "data_grade": "RESEARCH_PROXY"},
    {"symbol": "^SOX", "name": "Philadelphia Semiconductor", "provider": "yfinance", "timezone": "America/New_York",
     "asset_class": "index", "data_grade": "RESEARCH_PROXY"},
    {"symbol": "^VIX", "name": "VIX", "provider": "yfinance", "timezone": "America/New_York",
     "asset_class": "index", "data_grade": "RESEARCH_PROXY"},
    {"symbol": "USDJPY=X", "name": "USDJPY", "provider": "yfinance", "timezone": "UTC",
     "asset_class": "fx", "data_grade": "RESEARCH_PROXY"},
    {"symbol": "DX-Y.NYB", "name": "DXY (US Dollar Index proxy)", "provider": "yfinance", "timezone": "UTC",
     "asset_class": "index", "data_grade": "RESEARCH_PROXY"},
    {"symbol": "US2Y", "name": "US 2Y Treasury", "provider": "ustreasury", "timezone": "America/New_York",
     "asset_class": "rates", "data_grade": "OFFICIAL_DAILY"},
    {"symbol": "US5Y", "name": "US 5Y Treasury", "provider": "ustreasury", "timezone": "America/New_York",
     "asset_class": "rates", "data_grade": "OFFICIAL_DAILY"},
    {"symbol": "US10Y", "name": "US 10Y Treasury", "provider": "ustreasury", "timezone": "America/New_York",
     "asset_class": "rates", "data_grade": "OFFICIAL_DAILY"},
    {"symbol": "US30Y", "name": "US 30Y Treasury", "provider": "ustreasury", "timezone": "America/New_York",
     "asset_class": "rates", "data_grade": "OFFICIAL_DAILY"},
    {"symbol": "GC=F", "name": "Gold futures", "provider": "yfinance", "timezone": "America/New_York",
     "asset_class": "futures", "data_grade": "RESEARCH_PROXY"},
    {"symbol": "CL=F", "name": "WTI futures", "provider": "yfinance", "timezone": "America/New_York",
     "asset_class": "futures", "data_grade": "RESEARCH_PROXY"},
    {"symbol": "BTC-USD", "name": "Bitcoin", "provider": "yfinance", "timezone": "UTC",
     "asset_class": "crypto", "data_grade": "RESEARCH_PROXY"},
]

PANEL_SYMBOLS = [p["symbol"] for p in PANEL]

# 事件排程特徵（來源）：holiday 由 exchange_calendars 提供；其餘為結構化排程（需外部排程資料填入）。
EVENT_SCHEDULE_FEATURES = [
    {"name": "boj_schedule", "source": "schedule", "data_grade": "SCHEDULE", "note": "日銀金融政策決定會合"},
    {"name": "fomc_schedule", "source": "schedule", "data_grade": "SCHEDULE", "note": "FOMC 會議"},
    {"name": "cpi", "source": "schedule", "data_grade": "SCHEDULE", "note": "CPI 公布"},
    {"name": "nfp", "source": "schedule", "data_grade": "SCHEDULE", "note": "非農就業"},
    {"name": "holiday", "source": "exchange_calendars", "data_grade": "OFFICIAL", "note": "交易所休市日"},
    {"name": "ose_holiday_session", "source": "none", "data_grade": "UNAVAILABLE", "note": "OSE Holiday Trading session（無免費來源）"},
    {"name": "contract_expiry", "source": "schedule", "data_grade": "SCHEDULE", "note": "期貨契約到期日"},
]


def panel_by_provider() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for p in PANEL:
        out.setdefault(p["provider"], []).append(p["symbol"])
    return out
