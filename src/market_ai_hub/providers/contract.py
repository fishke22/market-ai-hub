"""Phase 2B — 統一 DataProviderContract（資料來源契約）。

每個資料來源都有靜態 spec（authority / market / frequency / data_grade / license /
delay_status / target_match / information_cutoff_compatible / base_delay）。
每筆資料可產生 contract 實例，計算 available_at（供 no-look-ahead）與 freshness。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, Field


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ProviderSpec:
    source_name: str
    authority: str
    market: str
    frequency: str                      # daily / intraday / tick / weekly
    data_grade: str                     # OFFICIAL_DAILY / OFFICIAL_DELAYED / RESEARCH_PROXY ...
    license: str
    delay_status: str                   # REALTIME / DELAYED / FREE_PLAN_LIMITED / BEST_EFFORT / UNKNOWN
    target_match: str                   # EXACT / PROXY / INDEX_PROXY
    information_cutoff_compatible: bool
    base_delay_seconds: int = 0         # 已知延遲（available_at = source_timestamp + delay）


PROVIDER_SPECS: dict[str, ProviderSpec] = {
    "twse": ProviderSpec("twse", "TWSE", "TWSE", "daily", "OFFICIAL_DAILY",
                         "台灣證券交易所公開資料", "REALTIME", "EXACT", True, 0),
    "finmind": ProviderSpec("finmind", "FinMind", "TWSE", "daily", "OFFICIAL_DAILY",
                            "FinMind 服務條款（Free tier）", "REALTIME", "EXACT", True, 0),
    "fred": ProviderSpec("fred", "Federal Reserve Bank of St. Louis", "US macro", "daily",
                         "OFFICIAL_DAILY", "美國政府公開資料", "REALTIME", "EXACT", True, 0),
    "yfinance": ProviderSpec("yfinance", "Yahoo Finance (unofficial)", "global proxy", "daily",
                             "RESEARCH_PROXY", "unofficial wrapper（個人研究用）",
                             "BEST_EFFORT", "INDEX_PROXY", True, 0),
    "taifex": ProviderSpec("taifex", "TAIFEX (台灣期交所)", "TWSE futures", "daily",
                           "OFFICIAL_DAILY", "台灣期交所公開資料", "REALTIME", "EXACT", True, 0),
    "boj": ProviderSpec("boj", "Bank of Japan", "JP macro", "daily",
                        "OFFICIAL_DAILY", "日本銀行公開資料", "REALTIME", "EXACT", True, 0),
    "ustreasury": ProviderSpec("ustreasury", "U.S. Department of the Treasury", "US rates", "daily",
                               "OFFICIAL_DAILY", "美國政府公開資料", "REALTIME", "EXACT", True, 0),
    "cftc_cot": ProviderSpec("cftc_cot", "CFTC", "US futures COT", "weekly",
                             "OFFICIAL_DELAYED", "美國政府公開資料", "DELAYED", "EXACT", True, 86400 * 3),
    "jquants": ProviderSpec("jquants", "JPX J-Quants", "JP", "daily",
                            "OFFICIAL_DELAYED", "J-Quants 服務條款（Free plan）",
                            "FREE_PLAN_LIMITED", "EXACT", True, 86400 * 84),  # Free ~12 週延遲
}


class DataProviderContract(BaseModel):
    """單筆資料的來源契約（記錄來源品質，供 no-look-ahead 判斷）。"""

    source_name: str
    authority: str
    market: str
    instrument: str
    event_time: datetime
    source_timestamp: datetime
    received_at: datetime
    available_at: datetime
    freshness: str
    frequency: str
    data_grade: str
    license: str
    delay_status: str
    target_match: str
    information_cutoff_compatible: bool


def _freshness(age_seconds: float | None) -> str:
    if age_seconds is None:
        return "UNKNOWN"
    if age_seconds <= 60:
        return "LIVE"
    if age_seconds <= 3600:
        return "RECENT"
    if age_seconds <= 86400:
        return "STALE"
    return "HISTORICAL"


def make_contract(
    source_name: str,
    instrument: str,
    event_time: datetime | None = None,
    source_timestamp: datetime | None = None,
    received_at: datetime | None = None,
) -> DataProviderContract:
    """由 source_name 的 spec + 時間戳產生 contract 實例。"""
    spec = PROVIDER_SPECS[source_name]
    received_at = received_at or utcnow()
    source_timestamp = source_timestamp or received_at
    event_time = event_time or source_timestamp

    def _aware(dt: datetime) -> datetime:
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)

    src = _aware(source_timestamp)
    available_at = src + timedelta(seconds=spec.base_delay_seconds)
    age = (received_at - src).total_seconds() if received_at.tzinfo is not None else None

    return DataProviderContract(
        source_name=source_name,
        authority=spec.authority,
        market=spec.market,
        instrument=instrument,
        event_time=_aware(event_time),
        source_timestamp=src,
        received_at=_aware(received_at),
        available_at=available_at,
        freshness=_freshness(age),
        frequency=spec.frequency,
        data_grade=spec.data_grade,
        license=spec.license,
        delay_status=spec.delay_status,
        target_match=spec.target_match,
        information_cutoff_compatible=spec.information_cutoff_compatible,
    )


def provider_spec(source_name: str) -> ProviderSpec:
    return PROVIDER_SPECS[source_name]
