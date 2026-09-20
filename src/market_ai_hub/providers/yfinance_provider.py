"""yfinance provider（spec §12）。

Yahoo Finance 非 institutional data API；yfinance 為 unofficial wrapper。
標記：BEST_EFFORT / DELAYED_POSSIBLE / PERSONAL_RESEARCH。
"""
from __future__ import annotations

import logging

import pandas as pd

from market_ai_hub.config.settings import load_symbols
from market_ai_hub.providers.base import BaseProvider, ProviderError, ProviderInfo, ProviderStatus

log = logging.getLogger(__name__)

TZ_MAP = {
    "^N225": "Asia/Tokyo",
    "USDJPY=X": "UTC",
    "JPY=X": "UTC",
    "NQ=F": "America/New_York",
    "ES=F": "America/New_York",
    "^VIX": "America/New_York",
    "^SOX": "America/New_York",
    "GC=F": "America/New_York",
    "CL=F": "America/New_York",
    "BTC-USD": "UTC",
}


class YFinanceProvider(BaseProvider):
    name = "yfinance"

    def __init__(self) -> None:
        import yfinance as yf  # lazy import，缺套件時 status 顯示 degraded 而非 crash

        self._yf = yf

    def status(self) -> ProviderInfo:
        try:
            import yfinance  # noqa: F401

            return ProviderInfo(name=self.name, status=ProviderStatus.OK)
        except Exception as e:  # pragma: no cover
            return ProviderInfo(name=self.name, status=ProviderStatus.UNAVAILABLE, message=str(e))

    def fetch(self, symbol: str, period: str = "1y", interval: str = "1d") -> pd.DataFrame:
        """抓 symbol 歷史資料，回傳統一 schema df（timestamp_utc 為 tz-aware）。"""
        try:
            raw = self._yf.Ticker(symbol).history(period=period, interval=interval, auto_adjust=False)
        except Exception as e:
            log.error("yfinance fetch failed for %s: %s", symbol, e)
            raise ProviderError(f"yfinance fetch failed: {e}") from e
        if raw.empty:
            raise ProviderError(f"yfinance returned empty for {symbol}")

        raw = raw.reset_index()
        ts_col = "Datetime" if "Datetime" in raw.columns else "Date"
        local_tz = TZ_MAP.get(symbol, "UTC")
        ts = pd.to_datetime(raw[ts_col])
        if ts.dt.tz is None:
            # naive → 先 localize 到 instrument local timezone，再 convert UTC（不得同一 naive 兩套解讀）
            local_ts = ts.dt.tz_localize(local_tz, ambiguous="infer", nonexistent="NaT")
            utc_ts = local_ts.dt.tz_convert("UTC")
        else:
            local_ts = ts.dt.tz_convert(local_tz)
            utc_ts = ts.dt.tz_convert("UTC")
        df = pd.DataFrame(
            {
                "timestamp_utc": utc_ts,
                "timestamp_local": local_ts,
                "open": raw["Open"],
                "high": raw["High"],
                "low": raw["Low"],
                "close": raw["Close"],
                "volume": raw["Volume"],
            }
        )
        return self.to_uniform_df(
            df, symbol, provider=self.name, data_grade="RESEARCH_PROXY", local_tz=local_tz
        )

    def fetch_all(self, period: str = "6mo", interval: str = "1d") -> dict[str, pd.DataFrame]:
        out: dict[str, pd.DataFrame] = {}
        for s in load_symbols():
            if s["provider"] != self.name:
                continue
            try:
                out[s["symbol"]] = self.fetch(s["symbol"], period=period, interval=interval)
            except ProviderError as e:
                log.warning("skip %s: %s", s["symbol"], e)
        return out
