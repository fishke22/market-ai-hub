"""Phase 2G.1 — Data Source Coverage Auditor（7）。

每個 factor 標 AUTHORITATIVE / OFFICIAL_DELAYED / RESEARCH_PROXY / OPTIONAL / MISSING。
不得宣稱全部 authoritative。
"""
from __future__ import annotations

from pydantic import BaseModel

AUTHORITATIVE = "AUTHORITATIVE"
OFFICIAL_DELAYED = "OFFICIAL_DELAYED"
RESEARCH_PROXY = "RESEARCH_PROXY"
OPTIONAL = "OPTIONAL"
MISSING = "MISSING"

# Phase 2G.2 升級 status
LIVE_VERIFIED = "LIVE_VERIFIED"          # 已實際連線 + 解析官方來源成功
HISTORICAL_VERIFIED = "HISTORICAL_VERIFIED"  # 官方歷史已抓取
CONTRACT_ONLY = "CONTRACT_ONLY"          # 有 provider 介面，尚未接實網
NEEDS_CONFIG = "NEEDS_CONFIG"            # 需 API key / 設定
DELAYED = "DELAYED"                      # 官方延遲來源
PROXY = "PROXY"                          # 第三方 proxy（非官方）

# V2-A.2 status disambiguation（LIVE 只描述 current usable live observation）
SOURCE_VERIFIED = "SOURCE_VERIFIED"      # official source verified reachable（非 live quote）
REFERENCE_AVAILABLE = "REFERENCE_AVAILABLE"  # 有官方 dated reference（e.g. daily settlement）
LIVE_AVAILABLE = "LIVE_AVAILABLE"        # 目前有可用 live observation（需 timestamp/freshness 證明）

# 大阪模型至少 audit 的 factor（誠實預設：大多 RESEARCH_PROXY / MISSING）
AUDIT_FACTORS = [
    "Micro", "Mini", "Large", "Nikkei spot", "TOPIX", "SGX Nikkei", "CME Nikkei",
    "NQ", "ES", "SOX", "USDJPY", "DXY", "VIX", "US2Y", "US5Y", "US10Y", "US30Y",
    "Gold", "WTI", "BTC", "BOJ", "Fed", "CPI", "NFP", "PCE", "GDP", "CFTC", "FX intervention",
]

# 誠實預設 status（依「可取得性」標注，非全部 authoritative）
DEFAULT_FACTOR_STATUS = {
    "Micro": MISSING,            # JPX provider 尚未接實網（本棒 parser + downloader）
    "Mini": MISSING,
    "Large": MISSING,
    "Nikkei spot": RESEARCH_PROXY,
    "TOPIX": RESEARCH_PROXY,
    "SGX Nikkei": MISSING,
    "CME Nikkei": MISSING,
    "NQ": RESEARCH_PROXY,
    "ES": RESEARCH_PROXY,
    "SOX": RESEARCH_PROXY,
    "USDJPY": RESEARCH_PROXY,
    "DXY": RESEARCH_PROXY,
    "VIX": RESEARCH_PROXY,       # 若接 Cboe official → AUTHORITATIVE
    "US2Y": RESEARCH_PROXY,
    "US5Y": RESEARCH_PROXY,
    "US10Y": RESEARCH_PROXY,
    "US30Y": RESEARCH_PROXY,
    "Gold": RESEARCH_PROXY,
    "WTI": RESEARCH_PROXY,
    "BTC": RESEARCH_PROXY,
    "BOJ": MISSING,
    "Fed": MISSING,
    "CPI": MISSING,
    "NFP": MISSING,
    "PCE": MISSING,
    "GDP": MISSING,
    "CFTC": MISSING,
    "FX intervention": MISSING,
}


class CoverageRecord(BaseModel):
    factor: str
    status: str
    note: str = ""


class DataCoverageAuditor:
    def audit(self, overrides: dict[str, str] | None = None) -> list[CoverageRecord]:
        """回傳每個 factor 的 coverage status；overrides 可標注官方來源已接上。"""
        status = dict(DEFAULT_FACTOR_STATUS)
        if overrides:
            status.update(overrides)
        out = []
        for f in AUDIT_FACTORS:
            out.append(CoverageRecord(factor=f, status=status.get(f, MISSING)))
        return out

    def authoritative_count(self, records: list[CoverageRecord]) -> int:
        return sum(1 for r in records if r.status == AUTHORITATIVE)

    def summary(self, records: list[CoverageRecord]) -> dict[str, int]:
        s: dict[str, int] = {}
        for r in records:
            s[r.status] = s.get(r.status, 0) + 1
        return s


# 大阪模型 coverage（section 9）逐項 source / coverage / freshness / status
OSAKA_FACTORS = [
    "Micro OHLC", "Micro settlement", "Mini", "Large", "Nikkei spot", "TOPIX",
    "JPX investor flow", "SGX Nikkei", "CME Nikkei", "NQ", "ES", "SOX", "USDJPY",
    "VIX", "US2Y", "US5Y", "US10Y", "US30Y", "Gold", "WTI", "BTC",
    "Fed", "BOJ", "CPI", "NFP", "PCE", "GDP", "CFTC", "JPY intervention",
]


class LiveCoverageRecord(BaseModel):
    factor: str
    source: str
    coverage: str
    freshness: str
    status: str


class LiveCoverageAuditor(DataCoverageAuditor):
    """真實反映缺口的 coverage（LIVE_VERIFIED / CONTRACT_ONLY / NEEDS_CONFIG / ...）。"""

    def audit_osaka(self, overrides: dict[str, dict] | None = None) -> list[LiveCoverageRecord]:
        default = {
            "Micro OHLC": ("JPX Daily Report (xlsx)", "daily", "per-contract OHLC (settlement=close proxy)"),
            "Micro settlement": ("JPX settlement CSV", "daily", "FUT_225MC 清算価格"),
            "Mini": ("JPX settlement CSV", "daily", "FUT_225M"),
            "Large": ("JPX settlement CSV", "daily", "FUT_225"),
            "Nikkei spot": ("JPX/Nikkei", "daily", "spot"),
            "TOPIX": ("JPX", "daily", "index"),
            "JPX investor flow": ("JPX Trading by Investor", "weekly", "official CSV"),
            "SGX Nikkei": ("SGX", "daily", "external"),
            "CME Nikkei": ("CME", "daily", "external"),
            "NQ": ("CME", "daily", "external proxy"),
            "ES": ("CME", "daily", "external proxy"),
            "SOX": ("Philadelphia", "daily", "external proxy"),
            "USDJPY": ("FX", "daily", "proxy"),
            "VIX": ("Cboe official", "daily", "authoritative history"),
            "US2Y": ("UST", "daily", "proxy"),
            "US5Y": ("UST", "daily", "proxy"),
            "US10Y": ("UST", "daily", "proxy"),
            "US30Y": ("UST", "daily", "proxy"),
            "Gold": ("COMEX", "daily", "proxy"),
            "WTI": ("EIA/CME", "daily", "proxy"),
            "BTC": ("exchange", "daily", "proxy"),
            "Fed": ("federalreserve.gov", "event", "FOMC calendar"),
            "BOJ": ("boj.or.jp", "event", "MPM/release"),
            "CPI": ("BLS API v2", "monthly", "release-time"),
            "NFP": ("BLS API v2", "monthly", "release-time"),
            "PCE": ("BEA API", "monthly", "needs key"),
            "GDP": ("BEA API", "quarterly", "needs key"),
            "CFTC": ("CFTC COT", "weekly", "positioning"),
            "JPY intervention": ("MOF", "event", "FX intervention"),
        }
        default_status = {
            "Micro OHLC": CONTRACT_ONLY, "Micro settlement": CONTRACT_ONLY, "Mini": CONTRACT_ONLY,
            "Large": CONTRACT_ONLY, "Nikkei spot": PROXY, "TOPIX": PROXY,
            "JPX investor flow": CONTRACT_ONLY, "SGX Nikkei": MISSING, "CME Nikkei": MISSING,
            "NQ": PROXY, "ES": PROXY, "SOX": PROXY, "USDJPY": PROXY,
            "VIX": PROXY, "US2Y": PROXY, "US5Y": PROXY, "US10Y": PROXY, "US30Y": PROXY,
            "Gold": PROXY, "WTI": PROXY, "BTC": PROXY,
            "Fed": CONTRACT_ONLY, "BOJ": CONTRACT_ONLY, "CPI": CONTRACT_ONLY, "NFP": CONTRACT_ONLY,
            "PCE": NEEDS_CONFIG, "GDP": NEEDS_CONFIG, "CFTC": MISSING, "JPY intervention": CONTRACT_ONLY,
        }
        records: list[LiveCoverageRecord] = []
        for f in OSAKA_FACTORS:
            src, coverage, freshness = default[f]
            status = default_status[f]
            if overrides and f in overrides:
                o = overrides[f]
                src = o.get("source", src)
                coverage = o.get("coverage", coverage)
                freshness = o.get("freshness", freshness)
                status = o.get("status", status)
            records.append(LiveCoverageRecord(factor=f, source=src, coverage=coverage,
                                              freshness=freshness, status=status))
        return records
