"""Phase 2T — TradingView Cross-Check（§14）。

與 MARKET_AI_HUB 自己算的結果比較（reference price / RSI / EMA / support/resistance /
chart state）。結果 MATCH / MINOR_DIFFERENCE / CONFLICT / UNAVAILABLE。
TradingView 數字不同不得偷偷覆蓋官方來源。
"""
from __future__ import annotations

MATCH = "MATCH"
MINOR_DIFFERENCE = "MINOR_DIFFERENCE"
CONFLICT = "CONFLICT"
UNAVAILABLE = "UNAVAILABLE"


def cross_check(internal: float | None, tradingview: float | None,
                tolerance: float = 0.01) -> str:
    """internal = MARKET_AI_HUB 自己的值；tradingview = optional UI 值。"""
    if internal is None or tradingview is None:
        return UNAVAILABLE
    ref = abs(internal)
    diff = abs(internal - tradingview) / ref if ref > 0 else 0.0
    if diff <= tolerance:
        return MATCH
    if diff <= tolerance * 5:
        return MINOR_DIFFERENCE
    return CONFLICT


class TradingViewCrossCheck:
    def __init__(self, tolerance: float = 0.01) -> None:
        self.tolerance = tolerance

    def compare(self, factor: str, internal: float | None,
                tradingview: float | None) -> dict:
        status = cross_check(internal, tradingview, self.tolerance)
        return {
            "factor": factor,
            "status": status,
            "internal": internal,
            "tradingview": tradingview,
            "override_authoritative": False,  # 永不覆蓋官方來源
        }
