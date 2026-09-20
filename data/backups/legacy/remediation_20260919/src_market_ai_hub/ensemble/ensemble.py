"""Ensemble（spec §23）。

第一版：equal-weight ensemble。
輸入：TimesFM / Chronos / XGBoost / LightGBM（FinCast optional）。
歷史績效不足 → 不得亂算權重，fallback equal weight。
輸出含 model_agreement: HIGH / MEDIUM / LOW。
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import numpy as np

from market_ai_hub.schemas.market_data import DataGrade, ForecastOutput

log = logging.getLogger(__name__)


def ensemble_equal_weight(forecasts: list[ForecastOutput], symbol: str, horizon: str) -> ForecastOutput:
    """equal-weight ensemble。任一模型失敗不應中斷 ensemble（graceful degradation）。"""
    if not forecasts:
        raise ValueError("no forecasts to ensemble")
    weights = np.ones(len(forecasts)) / len(forecasts)
    return _combine(forecasts, weights, symbol, horizon)


def ensemble_performance_weighted(
    forecasts: list[ForecastOutput],
    symbol: str,
    horizon: str,
    performance: dict[str, float] | None = None,
) -> ForecastOutput:
    """performance-weighted ensemble；績效不足（<3 個模型有紀錄）→ fallback equal weight。"""
    if not performance or sum(1 for f in forecasts if f.model in performance) < 3:
        return ensemble_equal_weight(forecasts, symbol, horizon)
    w = np.array([performance.get(f.model, 0.0) for f in forecasts], dtype=float)
    if w.sum() <= 0:
        return ensemble_equal_weight(forecasts, symbol, horizon)
    return _combine(forecasts, w / w.sum(), symbol, horizon)


def _combine(forecasts: list[ForecastOutput], weights: np.ndarray, symbol: str, horizon: str) -> ForecastOutput:
    p50 = float(np.average([f.point_forecast for f in forecasts], weights=weights))
    exp_ret = float(np.average([f.expected_return for f in forecasts], weights=weights))
    q_keys = sorted({k for f in forecasts for k in f.quantiles})
    quantiles = {
        k: float(np.average([f.quantiles.get(k, f.point_forecast) for f in forecasts], weights=weights))
        for k in q_keys
    }
    directions = [f.direction for f in forecasts]
    direction = max(set(directions), key=directions.count)
    agree_ratio = directions.count(direction) / len(directions)
    agreement = "HIGH" if agree_ratio >= 0.75 else ("MEDIUM" if agree_ratio >= 0.5 else "LOW")
    last = p50 / (1 + exp_ret)
    confidence = float(np.average([f.confidence for f in forecasts], weights=weights))
    return ForecastOutput(
        model="ensemble",
        symbol=symbol,
        as_of=datetime.now(timezone.utc),
        horizon=horizon,
        point_forecast=p50,
        expected_return=exp_ret,
        quantiles=quantiles,
        direction=direction,
        confidence=confidence,
        data_grade=forecasts[0].data_grade,
        warnings=[f"model_agreement={agreement}", "equal_weight" if np.allclose(weights, 1 / len(weights)) else "performance_weighted"],
    )


def model_agreement(forecasts: list[ForecastOutput]) -> str:
    if not forecasts:
        return "LOW"
    directions = [f.direction for f in forecasts]
    top = max(set(directions), key=directions.count)
    ratio = directions.count(top) / len(directions)
    return "HIGH" if ratio >= 0.75 else ("MEDIUM" if ratio >= 0.5 else "LOW")
