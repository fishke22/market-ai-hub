"""Phase 2I-A — Cross-source sanity check（§10）。

對重要 factor（Nikkei proxy/reference、USDJPY、VIX、Treasury）有多來源時做 sanity check。
差異超門檻 → DATA_CONFLICT（不默默選一個）。authoritative source 優先於 proxy。
"""
from __future__ import annotations

DATA_CONFLICT = "DATA_CONFLICT"
CONSISTENT = "CONSISTENT"
SINGLE_SOURCE = "SINGLE_SOURCE"


def cross_source_check(name: str, authoritative: float | None, proxy: float | None,
                       threshold: float = 0.05) -> dict:
    """比較 authoritative vs proxy；無第二來源 → SINGLE_SOURCE；差 > threshold → DATA_CONFLICT。"""
    if authoritative is None or proxy is None:
        return {"factor": name, "status": SINGLE_SOURCE, "note": "single source only"}
    ref = abs(authoritative)
    diff = abs(authoritative - proxy) / ref if ref > 0 else 0.0
    if diff > threshold:
        return {"factor": name, "status": DATA_CONFLICT,
                "authoritative": authoritative, "proxy": proxy, "diff": round(diff, 4)}
    return {"factor": name, "status": CONSISTENT, "diff": round(diff, 4)}


def check_factors(comparisons: dict[str, tuple[float | None, float | None]],
                  threshold: float = 0.05) -> list[dict]:
    """comparisons: {factor_name: (authoritative, proxy)}。"""
    out = []
    for name, (auth, proxy) in comparisons.items():
        out.append(cross_source_check(name, auth, proxy, threshold))
    return out
