"""Walk-forward backtest（spec §24）。

- 時間序列嚴禁 random split → chronological split + rolling window
- 統計：directional_accuracy / MAE / RMSE / pinball_loss / Brier（適用時）
- 交易研究：hit_rate / average_return / expectancy / profit_factor / max_drawdown / Sharpe / Sortino
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from market_ai_hub.schemas.backtest import BacktestRecord


@dataclass
class WalkForwardSplit:
    train: pd.DataFrame
    test: pd.DataFrame


def walk_forward_splits(df: pd.DataFrame, n_splits: int = 5, min_train: int = 60) -> list[WalkForwardSplit]:
    """chronological 分割：不 shuffle，train 永遠在 test 之前。"""
    n = len(df)
    if n < min_train * 2:
        return []
    test_size = max(1, n // (n_splits + 1))
    splits: list[WalkForwardSplit] = []
    for i in range(n_splits):
        test_start = min_train + i * test_size
        test_end = min(n, test_start + test_size)
        if test_end <= test_start or test_start >= n:
            break
        splits.append(WalkForwardSplit(train=df.iloc[:test_start], test=df.iloc[test_start:test_end]))
    return splits


def compute_metrics(
    actual: np.ndarray,
    predicted: np.ndarray,
    directions: list[str],
    threshold: float = 0.005,
) -> dict:
    """由 walk-forward 累積的 actual / predicted 計算全部指標。"""
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    err = predicted - actual
    mae = float(np.mean(np.abs(err)))
    rmse = float(np.sqrt(np.mean(err**2)))
    pinball = float(np.mean(np.where(err >= 0, 0.1 * err, -0.9 * err)))

    up = np.array([d == "up" for d in directions], dtype=bool)
    down = np.array([d == "down" for d in directions], dtype=bool)
    flat = ~(up | down)
    act_up = actual > threshold
    act_down = actual < -threshold
    hit = (up & act_up) | (down & act_down) | (flat & ~act_up & ~act_down)
    directional_accuracy = float(hit.mean())

    # 交易研究：up→+1, down→-1, flat→0；報酬 = direction * actual_return
    pos = (up * 1.0 - down * 1.0)
    trade_returns = pos * actual
    hit_rate = float((trade_returns > 0).mean()) if len(trade_returns) else 0.0
    average_return = float(trade_returns.mean()) if len(trade_returns) else 0.0
    wins = trade_returns[trade_returns > 0].sum()
    losses = -trade_returns[trade_returns < 0].sum()
    profit_factor = float(wins / losses) if losses > 0 else float("inf")
    expectancy = float(trade_returns.mean()) if len(trade_returns) else 0.0

    cum = (1 + pd.Series(trade_returns)).cumprod()
    dd = (cum / cum.cummax() - 1).min()
    max_drawdown = float(dd)

    sd = float(trade_returns.std(ddof=1)) if len(trade_returns) > 1 else 0.0
    sharpe = float(trade_returns.mean() / sd * np.sqrt(252)) if sd > 0 else 0.0
    downside = trade_returns[trade_returns < 0].std(ddof=1) if (trade_returns < 0).any() else 0.0
    if downside is None or not np.isfinite(downside) or downside < 1e-12:
        sortino = 0.0
    else:
        sortino = float(trade_returns.mean() / downside * np.sqrt(252))

    return {
        "directional_accuracy": directional_accuracy,
        "mae": mae,
        "rmse": rmse,
        "pinball_loss": pinball,
        "hit_rate": hit_rate,
        "average_return": average_return,
        "expectancy": expectancy,
        "profit_factor": profit_factor if np.isfinite(profit_factor) else 999.0,
        "max_drawdown": max_drawdown,
        "sharpe": sharpe,
        "sortino": sortino,
        "n_samples": len(actual),
    }


def make_record(metrics: dict, **meta) -> BacktestRecord:
    return BacktestRecord(
        timestamp=datetime.now(timezone.utc),
        brier_score=None,
        **meta,
        **metrics,
    )
