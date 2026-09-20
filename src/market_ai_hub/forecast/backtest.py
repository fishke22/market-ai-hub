"""Phase 2G — 歷史 evaluation / backtest（T/U）。

比較 Best Single Model / Best Baseline / Static Equal Weight / Dynamic Ensemble /
Regime Router，必須 same target / same horizon / same origins / same information_cutoff。
禁止只比較 dynamic ensemble vs weakest baseline。
"""
from __future__ import annotations

import numpy as np


def _direction_acc(point: np.ndarray, actual: np.ndarray) -> float:
    sign_p = np.sign(np.diff(np.concatenate([[0.0], point])))  # 簡化：與 0 比
    sign_a = np.sign(actual)
    return float((sign_p == sign_a).mean())


def compute_forecast_metrics(point: list[float], actual: list[float],
                             p10: list[float] | None = None, p90: list[float] | None = None,
                             scale: float | None = None) -> dict:
    p = np.asarray(point, dtype=float)
    a = np.asarray(actual, dtype=float)
    n = len(p)
    if n == 0:
        return {}
    err = p - a
    mae = float(np.mean(np.abs(err)))
    rmse = float(np.sqrt(np.mean(err ** 2)))
    mase = None
    if scale and scale > 0:
        mase = float(np.mean(np.abs(err)) / scale)
    direction = _direction_acc(p, a)
    coverage = calibration = None
    if p10 is not None and p90 is not None:
        lo = np.asarray(p10, dtype=float)
        hi = np.asarray(p90, dtype=float)
        coverage = float(((a >= lo) & (a <= hi)).mean())
        # pinball (90% 區間近似以 p50=point 對稱) → 用 point 當 p50 的 pinball
        alpha = 0.9
        pin = np.where(a < p, (1 - alpha) * (p - a), alpha * (a - p))
        calibration = float(np.mean(pin))
    return {
        "n": n, "mae": mae, "rmse": rmse, "mase": mase,
        "direction_accuracy": direction, "coverage": coverage, "calibration": calibration,
    }


def same_exam_comparison(methods: dict[str, dict], actual: list[float],
                         scale: float | None = None) -> dict[str, dict]:
    """methods: {name: {"point": [...], "p10": [...] | None, "p90": [...] | None}}。"""
    out: dict[str, dict] = {}
    for name, m in methods.items():
        out[name] = compute_forecast_metrics(
            m["point"], actual,
            p10=m.get("p10"), p90=m.get("p90"), scale=scale,
        )
    return out


def assert_same_exam(forecasts: dict[str, dict]) -> bool:
    """確認所有方法長度一致（same origins / cutoff）。"""
    lens = {len(m["point"]) for m in forecasts.values() if m.get("point")}
    return len(lens) <= 1
