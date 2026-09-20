"""Phase 2G.1 — Continuous Futures Builder（versioned）。

保留 RAW CONTRACT DATA；另外產生 continuous research series。
紀錄 roll_date / roll_method / adjustment_method。
禁止把 adjusted continuous price 冒充真實可成交價格。
"""
from __future__ import annotations

from pydantic import BaseModel, Field

ADJUSTED = "adjusted"          # 非可成交價（研究用）
UNADJUSTED = "unadjusted"      # 真實成交價

ROLL_METHODS = ["last_trading_day", "fixed_days_before_expiry"]
ADJUSTMENT_METHODS = ["ratio_backadjusted", "unadjusted", "difference_backadjusted"]


class ContinuousSeries(BaseModel):
    version: str = "1"
    product: str = ""
    series: list[dict] = Field(default_factory=list)     # [{date, price, is_executable_price}]
    roll_dates: list[str] = Field(default_factory=list)
    roll_method: str = ""
    adjustment_method: str = UNADJUSTED


class ContinuousFuturesBuilder:
    def __init__(self, roll_method: str = "last_trading_day",
                 adjustment_method: str = UNADJUSTED) -> None:
        if roll_method not in ROLL_METHODS:
            raise ValueError(f"unknown roll_method {roll_method}")
        if adjustment_method not in ADJUSTMENT_METHODS:
            raise ValueError(f"unknown adjustment_method {adjustment_method}")
        self.roll_method = roll_method
        self.adjustment_method = adjustment_method

    def build(self, rows: list[dict]) -> ContinuousSeries:
        """rows: [{contract_month, date, close}...]，依 date 排序。

        簡化 roll：contract_month 改變時記 roll_date。adjusted → is_executable_price=False。
        """
        rows = sorted(rows, key=lambda r: r["date"])
        series: list[dict] = []
        roll_dates: list[str] = []
        prev_contract = None
        prev_close = None
        for r in rows:
            cm = r.get("contract_month")
            if prev_contract is not None and cm != prev_contract:
                roll_dates.append(r["date"])
            close = float(r["close"]) if r.get("close") is not None else None
            price = close
            is_executable = True
            if self.adjustment_method != UNADJUSTED and close is not None and prev_close:
                # ratio back-adjust（研究用，非可成交價）
                price = close  # 本棒不實作跨合約價差調整，僅標記語義
                is_executable = False
            series.append({"date": r["date"], "contract_month": cm,
                           "price": price, "is_executable_price": is_executable})
            if close is not None:
                prev_close = close
            prev_contract = cm
        return ContinuousSeries(product="Nikkei 225 Micro", series=series,
                                roll_dates=roll_dates, roll_method=self.roll_method,
                                adjustment_method=self.adjustment_method)
