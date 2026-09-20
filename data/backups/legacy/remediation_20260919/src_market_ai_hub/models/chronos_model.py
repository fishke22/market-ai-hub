"""Chronos-2 adapter（spec §5）。

唯一官方來源：amazon/chronos-2 (HF)，chronos-forecasting 套件，Apache-2.0。
chronos-forecasting >= 2.x：輸入 3-d (batch, n_variates, history)，
輸出 (batch, n_quantiles, horizon)，21 個固定 quantiles：
[0.01, 0.05, 0.1, 0.15, ..., 0.9, 0.95, 0.99]。
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

MODEL_ID = "amazon/chronos-2"
MODEL_CACHE = project_root() / "models" / "cache" / "chronos-2"

CHRONOS2_QUANTILES = [0.01, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 0.99]


class ChronosAdapter:
    """包裝 BaseChronosPipeline。CPU 或 CUDA 皆可載入。"""

    def __init__(self, device: str | None = None) -> None:
        self._pipeline = None
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")

    def status(self) -> str:
        try:
            self.load()
            return "ready"
        except Exception as e:
            log.warning("chronos load failed: %s", e)
            return "unavailable"

    def load(self) -> None:
        if self._pipeline is not None:
            return
        from chronos import BaseChronosPipeline  # 延遲 import，避免模組級成本

        self._pipeline = BaseChronosPipeline.from_pretrained(
            MODEL_ID,
            device_map=self.device,
            cache_dir=str(MODEL_CACHE),
        )
        log.info("chronos-2 loaded on %s", self.device)

    def predict(
        self,
        series: pd.Series | np.ndarray | list,
        horizon: int = 7,
        quantiles: list[float] | None = None,
    ) -> dict:
        """預測。quantiles 預設 [0.1, 0.5, 0.9]（spec §5.4），從 21 個原生 quantiles 挑選。"""
        quantiles = quantiles or [0.1, 0.5, 0.9]
        self.load()
        if isinstance(series, pd.Series):
            series = series.to_numpy(dtype=float)
        arr = np.asarray(series, dtype=float)
        # 傳 CPU tensor：chronos2 pipeline 自行處理 device + pin_memory
        context = torch.tensor(arr, dtype=torch.float32).view(1, 1, -1)
        out = self._pipeline.predict(context, prediction_length=horizon)
        # out: list[torch.Tensor]，每 element (batch, n_quantiles, horizon)
        t = out[0].cpu().numpy()
        t = t.reshape(1, len(CHRONOS2_QUANTILES), horizon)
        # 對 horizon 各 step 取平均 -> 該 quantile 的代表值
        level_vals = t[0, :, :].mean(axis=1)
        idx_map = {q: i for i, q in enumerate(CHRONOS2_QUANTILES)}
        return {f"p{int(q * 100)}": float(level_vals[idx_map[q]]) for q in quantiles}


def chronos_forecast(
    adapter: ChronosAdapter,
    symbol: str,
    closes: pd.Series,
    horizon: str = "1d",
    horizon_steps: int = 7,
    data_grade: str = "RESEARCH_PROXY",
) -> ForecastOutput:
    """把 Chronos quantile 輸出轉成統一 ForecastOutput（spec §22）。"""
    q = adapter.predict(closes, horizon=horizon_steps)
    p50 = q["p50"]
    last = float(closes.iloc[-1])
    expected_return = (p50 - last) / last
    direction = "up" if expected_return > 0 else ("down" if expected_return < 0 else "flat")
    return ForecastOutput(
        model="chronos-2",
        symbol=symbol,
        as_of=datetime.now(timezone.utc),
        horizon=horizon,
        point_forecast=p50,
        expected_return=expected_return,
        quantiles=q,
        direction=direction,
        confidence=float(1.0 - (q["p90"] - q["p10"]) / (abs(last) + 1e-9)),
        data_grade=DataGrade(data_grade),
        warnings=[],
    )
