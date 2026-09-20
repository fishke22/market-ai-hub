"""Backtest 結果 schema（spec §24）。"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class BacktestRecord(BaseModel):
    model: str
    model_version: str
    data_version: str
    symbol: str
    period: str
    horizon: str
    feature_set: str
    timestamp: datetime

    directional_accuracy: float
    mae: float
    rmse: float
    pinball_loss: float
    brier_score: float | None = None

    hit_rate: float
    average_return: float
    expectancy: float
    profit_factor: float
    max_drawdown: float
    sharpe: float
    sortino: float

    n_samples: int
