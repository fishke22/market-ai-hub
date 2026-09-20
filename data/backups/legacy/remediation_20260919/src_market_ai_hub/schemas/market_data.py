"""統一市場資料 schema。所有時間戳 storage 一律 UTC；顯示轉換在 presentation 層做。"""
from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator


class DataGrade(str, Enum):
    RESEARCH_PROXY = "RESEARCH_PROXY"
    DELAYED = "DELAYED"
    OFFICIAL_DAILY = "OFFICIAL_DAILY"
    BROKER_REALTIME = "BROKER_REALTIME"
    EXCHANGE_REALTIME = "EXCHANGE_REALTIME"


class RealtimeGrade(str, Enum):
    BEST_EFFORT = "BEST_EFFORT"
    DELAYED_POSSIBLE = "DELAYED_POSSIBLE"
    PERSONAL_RESEARCH = "PERSONAL_RESEARCH"
    DELAYED = "DELAYED"


class MarketBar(BaseModel):
    """單根 K 線（統一 schema，spec §17）。"""

    timestamp_utc: datetime
    timestamp_local: datetime
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    provider: str
    data_grade: DataGrade
    retrieved_at: datetime

    @field_validator("timestamp_utc", "timestamp_local", "retrieved_at")
    @classmethod
    def _tz_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("naive datetime not allowed")
        return v


class ForecastOutput(BaseModel):
    """預測統一輸出（spec §22）。"""

    model: str
    symbol: str
    as_of: datetime
    horizon: str
    point_forecast: float
    expected_return: float
    quantiles: dict[str, float]
    direction: str
    confidence: float
    data_grade: DataGrade
    warnings: list[str] = Field(default_factory=list)


class Provenance(BaseModel):
    """raw 資料 provenance metadata（spec §18）。"""

    provider: str
    symbol: str
    requested_at: datetime
    received_at: datetime
    first_timestamp: datetime
    last_timestamp: datetime
    row_count: int
    checksum: str
    adjusted: bool = False
    frequency: str
