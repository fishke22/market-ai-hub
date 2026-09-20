"""Phase 2C — Regime 保護機制（樣本不足 / 信賴區間 / 收縮至全域）。

- minimum_sample_size：樣本不足 → REGIME_EVIDENCE=INSUFFICIENT。
- confidence interval：比例用 Wilson、均值用 standard error（deterministic）。
- shrinkage_to_global：樣本小時向全域（先驗）收縮，不得用少量樣本大幅調權重。
"""
from __future__ import annotations

import math


def shrinkage(stat: float, global_stat: float, n: int, k: float = 20.0) -> float:
    """shrinkage-to-global：n 小時向 global 收縮；n 大時趨近 stat。"""
    if n < 0:
        raise ValueError("n must be >= 0")
    return (n * stat + k * global_stat) / (n + k)


def wilson_ci(p: float, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval（比例的信賴區間）。n=0 → (nan, nan)。"""
    if n == 0:
        return (float("nan"), float("nan"))
    p = max(0.0, min(1.0, p))
    denom = 1 + z * z / n
    centre = p + z * z / (2 * n)
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * n)) / n)
    return ((centre - margin) / denom, (centre + margin) / denom)


def mean_ci(mean: float, std: float, n: int, z: float = 1.96) -> tuple[float, float]:
    """均值信賴區間（standard error）。n<=1 → (nan, nan)。"""
    if n <= 1:
        return (float("nan"), float("nan"))
    se = std / math.sqrt(n)
    return (mean - z * se, mean + z * se)


class RegimeProtection:
    def __init__(self, minimum_sample_size: int = 20, shrink_k: float = 20.0) -> None:
        self.minimum_sample_size = minimum_sample_size
        self.shrink_k = shrink_k

    def is_sufficient(self, n: int) -> bool:
        return n >= self.minimum_sample_size

    def shrink(self, stat: float, global_stat: float, n: int) -> float:
        return shrinkage(stat, global_stat, n, self.shrink_k)

    def insufficient_result(self, regime_name: str, n: int) -> dict:
        return {
            "regime": regime_name,
            "label": "insufficient",
            "status": "REGIME_EVIDENCE=INSUFFICIENT",
            "sample_size": n,
            "minimum_sample_size": self.minimum_sample_size,
            "evidence": {},
        }
