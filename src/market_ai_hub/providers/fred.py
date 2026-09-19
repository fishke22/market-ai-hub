"""FRED provider（spec §13）。FREE，需要 FRED_API_KEY（可留空則 status=needs_config）。

保留 observation_timestamp 與 retrieved_at，避免 data leakage。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx
import pandas as pd

from market_ai_hub.config.settings import get_secret
from market_ai_hub.providers.base import BaseProvider, ProviderError, ProviderInfo, ProviderStatus

log = logging.getLogger(__name__)

API = "https://api.stlouisfed.org/fred/series/observations"

# 第一批 series（之後可加 CPI/PCE/UNRATE 等）
SERIES = {
    "DGS2": {"name": "US 2Y Treasury", "frequency": "daily"},
    "DGS10": {"name": "US 10Y Treasury", "frequency": "daily"},
    "FEDFUNDS": {"name": "Fed Funds", "frequency": "daily"},
}


class FredProvider(BaseProvider):
    name = "fred"

    def status(self) -> ProviderInfo:
        if not get_secret("FRED_API_KEY"):
            return ProviderInfo(name=self.name, status=ProviderStatus.NEEDS_CONFIG, message="FRED_API_KEY not set")
        return ProviderInfo(name=self.name, status=ProviderStatus.OK)

    def fetch_series(self, series_id: str, limit: int = 500) -> pd.DataFrame:
        key = get_secret("FRED_API_KEY")
        if not key:
            raise ProviderError("FRED_API_KEY not set")
        try:
            resp = httpx.get(
                API,
                params={"series_id": series_id, "api_key": key, "file_type": "json", "limit": limit},
                timeout=30.0,
            )
            resp.raise_for_status()
            payload = resp.json()
        except Exception as e:
            log.error("fred request failed: %s", e)
            raise ProviderError(f"fred request failed: {e}") from e

        obs = payload.get("observations", [])
        if not obs:
            raise ProviderError(f"fred empty for {series_id}")
        retrieved_at = datetime.now(timezone.utc)
        df = pd.DataFrame(
            {
                "observation_timestamp": pd.to_datetime([o["date"] for o in obs], utc=True),
                "value": pd.to_numeric([o.get("value") or None for o in obs], errors="coerce"),
                "series_id": series_id,
                "retrieved_at": retrieved_at,
            }
        ).dropna(subset=["value"])
        df = df.sort_values("observation_timestamp").reset_index(drop=True)
        # 標記已知落差：FRED 非即時高頻資料
        df["data_grade"] = "OFFICIAL_DAILY"
        return df

    def fetch_all(self, limit: int = 500) -> dict[str, pd.DataFrame]:
        out: dict[str, pd.DataFrame] = {}
        for sid in SERIES:
            try:
                out[sid] = self.fetch_series(sid, limit=limit)
            except ProviderError as e:
                log.warning("fred %s failed: %s", sid, e)
        return out
