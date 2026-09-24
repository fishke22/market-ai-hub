"""Phase 2D.1 — 新 Challenger Adapters（NHITS / NBEATSx via neuralforecast）。

fit-on-the-fly（在 history window 上訓練，等同統計 baseline，非 foundation fine-tune）。
遵守 information_cutoff：只用 history df 內資料。future covariates 只用 known future（本輪不提供）。
"""
from __future__ import annotations

import pandas as pd

from market_ai_hub.research.tournament.adapter import ForecastResult, ModelAdapter


def _closes(df: pd.DataFrame) -> pd.Series:
    return df.sort_values("timestamp_utc")["close"].dropna()


class _NeuralForecastAdapter(ModelAdapter):
    task = "price"
    _model_name = "nhits"

    def __init__(self) -> None:
        self.name = self._model_name

    def forecast(self, df, steps):
        try:
            from neuralforecast import NeuralForecast
            from neuralforecast.models import NHITS as model_cls
        except Exception as e:
            return ForecastResult(point=None, warnings=[f"{self.name} import failed: {type(e).__name__}"])
        closes = _closes(df)
        if len(closes) < 30:
            return ForecastResult(point=None, warnings=[f"{self.name} insufficient data"])
        nf_df = pd.DataFrame({
            "unique_id": "1",
            "ds": pd.to_datetime(closes.index),
            "y": closes.values,
        })
        input_size = min(64, len(closes) - steps)
        try:
            model = model_cls(h=steps, input_size=input_size, max_steps=100)
            nf = NeuralForecast(models=[model], freq="D")
            nf.fit(nf_df)
            fc = nf.predict()
            col = model_cls.__name__  # 預測欄位名 = 模型類別名（NHITS / NBEATSx）
            point = float(fc[fc["unique_id"] == "1"][col].iloc[-1])
        except Exception as e:
            return ForecastResult(point=None, warnings=[f"{self.name} failed: {type(e).__name__}"])
        direction = "up" if point > closes.iloc[-1] else ("down" if point < closes.iloc[-1] else "flat")
        return ForecastResult(point=point, direction=direction, quantile_valid=None,
                              warnings=["neuralforecast fit-on-the-fly: point only"])


class NHITSAdapter(_NeuralForecastAdapter):
    _model_name = "nhits"
    revision = "3.2.2"

class NBEATSxAdapter(_NeuralForecastAdapter):
    _model_name = "nbeatsx"
    revision = "3.2.2"

    def __init__(self) -> None:
        super().__init__()
        # 只用 identity block（trend/seasonality 與短 horizon h=1 衝突）
        self._nbeatsx_kwargs = {"stack_types": ["identity"], "n_blocks": [3],
                                "random_seed": 42, "max_steps": 100}

    def forecast(self, df, steps):
        # 覆寫：NBEATSx 需額外參數
        try:
            from neuralforecast import NeuralForecast
            from neuralforecast.models import NBEATSx as model_cls
        except Exception as e:
            return ForecastResult(point=None, warnings=[f"{self.name} import failed: {type(e).__name__}"])

        closes = _closes(df)
        if len(closes) < 30:
            return ForecastResult(point=None, warnings=[f"{self.name} insufficient data"])
        nf_df = pd.DataFrame({"unique_id": "1", "ds": pd.to_datetime(closes.index), "y": closes.values})
        input_size = min(64, len(closes) - steps)
        try:
            model = model_cls(h=steps, input_size=input_size, **self._nbeatsx_kwargs)
            nf = NeuralForecast(models=[model], freq="D")
            nf.fit(nf_df)
            fc = nf.predict()
            col = model_cls.__name__
            point = float(fc[fc["unique_id"] == "1"][col].iloc[-1])
        except Exception as e:
            return ForecastResult(point=None, warnings=[f"{self.name} failed: {type(e).__name__}"])
        direction = "up" if point > closes.iloc[-1] else ("down" if point < closes.iloc[-1] else "flat")
        return ForecastResult(point=point, direction=direction, quantile_valid=None,
                              warnings=["neuralforecast fit-on-the-fly: point only"])
