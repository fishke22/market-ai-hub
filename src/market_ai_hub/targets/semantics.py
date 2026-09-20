"""Phase 2G.1 — Micro Forecast Semantics（4）。

優先預測 Micro return / normalized move / Micro-Mini basis，再 anchor 到 actual Micro reference price。
Mini/Large/SGX/CME 是 covariate/reference，不是 Micro 真實價格。
Micro actual 不存在 → PROXY_TRAINED_MICRO_ANCHORED，不得稱 DIRECT_MICRO_MODEL。
"""
from __future__ import annotations

DIRECT_MICRO_MODEL = "DIRECT_MICRO_MODEL"
PROXY_TRAINED_MICRO_ANCHORED = "PROXY_TRAINED_MICRO_ANCHORED"


class MicroForecastSemantics:
    """把 forecast 錨定到 Micro，並標明是否使用 Micro actual data。"""

    def micro_return(self, micro_forecast: float, micro_anchor: float) -> float:
        return micro_forecast / micro_anchor - 1.0

    def normalized_move(self, micro_return: float, micro_volatility: float) -> float:
        return micro_return / micro_volatility if micro_volatility else 0.0

    def micro_mini_basis(self, micro_price: float, mini_price: float) -> float:
        return micro_price - mini_price

    def label(self, has_micro_actual: bool) -> str:
        return DIRECT_MICRO_MODEL if has_micro_actual else PROXY_TRAINED_MICRO_ANCHORED

    def anchor(self, forecast_return: float, micro_anchor_price: float) -> float:
        """return → 絕對價（anchor 到 actual Micro reference price）。"""
        return micro_anchor_price * (1.0 + forecast_return)
