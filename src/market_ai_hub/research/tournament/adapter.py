"""Phase 2D — 統一 Model Adapter Contract。

- PRICE_FORECAST 模型可回 point / p10 / p50 / p90 / forecast_path；
  只有真的 predictive distribution 才能回 predictive quantiles（quantile_valid）。
- DIRECTION_CLASSIFICATION 模型回 class_label / raw_scores / probability_calibrated /
  calibration_metadata；不得製造假的價格 quantiles。
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import pandas as pd

log = logging.getLogger(__name__)


@dataclass
class ForecastResult:
    point: float | None = None
    p10: float | None = None
    p50: float | None = None
    p90: float | None = None
    forecast_path: list[float] | None = None
    quantile_valid: bool | None = None  # True = 真 predictive quantile 且 p10<=p50<=p90
    direction: str = ""  # up / down / flat
    class_label: int | None = None
    raw_scores: dict | None = None
    probability_calibrated: bool = False
    calibration_metadata: dict | None = None
    warnings: list[str] = field(default_factory=list)


class ModelAdapter(ABC):
    name: str = "adapter"
    task: str = "price"  # "price" | "direction"
    revision: str = ""
    training_cutoff: datetime | None = None

    def fit(self, df: pd.DataFrame) -> None:
        """用 df（OHLCV，截至 origin）訓練。預設 no-op（zero-shot / pretrained）。"""

    @abstractmethod
    def forecast(self, df: pd.DataFrame, steps: int) -> ForecastResult:
        """用 df 產生 steps 步預測。"""

    def metadata(self) -> dict:
        return {"name": self.name, "task": self.task, "revision": self.revision,
                "training_cutoff": str(self.training_cutoff) if self.training_cutoff else None}

    def supported_horizons(self) -> list[str]:
        return ["1d", "2d", "5d", "10d"]

    def release(self) -> None:
        """釋放 GPU / 資源（模型多時避免 VRAM 常駐）。預設 no-op。"""
