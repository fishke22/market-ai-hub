"""Phase 2A standardized evaluation（baselines + metrics）。

- 保留現有 walk-forward（backtest/walk_forward.py）不變。
- 價格 baselines：Last Price Naive / Random Walk / Drift / Moving Average。
- 分類 baselines：Majority Class / Always Flat。
- 價格 metrics：MAE / RMSE / MASE / Pinball Loss / Interval Coverage / Calibration Error。
- 分類 metrics：Accuracy / Balanced Accuracy / Macro F1 / MCC。
- 禁止固定 50% 當門檻（分類門檻 = max(majority baseline, uniform)）。
- FEVAdapter：標準化評估入口（autogluon/fev 為可選整合，未安裝則用內建 baselines）。
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

PRICE_METRICS = ["mae", "rmse", "mase", "pinball_loss", "interval_coverage", "calibration_error"]
CLASSIFICATION_METRICS = ["accuracy", "balanced_accuracy", "macro_f1", "mcc"]


# ── 價格 baselines ──

def last_price_naive(series: pd.Series, steps: int = 1) -> float:
    return float(series.iloc[-1])


def random_walk(series: pd.Series, steps: int = 1, seed: int = 42) -> float:
    """random walk baseline：下一期 = 最後價格（與 last-price 相同）＋由歷史殘差抽樣。

    注意：隨機項使其非唯一；評估時以 seed 固定，且與 last-price naive 在期望上等價。
    此處採用「殘差抽樣」的 random walk，符合財務文獻的 baseline 定義。
    """
    rets = series.pct_change().dropna()
    if len(rets) == 0:
        return float(series.iloc[-1])
    if steps < 1:
        raise ValueError("steps must be >= 1")
    rng = np.random.default_rng(seed)
    shocks = rng.choice(rets.to_numpy(), size=steps, replace=True)
    return float(series.iloc[-1] * np.prod(1.0 + shocks))


def drift(series: pd.Series, steps: int = 1) -> float:
    rets = series.pct_change().dropna()
    d = float(rets.mean()) if len(rets) else 0.0
    return float(series.iloc[-1] * (1 + d) ** steps)


def moving_average(series: pd.Series, steps: int = 1, window: int = 20) -> float:
    ma = series.rolling(window).mean().iloc[-1]
    if pd.isna(ma):
        return float(series.iloc[-1])
    return float(ma)


PRICE_BASELINES = {
    "last_price_naive": last_price_naive,
    "random_walk": random_walk,
    "drift": drift,
    "moving_average": moving_average,
}


def classification_baselines(y_true: np.ndarray, train_labels: np.ndarray | None = None) -> dict:
    """分類 baseline 的預測（與模型預測同長度），供準確率比較。

    - majority_class：只可由 train 多數類建立；缺 train labels 時為 None
    - always_flat：always predict 0（flat）
    """
    y_true = np.asarray(y_true)
    majority_pred = None
    if train_labels is not None and len(train_labels):
        from collections import Counter

        majority = Counter(np.asarray(train_labels).tolist()).most_common(1)[0][0]
        majority_pred = np.full(len(y_true), majority, dtype=int)
    return {
        "majority_class": majority_pred,
        "always_flat": np.zeros(len(y_true), dtype=int),
    }


# ── metrics ──

def _mae(a, p):
    return float(np.mean(np.abs(np.asarray(a) - np.asarray(p))))


def _rmse(a, p):
    return float(np.sqrt(np.mean((np.asarray(a) - np.asarray(p)) ** 2)))


def price_metrics(actual: np.ndarray, forecast: np.ndarray, naive_forecast: np.ndarray,
                  p10: np.ndarray | None = None, p90: np.ndarray | None = None) -> dict:
    actual = np.asarray(actual, dtype=float)
    forecast = np.asarray(forecast, dtype=float)
    naive_forecast = np.asarray(naive_forecast, dtype=float)
    mae = _mae(actual, forecast)
    rmse = _rmse(actual, forecast)
    mase = mae / _mae(actual, naive_forecast) if _mae(actual, naive_forecast) > 0 else float("nan")

    # pinball (0.5 median) 簡化：median pinball
    err = actual - forecast
    pinball = float(np.mean(np.where(err >= 0, 0.5 * err, -0.5 * err)))

    out = {"mae": mae, "rmse": rmse, "mase": mase, "pinball_loss": pinball,
           "interval_coverage": None, "calibration_error": None}
    if p10 is not None and p90 is not None:
        p10 = np.asarray(p10, dtype=float)
        p90 = np.asarray(p90, dtype=float)
        inside = (actual >= p10) & (actual <= p90)
        coverage = float(inside.mean())
        out["interval_coverage"] = coverage
        out["calibration_error"] = abs(coverage - 0.8)  # nominal 80%
    return out


def classification_metrics(y_true: np.ndarray, y_pred: np.ndarray,
                           train_labels: np.ndarray | None = None) -> dict:
    from sklearn.metrics import balanced_accuracy_score, f1_score, matthews_corrcoef

    y_true = np.asarray(y_true).astype(int)
    y_pred = np.asarray(y_pred).astype(int)
    acc = float((y_true == y_pred).mean())
    bal = float(balanced_accuracy_score(y_true, y_pred))
    macro_f1 = float(f1_score(y_true, y_pred, average="macro", zero_division=0))
    mcc = float(matthews_corrcoef(y_true, y_pred))
    # baseline 門檻（不固定 50%）
    bases = classification_baselines(y_true, train_labels)
    majority_pred = bases["majority_class"]
    majority_acc = None if majority_pred is None else float((y_true == majority_pred).mean())
    uniform = 1 / len(np.unique(y_true)) if len(np.unique(y_true)) else 1 / 3
    threshold = max(majority_acc, uniform) if majority_acc is not None else uniform
    return {
        "accuracy": acc, "balanced_accuracy": bal, "macro_f1": macro_f1, "mcc": mcc,
        "majority_class_baseline_accuracy": majority_acc,
        "uniform_baseline_accuracy": uniform,
        "baseline_threshold": threshold,
        "beats_majority_baseline": None if majority_acc is None else bal > threshold,
    }


class FEVAdapter:
    """標準化評估 adapter。

    autogluon / fev 為可選整合（尚未安裝，避免重依賴）。本 adapter 提供統一入口，
    用內建 baselines + metrics 完成標準化評估；未來可在此接入 autogluon/fev。
    """

    def __init__(self, available: bool = False) -> None:
        self._available = available

    @property
    def available(self) -> bool:
        return self._available

    def evaluate_price(self, actual, forecast, naive, p10=None, p90=None) -> dict:
        return price_metrics(actual, forecast, naive, p10, p90)

    def evaluate_classification(self, y_true, y_pred, train_labels=None) -> dict:
        return classification_metrics(y_true, y_pred, train_labels)


def make_fev_adapter() -> FEVAdapter:
    """建立 FEV adapter；autogluon/fev 未安裝 → available=False（用內建 baseline）。"""
    try:
        import autogluon  # noqa: F401

        return FEVAdapter(available=True)
    except Exception as e:
        log.info("autogluon/fev 未安裝，使用內建 baselines：%s", e)
        return FEVAdapter(available=False)
