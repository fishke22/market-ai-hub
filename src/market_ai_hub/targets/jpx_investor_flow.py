"""Phase 2G.2 — JPX Trading by Type of Investors（Investor Flow）。

優先官方 CSV。本棒未在 participant-volume 頁發現直接 CSV 連結 → CONTRACT_ONLY。
若資料粒度不足以單獨辨識 Micro，必須標示實際 product aggregation，不得錯稱 Micro-specific flow。
"""
from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path

import pandas as pd
from pydantic import BaseModel

INVESTOR_TYPES = ["foreign", "domestic_individual", "domestic_institutional", "proprietary"]


class InvestorFlowRow(BaseModel):
    period: str
    product: str
    product_aggregation: str = ""   # 若不能單獨辨識 Micro，標實際 aggregation
    investor_type: str
    buy_volume: float
    sell_volume: float
    net_volume: float
    published_at: str = ""
    available_at: str = ""


def parse_investor_flow_csv(raw_text: str) -> list[InvestorFlowRow]:
    """解析官方 investor flow CSV（欄位：period,product,investor_type,buy,sell,published_at）。"""
    df = pd.read_csv(io.StringIO(raw_text))
    rows: list[InvestorFlowRow] = []
    for _, r in df.iterrows():
        buy = float(r.get("buy_volume", 0))
        sell = float(r.get("sell_volume", 0))
        product = str(r.get("product", ""))
        # 若 product 是 aggregate（如「Nikkei 225 系」）而非單獨 Micro，標記
        aggregation = "" if "Micro" in product else product
        rows.append(InvestorFlowRow(
            period=str(r.get("period", "")), product=product,
            product_aggregation=aggregation, investor_type=str(r.get("investor_type", "")),
            buy_volume=buy, sell_volume=sell, net_volume=buy - sell,
            published_at=str(r.get("published_at", "")), available_at=str(r.get("available_at", "")),
        ))
    return rows


class JPXInvestorFlowProvider:
    """CONTRACT_ONLY：尚未接實網（官方 CSV URL 待確認）。"""

    status = "CONTRACT_ONLY"

    def fetch(self, *args, **kwargs) -> list[InvestorFlowRow]:
        raise NotImplementedError("JPX investor flow CSV URL not yet wired (CONTRACT_ONLY)")
