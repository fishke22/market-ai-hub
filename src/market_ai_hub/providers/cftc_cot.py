"""CFTC COT（Commitments of Traders）Public Reporting API（Socrata open data）。"""
from __future__ import annotations

import logging

import pandas as pd

from market_ai_hub.providers.base import BaseProvider, ProviderError, ProviderInfo, ProviderStatus
from market_ai_hub.providers.http_client import RateLimitedClient

log = logging.getLogger(__name__)

# CFTC COT（Futures & Options Combined）Socrata resource
BASE_URL = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"


class CftcCotProvider(BaseProvider):
    name = "cftc_cot"

    def __init__(self) -> None:
        self.client = RateLimitedClient(self.name, max_retries=3, default_ttl=86400)

    def status(self) -> ProviderInfo:
        return ProviderInfo(name=self.name, status=ProviderStatus.OK,
                            message="CFTC COT public reporting（官方 Socrata，每週）")

    def fetch_cot(self, market_and_exchange: str = "", limit: int = 100) -> pd.DataFrame:
        """查 COT（可選過濾市場，如 "ETHEREUM - CHICAGO MERCANTILE EXCHANGE"）。"""
        params: dict = {"$limit": limit}
        if market_and_exchange:
            params["market_and_exchange_names"] = market_and_exchange
        key = f"cot_{market_and_exchange}_{limit}"
        data = self.client.get_json(key, BASE_URL, params=params)
        if isinstance(data, dict):
            data = data.get("data", [])
        if not data:
            raise ProviderError("CFTC COT returned empty")
        df = pd.DataFrame(data)
        df["source_name"] = self.name
        return df
