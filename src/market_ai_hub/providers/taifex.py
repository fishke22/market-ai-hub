"""TAIFEX（台灣期交所）官方資料 provider（Phase 2B）。

- 期貨日資料：官方 CSV（big5）
- Time & Sales（最近 30 交易日）：官方成交明細（best-effort）
- authority=TAIFEX；data_grade=OFFICIAL_DAILY；time&sales 為近期明細（非即時逐筆）

端點以官方下載頁為準；若官方改版導致失敗 → ProviderError（graceful degradation），不假造資料。
"""
from __future__ import annotations

import io
import logging
from datetime import datetime, timedelta, timezone

import pandas as pd

from market_ai_hub.providers.base import BaseProvider, ProviderError, ProviderInfo, ProviderStatus
from market_ai_hub.providers.http_client import RateLimitedClient

log = logging.getLogger(__name__)

DAILY_URL = "https://www.taifex.com.tw/cht/3/dlFutDataDown"
TAS_URL = "https://www.taifex.com.tw/cht/3/dlFutDataDown"


class TaifexProvider(BaseProvider):
    name = "taifex"

    def __init__(self) -> None:
        self.client = RateLimitedClient(self.name, max_retries=3, default_ttl=86400)

    def status(self) -> ProviderInfo:
        return ProviderInfo(name=self.name, status=ProviderStatus.OK, message="TAIFEX 官方；期貨日資料 + 近30日 T&S")

    def fetch_daily(self, commodity: str = "TX", start: str = "", end: str = "") -> pd.DataFrame:
        """期貨日資料（近 N 交易日）。commodity 例如 TX（臺指期）。"""
        today = datetime.now(timezone.utc)
        start = start or (today - timedelta(days=40)).strftime("%Y/%m/%d")
        end = end or today.strftime("%Y/%m/%d")
        key = f"daily_{commodity}_{start}_{end}"
        body = self.client.post(key, DAILY_URL, data={
            "down_type": "1",  # TAIFEX dlFutDataDown 必需 down_type=1（每日交易行情）；缺此欄位回空
            "queryStartDate": start, "queryEndDate": end, "commodity_id": commodity,
        })
        try:
            df = pd.read_csv(io.StringIO(body), encoding="big5")
        except Exception as e:
            raise ProviderError(f"taifex CSV parse failed: {e}") from e
        if df.empty:
            raise ProviderError("taifex returned empty daily data")
        return df

    def fetch_time_and_sales(self, commodity: str = "TX", days: int = 30) -> pd.DataFrame:
        """最近 N 交易日 Time & Sales（best-effort，官方明細格式可能變動）。"""
        today = datetime.now(timezone.utc)
        start = (today - timedelta(days=days * 2)).strftime("%Y/%m/%d")
        end = today.strftime("%Y/%m/%d")
        key = f"tas_{commodity}_{start}_{end}"
        body = self.client.post(key, TAS_URL, data={
            "queryStartDate": start, "queryEndDate": end, "commodity_id": commodity,
        })
        try:
            df = pd.read_csv(io.StringIO(body), encoding="big5")
        except Exception as e:
            raise ProviderError(f"taifex T&S parse failed: {e}") from e
        if df.empty:
            raise ProviderError("taifex returned empty time & sales")
        return df
