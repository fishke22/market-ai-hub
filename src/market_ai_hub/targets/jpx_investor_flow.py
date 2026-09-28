"""JPX Trading by Type of Investor — official weekly receipt-time context.

JPX changed the public derivative investor-flow format on 2026-04-23. The
consolidated weekly CSV exposes product/investor codes. Nikkei 225 Micro
Futures is product type 331, verified by reconciling the official weekly PDF
totals against the CSV rows for the same period.

This provider is deliberately receipt-time only: JPX does not expose an exact
publication timestamp in the CSV, so available_at is the retrieval time.
It must not be used to backfill earlier origins as historical PIT evidence.
"""
from __future__ import annotations

import io
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from urllib.parse import urljoin

import httpx
import pandas as pd
from pydantic import BaseModel

INVESTOR_TYPES = ["foreign", "domestic_individual", "domestic_institutional", "proprietary"]
JPX_INVESTOR_FLOW_SCHEMA_VERSION = "JPX_INVESTOR_FLOW_20260423_V1"
JPX_INVESTOR_FLOW_INDEX_URL = (
    "https://www.jpx.co.jp/english/markets/statistics-derivatives/sector/index.html"
)
NIKKEI225_MICRO_PRODUCT_CODE = "331"
NIKKEI225_MICRO_PRODUCT_NAME = "Nikkei 225 Micro Futures"

_VERIFIED_INVESTOR_CODE_LABELS = {
    "11": "securities_companies",
    "32": "business_companies",
    "33": "other_institutions",
    "51": "individuals",
    "60": "foreigners",
}
_OFFICIAL_COLUMNS = {
    "帳票種別 Product type",
    "サイクル区分 Cycle",
    "年月週 Year, Month, Week",
    "報告年月日（自）Period covered - from",
    "報告年月日（至）Period covered - to",
    "投資部門コード Type of Investor",
    "数量金額区分 Volume/Value",
    "売 Sales",
    "売-差引 Balance",
    "買 Purchases",
    "買-差引 Balance",
    "合計 Total",
}


class InvestorFlowRow(BaseModel):
    period: str
    product: str
    product_aggregation: str = ""
    product_code: str = ""
    investor_type: str
    investor_code: str = ""
    buy_volume: float
    sell_volume: float
    net_volume: float
    published_at: str = ""
    available_at: str = ""
    availability_semantics: str = ""
    source_url: str = ""
    source_schema_version: str = ""


def parse_investor_flow_csv(raw_text: str) -> list[InvestorFlowRow]:
    """Backward-compatible normalized CSV parser used by existing fixtures."""
    df = pd.read_csv(io.StringIO(raw_text))
    rows: list[InvestorFlowRow] = []
    for _, r in df.iterrows():
        buy = float(r.get("buy_volume", 0))
        sell = float(r.get("sell_volume", 0))
        product = str(r.get("product", ""))
        aggregation = "" if "Micro" in product else product
        rows.append(
            InvestorFlowRow(
                period=str(r.get("period", "")),
                product=product,
                product_aggregation=aggregation,
                investor_type=str(r.get("investor_type", "")),
                buy_volume=buy,
                sell_volume=sell,
                net_volume=buy - sell,
                published_at=str(r.get("published_at", "")),
                available_at=str(r.get("available_at", "")),
            )
        )
    return rows


def parse_jpx_2026_investor_flow_csv(
    raw_text: str,
    *,
    source_url: str,
    retrieved_at: datetime,
) -> list[InvestorFlowRow]:
    """Parse the official post-2026-04-23 weekly CSV for Nikkei 225 Micro."""
    if retrieved_at.tzinfo is None:
        raise ValueError("retrieved_at must be timezone-aware")
    retrieved = retrieved_at.astimezone(timezone.utc)
    df = pd.read_csv(io.StringIO(raw_text))
    missing = _OFFICIAL_COLUMNS - set(df.columns)
    if missing:
        raise ValueError(f"JPX investor-flow schema mismatch: missing {sorted(missing)}")
    product_col = "帳票種別 Product type"
    investor_col = "投資部門コード Type of Investor"
    vv_col = "数量金額区分 Volume/Value"
    from_col = "報告年月日（自）Period covered - from"
    to_col = "報告年月日（至）Period covered - to"
    sales_col = "売 Sales"
    purchases_col = "買 Purchases"

    micro = df[
        (df[product_col].astype(str) == NIKKEI225_MICRO_PRODUCT_CODE)
        & (df[vv_col].astype(str) == "1")
    ].copy()
    if micro.empty:
        raise ValueError("JPX investor-flow CSV missing Nikkei 225 Micro product 331")

    rows: list[InvestorFlowRow] = []
    for _, item in micro.iterrows():
        start_raw = str(item[from_col]).strip()
        end_raw = str(item[to_col]).strip()
        if not (re.fullmatch(r"\d{8}", start_raw) and re.fullmatch(r"\d{8}", end_raw)):
            raise ValueError("JPX investor-flow period format changed")
        end_date = datetime.strptime(end_raw, "%Y%m%d").date()
        if end_date > retrieved.date():
            raise ValueError("JPX investor-flow future period relative to retrieval")
        investor_code = str(item[investor_col]).strip()
        buy = float(item[purchases_col])
        sell = float(item[sales_col])
        rows.append(
            InvestorFlowRow(
                period=f"{start_raw}/{end_raw}",
                product=NIKKEI225_MICRO_PRODUCT_NAME,
                product_code=NIKKEI225_MICRO_PRODUCT_CODE,
                investor_type=_VERIFIED_INVESTOR_CODE_LABELS.get(
                    investor_code, f"JPX_INVESTOR_CODE_{investor_code}"
                ),
                investor_code=investor_code,
                buy_volume=buy,
                sell_volume=sell,
                net_volume=buy - sell,
                published_at="",
                available_at=retrieved.isoformat(),
                availability_semantics="RECEIPT_TIME_ONLY_PUBLICATION_TIMESTAMP_UNVERIFIED",
                source_url=source_url,
                source_schema_version=JPX_INVESTOR_FLOW_SCHEMA_VERSION,
            )
        )
    return rows


class _WeeklyCsvLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[tuple[str, str, str]] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag.lower() != "a":
            return
        href = dict(attrs).get("href", "")
        match = re.search(r"Tousi_DV_W_(\d{8})_(\d{8})\.csv$", href)
        if match:
            self.links.append((href, match.group(1), match.group(2)))


class JPXInvestorFlowProvider:
    """Public JPX weekly investor-flow context, receipt-time causal only."""

    status = "AVAILABLE_OFFICIAL_WEEKLY_RECEIPT_TIME"

    def __init__(self, timeout: float = 20.0) -> None:
        self.timeout = timeout

    def _get_text(self, url: str) -> str:
        response = httpx.get(url, timeout=self.timeout)
        response.raise_for_status()
        return response.content.decode("utf-8-sig")

    def discover_latest_weekly_csv(self) -> str:
        html = self._get_text(JPX_INVESTOR_FLOW_INDEX_URL)
        parser = _WeeklyCsvLinkParser()
        parser.feed(html)
        if not parser.links:
            raise RuntimeError("JPX weekly investor-flow CSV link not found")
        href, _, _ = max(parser.links, key=lambda item: (item[2], item[1]))
        return urljoin(JPX_INVESTOR_FLOW_INDEX_URL, href)

    def fetch(
        self,
        *,
        source_url: str | None = None,
        retrieved_at: datetime | None = None,
    ) -> list[InvestorFlowRow]:
        retrieval = retrieved_at or datetime.now(timezone.utc)
        if retrieval.tzinfo is None:
            raise ValueError("retrieved_at must be timezone-aware")
        url = source_url or self.discover_latest_weekly_csv()
        raw_text = self._get_text(url)
        return parse_jpx_2026_investor_flow_csv(
            raw_text,
            source_url=url,
            retrieved_at=retrieval,
        )
