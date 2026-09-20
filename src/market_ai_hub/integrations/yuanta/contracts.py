"""Phase 2Y-A — Yuanta contracts（instrument / capability / market enum / recorder）。"""
from __future__ import annotations

from pydantic import BaseModel, Field

# 市場 enum（實際由 FunctionList.xlsx 市場類 sheet 確認；runtime 需再由 DLL enum 複核）
MARKET_TYPE = {
    "TWSE": 1, "TWOTC": 2, "TAIFEX": 3, "TWEMERGING": 4,
    "TWSEODD": 5, "TWOTCODD": 6,
    "SGX": 202, "CME": 203, "CBOT": 204, "TCE": 205, "OSE": 207,
}
OSE_MARKET_TYPE = 207


class YuantaInstrument(BaseModel):
    logical_instrument: str
    market_type: int | None = None
    spark_code: str = ""
    display_name: str = ""
    source: str = ""           # FunctionList / vendor doc / (未來) login
    verified: bool = False
    verified_at: str = ""


class YuantaCapability(BaseModel):
    name: str
    status: str = "UNKNOWN"     # SUPPORTED_BY_API / UNKNOWN / ...（不因 method 存在就標 SUPPORTED_BY_ACCOUNT）
    note: str = ""


class YuantaRecorderContract:
    """realtime recorder interface。現在 DISABLED_BY_POLICY（不做長時間 recorder）。"""

    enabled = False
    policy = "DISABLED_BY_POLICY"
    supported_streams = ["StockTick", "FiveTick", "Watchlist"]
