"""Phase 2F — 交易成本模型（ZERO_COST / BASE_COST / STRESS_COST）。

不交易也回報成本後績效；不得只報無成本績效。
"""
from __future__ import annotations

from dataclasses import dataclass

# 每單位名目交易成本的 proxy（假設值，可覆寫）
COST_PRESETS: dict[str, dict] = {
    "ZERO_COST": {"fee": 0.0, "spread_proxy": 0.0, "slippage": 0.0},
    "BASE_COST": {"fee": 0.0005, "spread_proxy": 0.0003, "slippage": 0.0005},
    "STRESS_COST": {"fee": 0.0020, "spread_proxy": 0.0010, "slippage": 0.0030},
}


@dataclass(frozen=True)
class CostModel:
    name: str
    fee: float
    spread_proxy: float
    slippage: float

    @classmethod
    def preset(cls, name: str) -> "CostModel":
        p = COST_PRESETS[name]
        return cls(name=name, fee=p["fee"], spread_proxy=p["spread_proxy"], slippage=p["slippage"])

    def per_trade(self) -> float:
        """單次交易（進+出）總成本佔名目比例。"""
        return 2.0 * (self.fee + self.spread_proxy + self.slippage)

    def apply(self, gross_returns) -> list[float]:
        """把每次進出場成本扣掉（用方向轉換次數近似 turnover）。"""
        out = []
        prev_side = 0
        for r in gross_returns:
            side = 1 if r >= 0 else -1  # 簡化：以報酬符號當持倉方向 proxy
            if side != prev_side and prev_side != 0:
                out.append(r - self.per_trade())
            else:
                out.append(r - self.fee - self.spread_proxy)
            prev_side = side
        return out


def all_cost_presets() -> list[CostModel]:
    return [CostModel.preset(n) for n in COST_PRESETS]
