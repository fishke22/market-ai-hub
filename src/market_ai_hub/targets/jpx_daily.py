"""Phase 2G.1 — JPX OSE Daily Report Provider（Micro / Mini / Large）。

解析指數期貨 daily report；incremental archive downloader。
Micro 歷史從實際可取得日期（2023-05-29）開始，不得製造更早的 Micro 資料。
"""
from __future__ import annotations

import hashlib
import io
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable

import pandas as pd
from pydantic import BaseModel

from market_ai_hub.automation.incremental import atomic_write
from market_ai_hub.targets.contract import TARGET, REFERENCE

# Micro 上市日（實際可取得日期）
MICRO_LISTING_DATE = date(2023, 5, 29)

# 產品名稱 → 角色
PRODUCT_ROLES = {
    "Nikkei 225 Micro": TARGET,
    "Nikkei 225 Mini": REFERENCE,
    "Nikkei 225 Futures": REFERENCE,
}


class OSEDailyRow(BaseModel):
    product: str
    contract_month: str
    date: str
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    volume: int | None = None
    settlement: float | None = None
    source_url: str = ""
    source_hash: str = ""


class MicroListingError(Exception):
    """Micro 資料不得早於上市日（不得偽造）。"""


def assert_micro_not_before(d: str | date) -> None:
    d = date.fromisoformat(str(d)) if not isinstance(d, date) else d
    if d < MICRO_LISTING_DATE:
        raise MicroListingError(f"Micro data before {MICRO_LISTING_DATE} is not available (got {d})")


def parse_daily_report(raw_text: str, source_url: str = "") -> list[OSEDailyRow]:
    """解析 OSE daily report（CSV 子集）。

    預期欄位：product,contract_month,date,open,high,low,close,volume,settlement
    （可變欄位以最小集解析；缺欄位 → None）。Micro 早於上市日 → 跳過（不偽造）。
    """
    df = pd.read_csv(io.StringIO(raw_text))
    rows: list[OSEDailyRow] = []
    for _, r in df.iterrows():
        product = str(r.get("product", ""))
        d = str(r.get("date", ""))
        if product == "Nikkei 225 Micro":
            try:
                assert_micro_not_before(d)
            except MicroListingError:
                continue  # 不製造上市前 Micro
        if product not in PRODUCT_ROLES:
            continue
        payload = "|".join(str(r.get(c, "")) for c in ("product", "contract_month", "date",
                                                       "open", "high", "low", "close", "volume", "settlement"))
        rows.append(OSEDailyRow(
            product=product, contract_month=str(r.get("contract_month", "")), date=d,
            open=_f(r.get("open")), high=_f(r.get("high")), low=_f(r.get("low")),
            close=_f(r.get("close")), volume=_i(r.get("volume")), settlement=_f(r.get("settlement")),
            source_url=source_url,
            source_hash=hashlib.sha256(payload.encode()).hexdigest()[:16],
        ))
    return rows


def _f(v):
    if v is None or (isinstance(v, float) and pd.isna(v)) or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _i(v):
    if v is None or (isinstance(v, float) and pd.isna(v)) or v == "":
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


class JPXOSEDailyReportProvider:
    """JPX OSE daily report provider。fetcher 可注入（網路 / 本地檔案），測試可 mock。"""

    def __init__(self, data_root: Path | None = None) -> None:
        from market_ai_hub.automation.data_lake import DataLakeManager
        self.lake = DataLakeManager(data_root)

    def download_incremental(self, fetcher: Callable[[str, str], str],
                             start_date: str, end_date: str, product: str = "Nikkei 225 Micro") -> Path:
        """incremental archive downloader：抓 [start_date, end_date]，寫 parquet + manifest。

        fetcher(start_date, end_date) -> raw text（可 mock）。
        Micro 起點會 clamp 到 MICRO_LISTING_DATE。
        """
        if product == "Nikkei 225 Micro":
            s = max(date.fromisoformat(start_date), MICRO_LISTING_DATE).isoformat()
            if date.fromisoformat(end_date) < MICRO_LISTING_DATE:
                raise MicroListingError("requested Micro range entirely before listing")
        else:
            s = start_date
        raw = fetcher(s, end_date)
        rows = parse_daily_report(raw, source_url=f"JPX_OSE_{s}_{end_date}")
        df = pd.DataFrame([r.model_dump() for r in rows])
        filename = f"{product.replace(' ', '_').lower()}_{s}_{end_date}.parquet"
        path = self.lake.raw_path("jpx", "ose_daily", "OSE", product, int(s[:4]), int(s[5:7]), filename)
        atomic_write(path, df.to_parquet(index=False))
        return path

    def load(self, product: str = "Nikkei 225 Micro", data_root: Path | None = None) -> pd.DataFrame:
        from market_ai_hub.automation.data_lake import DataLakeManager
        lake = DataLakeManager(data_root)
        base = lake.root / "raw" / "jpx" / "ose_daily" / "OSE" / product
        if not base.exists():
            return pd.DataFrame()
        return pd.concat([pd.read_parquet(p) for p in base.rglob("*.parquet")], ignore_index=True)
