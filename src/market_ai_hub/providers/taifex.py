"""TAIFEX（台灣期交所）官方資料 provider（Phase 2B）。

- 期貨日資料：官方 CSV（big5）
- Time & Sales（最近 30 交易日）：官方成交明細（best-effort）
- authority=TAIFEX；data_grade=OFFICIAL_DAILY；time&sales 為近期明細（非即時逐筆）

端點以官方下載頁為準；若官方改版導致失敗 → ProviderError（graceful degradation），不假造資料。
"""
from __future__ import annotations

import csv
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import hashlib
import io
import logging

import pandas as pd

from market_ai_hub.providers.base import BaseProvider, ProviderError, ProviderInfo, ProviderStatus
from market_ai_hub.providers.http_client import RateLimitedClient

log = logging.getLogger(__name__)

DAILY_URL = "https://www.taifex.com.tw/cht/3/dlFutDataDown"
TAS_URL = "https://www.taifex.com.tw/cht/3/dlFutDataDown"

DAILY_REQUIRED_COLUMNS = {
    "交易日期",
    "契約",
    "到期月份(週別)",
    "收盤價",
    "結算價",
    "交易時段",
}


@dataclass(frozen=True)
class TaifexDailySnapshot:
    """One content-addressed TAIFEX official daily download receipt."""

    frame: pd.DataFrame
    commodity: str
    query_start: str
    query_end: str
    received_at: datetime
    source_snapshot_id: str


def _parse_query_date(value: str) -> date:
    try:
        return datetime.strptime(str(value), "%Y/%m/%d").date()
    except ValueError as exc:
        raise ProviderError(f"taifex date must be YYYY/MM/DD: {value!r}") from exc


def _one_month_after(value: date) -> date:
    year = value.year + (1 if value.month == 12 else 0)
    month = 1 if value.month == 12 else value.month + 1
    day = min(value.day, monthrange(year, month)[1])
    return date(year, month, day)


def _validate_daily_range(start: str, end: str) -> tuple[str, str]:
    start_date = _parse_query_date(start)
    end_date = _parse_query_date(end)
    if end_date < start_date:
        raise ProviderError("taifex daily range end precedes start")
    if end_date > _one_month_after(start_date):
        raise ProviderError("taifex daily download range exceeds official one-month limit")
    return start_date.strftime("%Y/%m/%d"), end_date.strftime("%Y/%m/%d")


def _parse_daily_csv(body: str) -> pd.DataFrame:
    text = str(body or "")
    prefix = text.lstrip()[:256].lower()
    if not text.strip():
        raise ProviderError("taifex returned empty daily body")
    if prefix.startswith("<!doctype") or prefix.startswith("<html") or "<script" in prefix:
        raise ProviderError("taifex returned HTML instead of daily CSV")

    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        raise ProviderError("taifex daily CSV has no rows")
    header = [str(x).strip() for x in rows[0]]
    if not DAILY_REQUIRED_COLUMNS <= set(header):
        raise ProviderError(
            "taifex daily CSV schema mismatch: missing "
            + ",".join(sorted(DAILY_REQUIRED_COLUMNS - set(header)))
        )

    normalized: list[list[str]] = []
    for line_no, raw in enumerate(rows[1:], start=2):
        row = [str(x).strip() for x in raw]
        if not any(row):
            continue
        while len(row) > len(header) and row and row[-1] == "":
            row.pop()
        if len(row) != len(header):
            raise ProviderError(
                f"taifex daily CSV row {line_no} field count {len(row)} != header {len(header)}"
            )
        normalized.append(row)
    if not normalized:
        raise ProviderError("taifex returned no daily data rows")
    return pd.DataFrame(normalized, columns=header)


def _snapshot_id(*, commodity: str, start: str, end: str, body: str) -> str:
    payload = f"{commodity}|{start}|{end}|".encode("utf-8") + body.encode("utf-8")
    return "taifex-daily:" + hashlib.sha256(payload).hexdigest()[:32]


class TaifexProvider(BaseProvider):
    name = "taifex"

    def __init__(self) -> None:
        self.client = RateLimitedClient(self.name, max_retries=3, default_ttl=86400)

    def status(self) -> ProviderInfo:
        return ProviderInfo(name=self.name, status=ProviderStatus.OK, message="TAIFEX 官方；期貨日資料 + 近30日 T&S")

    def fetch_daily_snapshot(
        self,
        commodity: str = "TX",
        start: str = "",
        end: str = "",
    ) -> TaifexDailySnapshot:
        """Fetch one official daily CSV window and bind content to observed receipt time.

        TAIFEX limits a query window to one month. Historical rows do not carry
        publication timestamps, so received_at is the actual cache/fetch receipt
        time; callers must never reinterpret it as trading-date publication time.
        """
        now = datetime.now(timezone.utc)
        start = start or (now - timedelta(days=28)).strftime("%Y/%m/%d")
        end = end or now.strftime("%Y/%m/%d")
        start, end = _validate_daily_range(start, end)
        commodity = str(commodity or "").strip().upper()
        if not commodity:
            raise ProviderError("taifex commodity is required")
        key = f"daily_{commodity}_{start}_{end}"
        body = self.client.post(
            key,
            DAILY_URL,
            data={
                "down_type": "1",
                "queryStartDate": start,
                "queryEndDate": end,
                "commodity_id": commodity,
            },
        )
        frame = _parse_daily_csv(body)
        cache_path = self.client._cache_path(key)
        received_at = (
            datetime.fromtimestamp(cache_path.stat().st_mtime, tz=timezone.utc)
            if cache_path.exists()
            else datetime.now(timezone.utc)
        )
        return TaifexDailySnapshot(
            frame=frame,
            commodity=commodity,
            query_start=start,
            query_end=end,
            received_at=received_at,
            source_snapshot_id=_snapshot_id(
                commodity=commodity,
                start=start,
                end=end,
                body=body,
            ),
        )

    def fetch_daily(self, commodity: str = "TX", start: str = "", end: str = "") -> pd.DataFrame:
        """期貨日資料；保留既有 DataFrame API，但改用 fail-closed snapshot parser。"""
        return self.fetch_daily_snapshot(commodity, start=start, end=end).frame.copy()

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
