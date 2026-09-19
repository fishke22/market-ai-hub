"""Provider 基底：統一 status / 錯誤模型。graceful degradation 的核心。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

import pandas as pd


class ProviderStatus(str, Enum):
    OK = "ok"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    DISABLED = "disabled"
    NEEDS_CONFIG = "needs_config"


@dataclass
class ProviderInfo:
    name: str
    status: ProviderStatus
    message: str = ""
    checked_at: datetime = field(default_factory=datetime.utcnow)


class ProviderError(Exception):
    """Provider 層錯誤；上層抓到後做 graceful degradation。"""


class BaseProvider:
    name: str = "base"

    def status(self) -> ProviderInfo:
        return ProviderInfo(name=self.name, status=ProviderStatus.OK)

    def fetch(self, symbol: str, **kwargs) -> pd.DataFrame:
        raise NotImplementedError

    def to_uniform_df(
        self,
        df: pd.DataFrame,
        symbol: str,
        provider: str,
        data_grade: str,
        local_tz: str,
    ) -> pd.DataFrame:
        """把 provider 原生 df 轉成統一 schema。時間一律 UTC。"""
        out = pd.DataFrame(
            {
                "timestamp_utc": pd.to_datetime(df["timestamp_utc"], utc=True),
                "timestamp_local": pd.to_datetime(df["timestamp_local"]),
                "symbol": symbol,
                "open": df["open"].astype(float),
                "high": df["high"].astype(float),
                "low": df["low"].astype(float),
                "close": df["close"].astype(float),
                "volume": df["volume"].astype(float) if "volume" in df else 0.0,
                "provider": provider,
                "data_grade": data_grade,
            }
        )
        if "timestamp_local" not in df:
            out["timestamp_local"] = out["timestamp_utc"].dt.tz_convert(local_tz)
        return out.sort_values("timestamp_utc").reset_index(drop=True)
