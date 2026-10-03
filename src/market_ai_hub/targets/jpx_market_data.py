"""Phase 2G.2 — JPX Market Data（whole_day xlsx 成交量 / open_interest xlsx 建玉）。

真實檔案結構（2026-09-18 實測）：
- derivatives_market_data_whole_day.xlsx → sheet `market_data_Futures`
  欄位：A=exchange, B=category, C=商品名(日/英), D=session, E=volume, F=J-NET vol, G=value, H=J-NET value
- open_interest.xlsx → sheet `デリバティブ建玉残高状況`（per-contract-month volume + OI）
"""
from __future__ import annotations

import hashlib
import io
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from pydantic import BaseModel

from market_ai_hub.targets.jpx_daily import atomic_write

# 2026-10-03 實測：open_interest.xlsx 的正確路徑 token 是 t13vrt0000026aes-att
# （tvdivq00000014nn-att 已失效，會回 404 HTML）。whole_day xlsx 的現行公開路徑
# 尚未實測；fetch_whole_day 在路徑核實前不該被當成可靠的成交量來源。
MARKET_BASE = "https://www.jpx.co.jp/markets/derivatives/trading-volume/t13vrt0000026aes-att"

SESSION_MAP = {"夜間": "night", "前場": "morning", "後場": "afternoon", "合計": "total"}

PRODUCT_EN = {
    "マイクロ": "Nikkei 225 Micro Futures",
    "Nikkei 225 Micro Futures": "Nikkei 225 Micro Futures",
    "Nikkei 225 mini": "Nikkei 225 mini",
    "Nikkei 225 Futures": "Nikkei 225 Futures",
    "日経225先物": "Nikkei 225 Futures",
    "TOPIX": "TOPIX Futures",
}


class ProductVolume(BaseModel):
    product: str
    session: str
    volume: float | None = None
    value: float | None = None
    date: str = ""
    source_url: str = ""


class ContractOI(BaseModel):
    product: str
    contract_month: str
    volume: int | None = None
    open_interest: int | None = None
    oi_change: int | None = None
    date: str = ""
    source_url: str = ""


def _f(v):
    if v is None or v == "" or v == "－":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _i(v):
    f = _f(v)
    return int(f) if f is not None else None


def _product_en(cell: str) -> str | None:
    if not cell:
        return None
    en = cell.split("\n")[-1].strip()
    if "Micro" in en:
        return "Nikkei 225 Micro Futures"
    if "mini" in en:
        return "Nikkei 225 mini"
    if "Nikkei 225 Futures" in en:
        return "Nikkei 225 Futures"
    if "TOPIX" in en:
        return "TOPIX Futures"
    return None


def _session(cell: str) -> str | None:
    if not cell:
        return None
    for jp, en in SESSION_MAP.items():
        if jp in cell:
            return en
    return None


def parse_whole_day_volumes(xlsx_bytes: bytes, date: str = "", source_url: str = "") -> list[ProductVolume]:
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes), data_only=True)
    ws = wb["market_data_Futures"]
    out: list[ProductVolume] = []
    current = None
    for row in ws.iter_rows(values_only=True):
        c = row[2] if len(row) > 2 else None
        d = row[3] if len(row) > 3 else None
        e = row[4] if len(row) > 4 else None
        g = row[6] if len(row) > 6 else None
        if c and str(c).strip():
            p = _product_en(str(c))
            if p:
                current = p
        if d and str(d).strip() and current:
            sess = _session(str(d))
            if sess:
                out.append(ProductVolume(product=current, session=sess, volume=_f(e),
                                         value=_f(g), date=date, source_url=source_url))
    return out


# 凍結解析規則 W3.4-OI-1（2026-10-03 以 20261002open_interest.xlsx 實測驗證）：
#   sheet = デリバティブ建玉残高状況；只用「右欄帶」（column index 7-11）。
#   col7 = 產品名（僅區塊第一列有值；「日経225マイクロ」= Micro 區塊開頭）
#   col8 = 限月 token（YYYY年M月限）或「合計」（區塊結束）
#   col9 = 取引高（成交量）／col10 = 当日建玉残高／col11 = 前日比
#   驗證：2026-10-02 檔 Micro 區塊 202610=75668, 202611=2028, 202612=861495,
#   202703=10439，與官方合計列 949630 完全相符。
OI_BAND_PRODUCT_COL = 7
OI_BAND_MONTH_COL = 8
OI_BAND_VOLUME_COL = 9
OI_BAND_OI_COL = 10
OI_BAND_CHANGE_COL = 11


def parse_open_interest(xlsx_bytes: bytes, date: str = "", source_url: str = "",
                        product: str | None = None) -> list[ContractOI]:
    """依 W3.4-OI-1 凍結規則解析 open_interest.xlsx 的 per-contract volume + OI。

    - 只讀右欄帶（col 7-11）；產品記號不認識時立即停止歸屬（不會把
      ミニTOPIX 等其他產品的月份列誤歸到日經產品）。
    - (product, contract_month) 只取檔案內第一次出現。
    - `product` 傳入時只回傳該產品的列（如 Nikkei 225 Micro Futures）。
    """
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(xlsx_bytes), data_only=True)
    ws = wb["デリバティブ建玉残高状況"]
    out: list[ContractOI] = []

    def cell(i: int):
        return row[i] if len(row) > i else None

    current: str | None = None
    seen: set[tuple[str, str]] = set()
    for row in ws.iter_rows(values_only=True):
        marker = str(cell(OI_BAND_PRODUCT_COL)).strip() if cell(OI_BAND_PRODUCT_COL) else ""
        if marker:
            current = _nikkei_product(marker)  # 不認識 → None，停止歸屬
        if current is None:
            continue
        month_cell = str(cell(OI_BAND_MONTH_COL)).strip() if cell(OI_BAND_MONTH_COL) else ""
        if not month_cell:
            continue
        if month_cell == "合計":
            current = None
            continue
        month = _contract_month(month_cell)
        if month is None:
            continue
        if (current, month) in seen:
            continue
        seen.add((current, month))
        if product is not None and current != product:
            continue
        out.append(ContractOI(
            product=current,
            contract_month=month,
            volume=_i(cell(OI_BAND_VOLUME_COL)),
            open_interest=_i(cell(OI_BAND_OI_COL)),
            oi_change=_i(cell(OI_BAND_CHANGE_COL)),
            date=date,
            source_url=source_url,
        ))
    return out


def _nikkei_product(cell: str) -> str | None:
    if "日経225マイクロ" in cell or "Nikkei 225 Micro" in cell:
        return "Nikkei 225 Micro Futures"
    if "日経225mini" in cell:
        return "Nikkei 225 mini"
    if "日経225" in cell and "月限" not in cell:
        return "Nikkei 225 Futures"
    return None


def _is_non_nikkei_header(cell: str) -> bool:
    if "月限" in cell:
        return False
    return ("先物" in cell or "Futures" in cell or "オプション" in cell or "Options" in cell)


def _contract_month(cell: str) -> str | None:
    """「2026年12月限」→ 「202612」."""
    import re
    m = re.search(r"(\d{4})年(\d{1,2})月限", cell)
    if not m:
        return None
    return f"{int(m.group(1)):04d}{int(m.group(2)):02d}"


class JPXMarketDataProvider:
    def __init__(self, data_root: Path | None = None) -> None:
        from market_ai_hub.automation.data_lake import DataLakeManager
        self.lake = DataLakeManager(data_root)

    def whole_day_url(self, d: str) -> str:
        return f"{MARKET_BASE}/{d}_derivatives_market_data_whole_day.xlsx"

    def open_interest_url(self, d: str) -> str:
        return f"{MARKET_BASE}/{d}open_interest.xlsx"

    def fetch_whole_day(self, d: str, getter=None) -> list[ProductVolume]:
        if getter is None:
            import httpx
            def getter(u):
                return httpx.get(u, timeout=30, follow_redirects=True).content
        raw = getter(self.whole_day_url(d))
        return parse_whole_day_volumes(raw, date=d, source_url=self.whole_day_url(d))

    def fetch_open_interest(self, d: str, getter=None,
                            product: str | None = None) -> list[ContractOI]:
        if getter is None:
            import httpx
            def getter(u):
                return httpx.get(u, timeout=30, follow_redirects=True).content
        raw = getter(self.open_interest_url(d))
        return parse_open_interest(raw, date=d, source_url=self.open_interest_url(d),
                                   product=product)

    def save_open_interest(self, d: str, rows: list[ContractOI]) -> Path:
        df = pd.DataFrame([r.model_dump() for r in rows])
        path = self.lake.raw_path("jpx", "open_interest", "OSE", "all",
                                  int(d[:4]), int(d[4:6]), f"open_interest_{d}.parquet")
        atomic_write(path, df.to_parquet(index=False))
        return path

    def open_interest_path(self, d: str) -> Path:
        return self.lake.raw_path("jpx", "open_interest", "OSE", "all",
                                  int(d[:4]), int(d[4:6]), f"open_interest_{d}.parquet")
