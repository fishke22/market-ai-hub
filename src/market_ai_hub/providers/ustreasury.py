"""U.S. Treasury Daily Treasury Par Yield Curve Rates（2Y/5Y/10Y/30Y）。"""
from __future__ import annotations

import io
import logging
from datetime import datetime

import pandas as pd

from market_ai_hub.providers.base import BaseProvider, ProviderError, ProviderInfo, ProviderStatus
from market_ai_hub.providers.http_client import RateLimitedClient

log = logging.getLogger(__name__)

BASE = "https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv"
COLS = {"2 Yr": "dgs2", "5 Yr": "dgs5", "10 Yr": "dgs10", "30 Yr": "dgs30"}


class USTreasuryProvider(BaseProvider):
    name = "ustreasury"

    def __init__(self) -> None:
        self.client = RateLimitedClient(self.name, max_retries=3, default_ttl=86400)

    def status(self) -> ProviderInfo:
        return ProviderInfo(name=self.name, status=ProviderStatus.OK, message="U.S. Treasury par yield curve (2Y/5Y/10Y/30Y)")

    def fetch_daily_rates(self, year: int | None = None) -> pd.DataFrame:
        """某年度每日 2Y/5Y/10Y/30Y 殖利率（CSV）。"""
        year = year or datetime.now().year
        url = f"{BASE}/{year}/all?type=daily_treasury_yield_curve&field_tdr_date_value={year}&page&_format=csv"
        body = self.client.request(f"rates_{year}", url)
        try:
            df = pd.read_csv(io.StringIO(body), encoding="utf-8-sig")
        except Exception as e:
            raise ProviderError(f"treasury CSV parse failed: {e}") from e
        if df.empty:
            raise ProviderError("treasury returned empty")
        keep = {"Date": "date", **COLS}
        df = df.rename(columns=keep)[["date", "dgs2", "dgs5", "dgs10", "dgs30"]]
        df["date"] = pd.to_datetime(df["date"], utc=True)
        for c in ("dgs2", "dgs5", "dgs10", "dgs30"):
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df = df.dropna(subset=["dgs2", "dgs10"]).sort_values("date").reset_index(drop=True)
        df["source_name"] = self.name
        return df
