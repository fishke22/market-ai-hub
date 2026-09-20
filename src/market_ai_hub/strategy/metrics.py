"""Phase 2F — 策略績效 metrics（G）。"""
from __future__ import annotations

import numpy as np
import pandas as pd

from market_ai_hub.strategy.cost import CostModel


def _annualized_return(r: np.ndarray, periods_per_year: int) -> float:
    if len(r) == 0:
        return 0.0
    total = float(np.prod(1 + r) - 1.0)
    years = len(r) / periods_per_year
    if years <= 0:
        return 0.0
    return float((1 + total) ** (1 / years) - 1.0) if total > -1 else -1.0


def compute_strategy_metrics(returns: list[float], cost: CostModel | None = None,
                             periods_per_year: int = 252) -> dict:
    """returns：每筆交易 net（或 gross）回報。回傳完整 metrics dict。

    沒交易 → 各欄 0.0 / None，hit_rate 等仍合法（不 crash）。
    """
    gross = np.asarray(returns, dtype=float)
    if cost is not None:
        r = np.asarray(cost.apply(list(gross)), dtype=float)
    else:
        r = gross.copy()
    n = len(r)
    if n == 0:
        return _empty_metrics()
    wins = r[r > 0]
    losses = r[r < 0]
    gross_wins = gross[gross > 0]
    gross_losses = gross[gross < 0]
    mean = float(r.mean())
    std = float(r.std(ddof=1)) if n > 1 else 0.0
    downside = r[r < 0]
    dstd = float(downside.std(ddof=1)) if len(downside) > 1 else 0.0
    ann_ret = _annualized_return(r, periods_per_year)
    ann_vol = float(std * np.sqrt(periods_per_year))
    sharpe = float(ann_ret / ann_vol) if ann_vol > 0 else 0.0
    sortino = float(ann_ret / (dstd * np.sqrt(periods_per_year))) if dstd > 0 else 0.0
    # drawdown on cumulative equity
    equity = np.cumprod(1 + r)
    peak = np.maximum.accumulate(equity)
    max_dd = float((equity / peak - 1).min())
    pf = (float(gross_wins.sum()) / abs(float(gross_losses.sum()))) if len(gross_losses) and gross_losses.sum() != 0 else float("inf")
    return {
        "number_of_trades": n,
        "hit_rate": float((r > 0).mean()),
        "expectancy": mean,
        "profit_factor": pf,
        "annualized_return": ann_ret,
        "volatility": ann_vol,
        "Sharpe": sharpe,
        "Sortino": sortino,
        "max_drawdown": max_dd,
        "average_MAE": float(np.mean(np.abs(gross))),
        "average_MFE": float(gross_wins.mean()) if len(gross_wins) else 0.0,
        "turnover": n,  # 每筆交易一次進出，簡化 proxy
        "cost_sensitivity": float(mean - float(gross.mean())) if cost is not None else 0.0,
        "regime_stability": 0.0,  # 由呼叫方帶入 regime 分佈穩定度，預設 0
    }


def _empty_metrics() -> dict:
    return {
        "number_of_trades": 0, "hit_rate": 0.0, "expectancy": 0.0,
        "profit_factor": 0.0, "annualized_return": 0.0, "volatility": 0.0,
        "Sharpe": 0.0, "Sortino": 0.0, "max_drawdown": 0.0,
        "average_MAE": 0.0, "average_MFE": 0.0, "turnover": 0,
        "cost_sensitivity": 0.0, "regime_stability": 0.0,
    }
