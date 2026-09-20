"""Phase 2F — 防止策略 overfitting（H）。

minimum_trade_count / multiple-window validation / parameter-complexity penalty / stability checks。
5 筆交易贏 4 次不得稱 EDGE_FOUND。
"""
from __future__ import annotations

MIN_TRADE_COUNT = 30


def guard_edge(n_trades: int, hit_rate: float | None = None,
               n_horizons_valid: int = 1, n_params: int = 0,
               min_trades: int = MIN_TRADE_COUNT, min_horizons: int = 1,
               complexity_penalty_per_param: float = 0.01) -> tuple[bool, str]:
    """回傳 (是否可宣稱 EDGE_FOUND, 原因)。

    - 交易數 < min_trades → 不得宣稱（即便 hit_rate 高）
    - 多窗口：同 rule 需在 ≥ min_horizons 個 horizon 仍成立
    - 參數複雜度：n_params * penalty 折減 edge（此處以門檻近似）
    """
    if n_trades < min_trades:
        return False, f"insufficient trades ({n_trades}<{min_trades})"
    if hit_rate is not None and n_trades < min_trades:
        return False, "insufficient trades (small-sample hit_rate not meaningful)"
    if n_horizons_valid < min_horizons:
        return False, f"not stable across windows ({n_horizons_valid}<{min_horizons})"
    if n_params * complexity_penalty_per_param > 0.2:
        return False, f"too complex (n_params={n_params})"
    return True, "ok"


def stability_check(edge_by_window: list[float]) -> tuple[bool, float]:
    """跨窗口 edge 一致性：回傳 (stable, std)。"""
    import numpy as np

    arr = np.asarray(edge_by_window, dtype=float)
    if len(arr) < 2:
        return False, 0.0
    std = float(arr.std(ddof=1))
    # 簡化門檻：正負號一致且 std 小於平均絕對值
    sign_consistent = (np.sign(arr) == np.sign(arr[0])).all()
    return bool(sign_consistent and std < abs(float(arr.mean()))), std
