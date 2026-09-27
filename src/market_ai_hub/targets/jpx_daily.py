"""Phase 2G.1 — JPX OSE Daily Report Provider（Micro / Mini / Large）。

解析指數期貨 daily report；incremental archive downloader。
Micro 歷史從實際可取得日期（2023-05-29）開始，不得製造更早的 Micro 資料。
"""
from __future__ import annotations

import hashlib
import io
import re
import zipfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable

import pandas as pd
from pydantic import BaseModel

from market_ai_hub.automation.incremental import atomic_write
from market_ai_hub.targets.contract import TARGET, REFERENCE

# Micro 上市日（實際可取得日期）
MICRO_LISTING_DATE = date(2023, 5, 29)

JPX_PUBLIC_BASE = "https://www.jpx.co.jp"
JPX_DAILY_JSON_BASE = JPX_PUBLIC_BASE + "/automation/markets/statistics-derivatives/daily/json"

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


class PublicDailyReportError(RuntimeError):
    """Public JPX daily-report archive could not be fetched or parsed."""


def _http_bytes(url: str) -> bytes:
    import httpx
    r = httpx.get(url, timeout=45, follow_redirects=True)
    r.raise_for_status()
    return r.content


def _http_json(url: str) -> dict:
    import json
    return json.loads(_http_bytes(url).decode("utf-8"))


def public_daily_report_index(month: str, getter_json=None) -> list[dict]:
    """Return the JPX public OSE daily-report index for YYYYMM."""
    if not re.fullmatch(r"\d{6}", str(month)):
        raise ValueError("month must be YYYYMM")
    getter_json = getter_json or _http_json
    url = f"{JPX_DAILY_JSON_BASE}/daily_report_{month}.json"
    data = getter_json(url)
    rows = data.get("TableDatas", []) if isinstance(data, dict) else []
    out = []
    for row in rows:
        d = str(row.get("TradeDate", "") or "")
        z = str(row.get("OseAll", "") or "")
        if re.fullmatch(r"\d{8}", d) and z:
            out.append({"trade_date": d, "zip_url": z if z.startswith("http") else JPX_PUBLIC_BASE + z})
    return out


def public_daily_report_months(getter_json=None) -> list[str]:
    """Discover publicly listed current-system archive months."""
    getter_json = getter_json or _http_json
    url = f"{JPX_DAILY_JSON_BASE}/daily_report_monthlylist.json"
    data = getter_json(url)
    months = []
    for row in (data.get("TableDatas", []) if isinstance(data, dict) else []):
        m = str(row.get("Month", "") or "")
        if re.fullmatch(r"\d{6}", m):
            months.append(m)
    return sorted(set(months))


def _number(text: str) -> float | None:
    t = str(text or "").replace(",", "").replace("…", "").strip()
    if not t or t in {"-", "－"}:
        return None
    try:
        return float(t)
    except ValueError:
        return None


def parse_micro_settlement_layout(
    layout_text: str,
    *,
    trade_date: str,
    source_url: str = "",
    source_hash: str = "",
) -> list[OSEDailyRow]:
    """Parse the verified Auction Market Micro rows from pypdf layout text.

    Only contract month and official settlement are promoted. The multiple intraday
    OHLC blocks in the PDF are intentionally left unset until separately contracted.
    """
    if not re.fullmatch(r"\d{8}", trade_date):
        raise ValueError("trade_date must be YYYYMMDD")
    lines = [ln.strip() for ln in str(layout_text or "").splitlines() if ln.strip()]
    has_auction = any("Auction Market" in ln for ln in lines)
    title_idx = next(
        (i for i, ln in enumerate(lines) if ln.startswith("Nikkei 225 Micro Futures")),
        None,
    )
    if not has_auction or title_idx is None:
        return []
    start = title_idx + 1
    out: list[OSEDailyRow] = []
    for line in lines[start:]:
        if line.startswith("+") or line.startswith("Copyright"):
            if out:
                break
            continue
        if not re.match(r"^\d{6}\s", line):
            continue
        cols = re.split(r"\s{2,}", line.strip())
        if len(cols) < 16 or not re.fullmatch(r"\d{6}", cols[0]):
            continue
        settlement = _number(cols[15])
        if settlement is None or settlement <= 0:
            continue
        payload = f"{trade_date}|{cols[0]}|{settlement}|{source_hash}"
        out.append(OSEDailyRow(
            product="Nikkei 225 Micro",
            contract_month=cols[0],
            date=f"{trade_date[:4]}-{trade_date[4:6]}-{trade_date[6:8]}",
            settlement=settlement,
            source_url=source_url,
            source_hash=hashlib.sha256(payload.encode()).hexdigest()[:16],
        ))
    return out


def parse_micro_settlement_pdf(
    pdf_bytes: bytes,
    *,
    trade_date: str,
    source_url: str = "",
) -> list[OSEDailyRow]:
    """Extract Micro settlements from an official sif_dyr PDF.

    pypdf is loaded lazily. Missing optional parser fails closed and does not affect
    already materialized parquet data used by analysis.
    """
    try:
        import pypdf
    except Exception as exc:  # pragma: no cover - environment dependent
        raise PublicDailyReportError("PDF_PARSER_NOT_AVAILABLE") from exc

    pdf_hash = hashlib.sha256(pdf_bytes).hexdigest()
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    candidates: list[OSEDailyRow] = []
    for page in reader.pages:
        try:
            text = page.extract_text(extraction_mode="layout") or ""
        except TypeError:  # older compatible pypdf fallback
            text = page.extract_text() or ""
        if "Nikkei 225 Micro Futures" not in text or "Auction Market" not in text:
            continue
        rows = parse_micro_settlement_layout(
            text, trade_date=trade_date, source_url=source_url, source_hash=pdf_hash,
        )
        if rows:
            candidates.extend(rows)
            break
    return candidates


def parse_micro_settlement_zip(
    zip_bytes: bytes,
    *,
    trade_date: str,
    source_url: str = "",
) -> list[OSEDailyRow]:
    """Extract sif_dyr_YYYYMMDD.pdf from the official OSE daily-report ZIP."""
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        wanted = f"sif_dyr_{trade_date}.pdf"
        names = zf.namelist()
        # Some JPX ZIPs place PDFs under a dated directory while most keep them at root.
        # Match by basename so archive packaging differences do not create false missing days.
        name = next(
            (
                n for n in names
                if Path(n).name.lower() == wanted.lower()
            ),
            "",
        )
        if not name:
            name = next(
                (
                    n for n in names
                    if Path(n).name.lower().startswith("sif_dyr_")
                    and Path(n).name.lower().endswith(".pdf")
                    and "flex" not in Path(n).name.lower()
                ),
                "",
            )
        if not name:
            raise PublicDailyReportError("INDEX_FUTURES_PDF_NOT_FOUND")
        return parse_micro_settlement_pdf(
            zf.read(name), trade_date=trade_date, source_url=source_url,
        )


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

    def fetch_public_day(
        self,
        trade_date: str,
        *,
        zip_url: str = "",
        getter_bytes=None,
        getter_json=None,
    ) -> list[OSEDailyRow]:
        """Fetch one public JPX OSE daily-report day and parse Micro settlements."""
        d = str(trade_date).replace("-", "")
        if not re.fullmatch(r"\d{8}", d):
            raise ValueError("trade_date must be YYYYMMDD")
        if not zip_url:
            recs = public_daily_report_index(d[:6], getter_json=getter_json)
            rec = next((x for x in recs if x["trade_date"] == d), None)
            if rec is None:
                return []
            zip_url = rec["zip_url"]
        getter_bytes = getter_bytes or _http_bytes
        raw = getter_bytes(zip_url)
        return parse_micro_settlement_zip(raw, trade_date=d, source_url=zip_url)

    def save_public_day(self, trade_date: str, rows: list[OSEDailyRow]) -> Path | None:
        """Persist a compact parsed daily file; never stores the multi-megabyte ZIP."""
        if not rows:
            return None
        d = str(trade_date).replace("-", "")
        df = pd.DataFrame([r.model_dump() for r in rows])
        path = self.lake.raw_path(
            "jpx", "ose_daily", "OSE", "Nikkei 225 Micro",
            int(d[:4]), int(d[4:6]), f"micro_settlement_{d}.parquet",
        )
        atomic_write(path, df.to_parquet(index=False))
        return path

    def sync_public_months(
        self,
        months: list[str],
        *,
        skip_existing: bool = True,
        getter_bytes=None,
        getter_json=None,
    ) -> dict:
        """Incrementally materialize public Micro settlement history for listed months."""
        written = 0
        skipped = 0
        missing = 0
        errors: list[str] = []
        for month in months:
            try:
                recs = public_daily_report_index(month, getter_json=getter_json)
            except Exception as exc:
                errors.append(f"{month}:INDEX:{type(exc).__name__}")
                continue
            for rec in recs:
                d = rec["trade_date"]
                existing = self.lake.raw_path(
                    "jpx", "ose_daily", "OSE", "Nikkei 225 Micro",
                    int(d[:4]), int(d[4:6]), f"micro_settlement_{d}.parquet",
                )
                if skip_existing and existing.exists():
                    skipped += 1
                    continue
                try:
                    rows = self.fetch_public_day(
                        d, zip_url=rec["zip_url"],
                        getter_bytes=getter_bytes, getter_json=getter_json,
                    )
                    if not rows:
                        missing += 1
                        continue
                    self.save_public_day(d, rows)
                    written += 1
                except Exception as exc:
                    errors.append(f"{d}:{type(exc).__name__}")
        return {
            "status": "OK" if not errors else "PARTIAL",
            "months": list(months),
            "written_days": written,
            "skipped_days": skipped,
            "missing_days": missing,
            "errors": errors,
        }

    def load(self, product: str = "Nikkei 225 Micro", data_root: Path | None = None) -> pd.DataFrame:
        from market_ai_hub.automation.data_lake import DataLakeManager
        lake = DataLakeManager(data_root)
        base = lake.root / "raw" / "jpx" / "ose_daily" / "OSE" / product
        if not base.exists():
            return pd.DataFrame()
        files = list(base.rglob("*.parquet"))
        if not files:
            return pd.DataFrame()
        return pd.concat([pd.read_parquet(p) for p in files], ignore_index=True)
