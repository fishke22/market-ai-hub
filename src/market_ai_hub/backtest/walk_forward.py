"""Walk-forward backtest（spec §24 + V1 remediation Phase 5/13）。

- 時間序列嚴禁 random split → chronological split + rolling window
- 分類指標：accuracy / balanced_accuracy / macro_f1 / mcc + 同-origin baselines
- majority training prevalence 與 OOS majority-classifier metrics 分欄，不混尺度
- eligibility 要求 accuracy / balanced_accuracy / macro_f1 各自優於對應 majority baseline
- gross strategy diagnostics 只使用真 realized return；成本未建模時不宣稱 economic edge
- TS 指標：MAE / RMSE / MASE（naive 為 last-price）
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
    """Numeric return-forecast metrics.

    Both actual and predicted must be realized/forecast returns on the same
    numeric scale. Classification class IDs must never be passed here.
    """
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
    pos = up * 1.0 - down * 1.0
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


def strategy_metrics(realized_returns: np.ndarray, directions: list[str]) -> dict:
    """Gross strategy diagnostics from real realized returns.

    Fees, tax and slippage are deliberately excluded, so this cannot be
    presented as a cost-aware economic edge.
    """
    actual = np.asarray(realized_returns, dtype=float)
    if len(actual) != len(directions):
        raise ValueError("realized_returns and directions length mismatch")
    if not np.isfinite(actual).all():
        raise ValueError("realized_returns must be finite")

    up = np.array([d == "up" for d in directions], dtype=bool)
    down = np.array([d == "down" for d in directions], dtype=bool)
    pos = up.astype(float) - down.astype(float)
    trade_returns = pos * actual
    active = pos != 0
    active_returns = trade_returns[active]

    hit_rate = (
        float((active_returns > 0).mean()) if len(active_returns) else None
    )
    average_return = float(trade_returns.mean()) if len(trade_returns) else None
    wins = float(active_returns[active_returns > 0].sum()) if len(active_returns) else 0.0
    losses = float(-active_returns[active_returns < 0].sum()) if len(active_returns) else 0.0
    profit_factor = (wins / losses) if losses > 0 else None
    expectancy = (
        float(active_returns.mean()) if len(active_returns) else None
    )

    if len(trade_returns):
        cum = (1 + pd.Series(trade_returns)).cumprod()
        max_drawdown = float((cum / cum.cummax() - 1).min())
    else:
        max_drawdown = None

    sd = float(trade_returns.std(ddof=1)) if len(trade_returns) > 1 else 0.0
    sharpe = (
        float(trade_returns.mean() / sd * np.sqrt(252)) if sd > 0 else None
    )
    downside = (
        active_returns[active_returns < 0].std(ddof=1)
        if (active_returns < 0).any()
        else np.nan
    )
    sortino = (
        float(trade_returns.mean() / downside * np.sqrt(252))
        if np.isfinite(downside) and downside > 1e-12
        else None
    )
    return {
        "hit_rate": hit_rate,
        "average_return": average_return,
        "expectancy": expectancy,
        "profit_factor": profit_factor,
        "max_drawdown": max_drawdown,
        "sharpe": sharpe,
        "sortino": sortino,
        "economic_metrics_status": "GROSS_REALIZED_RETURN_DIAGNOSTIC_NO_COSTS",
        "economic_return_semantics": "POSITION_TIMES_REALIZED_NEXT_BAR_RETURN",
        "transaction_costs_included": False,
        "n_active_trades": int(active.sum()),
    }


def classification_metrics(y_true: np.ndarray, y_pred: np.ndarray, train_labels: np.ndarray | None = None) -> dict:
    """Three-class OOS metrics with same-metric, same-origin baselines.

    beats_majority_baseline requires accuracy, balanced accuracy and
    macro-F1 to each beat the corresponding same-origin majority-classifier
    comparator; training prevalence is reported separately.
    """
    from sklearn.metrics import balanced_accuracy_score, f1_score, matthews_corrcoef

    y_true = np.asarray(y_true).astype(int)
    y_pred = np.asarray(y_pred).astype(int)
    n = len(y_true)
    if n == 0:
        return {"n_oos": 0}

    acc = float((y_true == y_pred).mean())
    bal_acc = float(balanced_accuracy_score(y_true, y_pred))
    macro_f1 = float(f1_score(y_true, y_pred, average="macro", zero_division=0))
    mcc = float(matthews_corrcoef(y_true, y_pred))

    if train_labels is not None and len(train_labels):
        tr = np.asarray(train_labels).astype(int)
        counts = {c: int((tr == c).sum()) for c in (-1, 0, 1)}
        total = sum(counts.values()) or 1
        dist = {str(k): round(v / total, 4) for k, v in counts.items()}
        # Deterministic tie preference: flat, down, up.
        majority_class = max((0, -1, 1), key=lambda c: counts[c])
        majority_pred = np.full(n, majority_class, dtype=int)
        majority_acc = float((y_true == majority_pred).mean())
        majority_bal = float(balanced_accuracy_score(y_true, majority_pred))
        majority_macro_f1 = float(
            f1_score(y_true, majority_pred, average="macro", zero_division=0)
        )
        majority_train_prevalence = float(counts[majority_class] / total)
    else:
        dist = {"-1": None, "0": None, "1": None}
        majority_class = None
        majority_acc = None
        majority_bal = None
        majority_macro_f1 = None
        majority_train_prevalence = None

    uniform_acc = 1 / 3
    uniform_bal = 1 / 3
    threshold = (
        max(majority_bal, uniform_bal)
        if majority_bal is not None
        else None
    )
    beats = (
        None
        if threshold is None
        else bool(
            acc > majority_acc
            and bal_acc > threshold
            and macro_f1 > majority_macro_f1
        )
    )

    return {
        "n_oos": n,
        "accuracy": acc,
        "balanced_accuracy": bal_acc,
        "macro_f1": macro_f1,
        "mcc": mcc,
        "class_distribution": dist,
        "majority_class": majority_class,
        "majority_class_train_prevalence": majority_train_prevalence,
        "uniform_random_baseline_accuracy": uniform_acc,
        "uniform_random_baseline_balanced_accuracy": uniform_bal,
        "majority_class_baseline_accuracy": majority_acc,
        "majority_class_baseline_balanced_accuracy": majority_bal,
        "majority_class_baseline_macro_f1": majority_macro_f1,
        "baseline_metric": "accuracy+balanced_accuracy+macro_f1",
        "baseline_threshold": threshold,
        "baseline_semantics": "OOS_SAME_ORIGIN_MAJORITY_CLASSIFIER_V2",
        "beats_majority_baseline": beats,
    }


def make_record(metrics: dict, **meta) -> BacktestRecord:
    return BacktestRecord(
        timestamp=datetime.now(timezone.utc),
        brier_score=None,
        **meta,
        **metrics,
    )
