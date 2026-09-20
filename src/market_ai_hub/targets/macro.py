"""Phase 2G.2 — Official Macro providers（live connect）。

LIVE VERIFIED（本棒實測連線）：
  BLS Public API v2（POST）／Cboe VIX daily history（CSV）／SEC EDGAR（data.sec.gov，無 key）／BOJ（HTML）。
NEEDS_CONFIG / CONTRACT：
  BEA（免費 key）／Japan e-Stat（appId）／EIA（API key）／EDINET（config-only）／Fed（calendar 解析）/ MOF（HTML）。

不得把修訂後資料冒充當時可見值（release-time correctness 見 release_time.py）。
"""
from __future__ import annotations

import io
from datetime import datetime, timezone

import pandas as pd
from pydantic import BaseModel, Field

BLS_SERIES = {
    "CPI": "CUUR0000SA0",
    "Core CPI": "CUUR0000SA0L1E",
    "Employment": "CES0000000001",
    "Unemployment": "LNS14000000",
    "Average Hourly Earnings": "CES0500000003",
}


class MacroRelease(BaseModel):
    series_id: str
    period: str
    value: float
    release_timestamp: datetime | None = None
    available_at: datetime | None = None
    source: str = ""


class BLSProvider:
    """BLS Public API v2。POST；不需 key（本棒實測 200 OK）。"""

    url = "https://api.bls.gov/publicAPI/v2/timeseries/data/"

    def fetch(self, series_ids: list[str], start_year: str, end_year: str,
              post=None) -> list[MacroRelease]:
        import httpx
        if post is None:
            def post(u, json):
                return httpx.post(u, json=json, timeout=60, follow_redirects=True).json()
        data = post(self.url, {"seriesid": series_ids, "startyear": start_year, "endyear": end_year})
        out: list[MacroRelease] = []
        for s in data.get("Results", {}).get("series", []):
            sid = s.get("seriesID", "")
            for item in s.get("data", []):
                try:
                    val = float(item.get("value", "nan"))
                except (TypeError, ValueError):
                    continue
                out.append(MacroRelease(
                    series_id=sid, period=f"{item.get('year')}-{item.get('period')}",
                    value=val, source="BLS",
                ))
        return out


class CboeVixProvider:
    """Cboe VIX official daily history（CSV）。Yahoo 退為 fallback。"""

    url = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv"

    def fetch(self, getter=None) -> pd.DataFrame:
        import httpx
        if getter is None:
            def getter(u):
                return httpx.get(u, timeout=30, follow_redirects=True).content
        raw = getter(self.url)
        df = pd.read_csv(io.BytesIO(raw))
        df.columns = [c.strip().upper() for c in df.columns]
        df["Date"] = pd.to_datetime(df["DATE"] if "DATE" in df.columns else df.iloc[:, 0])
        return df


class SecEdgarProvider:
    """SEC EDGAR（data.sec.gov，無 key，需 User-Agent）。"""

    base = "https://data.sec.gov/submissions/CIK{cik}.json"
    UA = {"User-Agent": "MARKET_AI_HUB research local@example.com"}

    def recent_filings(self, cik: str, getter=None) -> list[dict]:
        import httpx
        if getter is None:
            def getter(u):
                return httpx.get(u, headers=self.UA, timeout=30, follow_redirects=True).json()
        data = getter(self.base.format(cik=cik))
        recent = data.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        dates = recent.get("filingDate", [])
        accs = recent.get("accessionNumber", [])
        out = []
        for i in range(min(len(forms), len(dates), len(accs))):
            out.append({"form": forms[i], "filing_date": dates[i], "accession": accs[i]})
        return out


PROVIDER_STATUS = {
    "BLS": "LIVE_VERIFIED", "BEA": "NEEDS_CONFIG", "Fed": "CONTRACT_ONLY",
    "BOJ": "LIVE_VERIFIED", "eStat": "NEEDS_CONFIG", "CabinetOffice": "CONTRACT_ONLY",
    "MOF": "CONTRACT_ONLY", "EIA": "NEEDS_CONFIG", "SEC EDGAR": "LIVE_VERIFIED",
    "EDINET": "NEEDS_CONFIG", "Cboe": "LIVE_VERIFIED",
}
