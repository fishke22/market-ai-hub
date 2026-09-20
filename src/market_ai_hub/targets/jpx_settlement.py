"""Phase 2G.2 — JPX Settlement CSV Provider（官方 rbYYYYMMDD.csv）。

與 Daily Report OHLC 分開保存；settlement 不得誤當 OHLC close。
產品 token：
  FUT_225   = Nikkei 225 Futures (Large)
  FUT_225M  = Nikkei 225 mini
  FUT_225MC = Nikkei 225 Micro Futures
"""
from __future__ import annotations

import hashlib
import io
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from pydantic import BaseModel

from market_ai_hub.targets.jpx_daily import atomic_write

PRODUCT_TOKENS = {
    "FUT_225MC": "Nikkei 225 Micro Futures",
    "FUT_225M": "Nikkei 225 mini",
    "FUT_225": "Nikkei 225 Futures",
}

SETTLEMENT_BASE = "https://www.jpx.co.jp/markets/derivatives/settlement-price/tvdivq00000014l6-att"


class SettlementRow(BaseModel):
    contract: str
    product: str
    settlement_price: float
    final_settlement_price: float | None = None
    date: str = ""
    source_url: str = ""
    source_hash: str = ""


def parse_settlement_csv(raw_text: str, date: str = "", source_url: str = "",
                         encoding: str = "shift_jis") -> list[SettlementRow]:
    """解析 rbYYYYMMDD.csv。欄位：銘柄コード,銘柄名称,PUT/CAL,限月,権利行使価格,清算価格,...

    官方 CSV 前有注記行（＊…）與空行，需定位到含「銘柄コード」的 header 行。
    """
    import codecs
    text = raw_text
    if isinstance(raw_text, bytes):
        text = raw_text.decode(encoding, "replace")
    lines = text.splitlines()
    header_idx = None
    for i, ln in enumerate(lines):
        if "銘柄コード" in ln:
            header_idx = i
            break
    if header_idx is None:
        return []
    df = pd.read_csv(io.StringIO("\n".join(lines[header_idx:])))
    rows: list[SettlementRow] = []
    for _, r in df.iterrows():
        name = str(r.get("銘柄名称", "")).strip()
        token = ""
        for t in ("FUT_225MC", "FUT_225M", "FUT_225"):
            if name.startswith(t + "_"):
                token = t
                break
        if token not in PRODUCT_TOKENS:
            continue
        contract = str(r.get("限月", "")).strip()
        settle = _f(r.get("清算価格"))
        if settle is None:
            continue
        payload = f"{name}|{contract}|{settle}"
        rows.append(SettlementRow(
            contract=contract, product=PRODUCT_TOKENS[token],
            settlement_price=settle, final_settlement_price=None,
            date=date, source_url=source_url,
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


class JPXSettlementProvider:
    def __init__(self, data_root: Path | None = None) -> None:
        from market_ai_hub.automation.data_lake import DataLakeManager
        self.lake = DataLakeManager(data_root)

    def url_for(self, d: str) -> str:
        return f"{SETTLEMENT_BASE}/rb{d}.csv"

    def fetch_parse(self, d: str, getter=None) -> list[SettlementRow]:
        """d = YYYYMMDD。getter 可注入（mock/網路）。"""
        if getter is None:
            import httpx
            def getter(u):
                return httpx.get(u, timeout=30, follow_redirects=True).content
        raw = getter(self.url_for(d))
        return parse_settlement_csv(raw, date=d, source_url=self.url_for(d))

    def save(self, d: str, rows: list[SettlementRow]) -> Path:
        df = pd.DataFrame([r.model_dump() for r in rows])
        path = self.lake.raw_path("jpx", "settlement", "OSE", "all",
                                  int(d[:4]), int(d[4:6]), f"rb{d}.parquet")
        atomic_write(path, df.to_parquet(index=False))
        return path
