"""TimesFM 3.0 adapter（spec §6）。

- 官方 repository: google-research/timesfm, package timesfm[torch] (timesfm 3.0.x)
- 模型: google/timesfm-3.0-pytorch
- 授權：code Apache-2.0；weights = timesfm-non-commercial-license-v1.0
  → 僅 non-commercial / research / evaluation，詳見 docs/LICENSE_MATRIX.md
- API：TimesFM3Forecaster.from_pretrained(...) + predict(context, horizon, return_quantiles=True)
  原生 quantiles = [0.1..0.9]，median_quantile_index=4 (0.5)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from market_ai_hub.config.settings import project_root
from market_ai_hub.schemas.market_data import DataGrade, ForecastOutput

log = logging.getLogger(__name__)

MODEL_ID = "google/timesfm-3.0-pytorch"
MODEL_CACHE = project_root() / "models" / "cache" / "timesfm-3.0"
LICENSE_TAG = "TIMESFM3_NON_COMMERCIAL_ONLY"
NATIVE_QUANTILES = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]


class TimesFM3Adapter:
    """包裝 timesfm3.TimesFM3Forecaster。CUDA 失敗時標記 degraded/unavailable，不影響 Chronos。"""

    def __init__(self, device: str | None = None) -> None:
        self._model = None
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self._last_error = ""

    def status(self) -> str:
        try:
            self.load()
            return "ready"
        except Exception as e:
            self._last_error = str(e)
            log.warning("timesfm3 load failed: %s", e)
            return "unavailable"

    def load(self) -> None:
        if self._model is not None:
            return
        from timesfm3.timesfm3_forecaster import TimesFM3Forecaster  # 延遲 import

        self._model = TimesFM3Forecaster.from_pretrained(
            MODEL_ID,
            device=self.device,
            cache_dir=str(MODEL_CACHE),
        )
        log.info("timesfm3 loaded on %s", self.device)

    def predict(
        self,
        series: pd.Series | np.ndarray | list,
        horizon: int = 7,
        quantiles: list[float] | None = None,
        past_only_covariates: np.ndarray | None = None,
    ) -> dict:
        """univariate quantile forecast（spec §6.2 / §6.4 past-only covariates）。"""
        quantiles = quantiles or [0.1, 0.5, 0.9]
        self.load()
        if isinstance(series, pd.Series):
            series = series.to_numpy(dtype=float)
        ctx = np.asarray(series, dtype=float)
        out = self._model.predict(
            ctx,
            horizon=horizon,
            return_quantiles=True,
            past_only_covariates=past_only_covariates,
        )
        # quantiles: (horizon, 9) 對應 [0.1..0.9]
        qmat = np.asarray(out.quantiles)
        idx = {q: NATIVE_QUANTILES.index(q) for q in quantiles}
        level_means = qmat.mean(axis=0)  # horizon 平均
        return {f"p{int(q * 100)}": float(level_means[idx[q]]) for q in quantiles}

    def predict_multivariate(self, series: np.ndarray, horizon: int = 7) -> np.ndarray:
        """multivariate forecast（spec §6.3）。series: (n_variates, history)。"""
        self.load()
        out = self._model.predict(series, horizon=horizon)
        return np.asarray(out.forecast)


def timesfm_forecast(
    adapter: TimesFM3Adapter,
    symbol: str,
    closes: pd.Series,
    horizon: str = "1d",
    horizon_steps: int = 7,
    data_grade: str = "RESEARCH_PROXY",
) -> ForecastOutput:
    q = adapter.predict(closes, horizon=horizon_steps)
    p50 = q["p50"]
    last = float(closes.iloc[-1])
    expected_return = (p50 - last) / last
    direction = "up" if expected_return > 0 else ("down" if expected_return < 0 else "flat")
    return ForecastOutput(
        model="timesfm-3.0",
        symbol=symbol,
        as_of=datetime.now(timezone.utc),
        horizon=horizon,
        point_forecast=p50,
        expected_return=expected_return,
        quantiles=q,
        direction=direction,
        confidence=float(1.0 - (q["p90"] - q["p10"]) / (abs(last) + 1e-9)),
        data_grade=DataGrade(data_grade),
        warnings=[LICENSE_TAG],
    )
