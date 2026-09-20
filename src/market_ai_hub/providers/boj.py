"""Bank of Japan Time-Series Data（BOJ 時系列統計）。best-effort（官方資料）。"""
from __future__ import annotations

import io
import logging

import pandas as pd

from market_ai_hub.providers.base import BaseProvider, ProviderError, ProviderInfo, ProviderStatus
from market_ai_hub.providers.http_client import RateLimitedClient

log = logging.getLogger(__name__)

# BOJ Time-Series Data Search 的 CSV 下載入口（官方統計站）。
SEARCH_URL = "https://www.stat-search.boj.or.jp/ssi/mtshtml/m_en.html"
# 直接下載單一統計的代碼參數以官方統計站為準；此為 known-good 範例路徑。
DOWNLOAD_URL = "https://www.stat-search.boj.or.jp/ssi/cgi-bin/famecgi2"


class BojProvider(BaseProvider):
    name = "boj"

    def __init__(self) -> None:
        self.client = RateLimitedClient(self.name, max_retries=3, default_ttl=86400)

    def status(self) -> ProviderInfo:
        return ProviderInfo(name=self.name, status=ProviderStatus.OK,
                            message="Bank of Japan Time-Series（官方，CSV）")

    def fetch_series(self, series_code: str, start: str = "", end: str = "") -> pd.DataFrame:
        """下載單一 BOJ 時序列（series_code 以官方統計站為準）。"""
        params = {"series_code": series_code, "from": start, "to": end}
        body = self.client.request(f"boj_{series_code}_{start}_{end}", DOWNLOAD_URL, params=params)
        try:
            df = pd.read_csv(io.StringIO(body))
        except Exception as e:
            raise ProviderError(f"boj CSV parse failed: {e}") from e
        if df.empty:
            raise ProviderError(f"boj series {series_code} returned empty")
        df["series_code"] = series_code
        df["source_name"] = self.name
        return df
