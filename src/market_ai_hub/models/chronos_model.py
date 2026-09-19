"""Chronos-2 adapter（spec §5 + V1 remediation + V1.1）。

- model_task = PRICE_FORECAST（真 predictive quantile 來源之一）
- predict 回傳 per-step path（每步 p10/p50/p90）
- quantile contract：output 建立時驗證 p10<=p50<=p90；invalid 標記且不得進 ensemble
- forecast_dates：^N225 用 TSE（XTKS）日曆；其他 symbol 用 weekend-only 近似並標 calendar_grade
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from market_ai_hub.config.settings import project_root
from market_ai_hub.schemas.market_data import (
    DataGrade,
    EngineeringStatus,
    ForecastOutput,
    ModelRole,
    ModelTask,
    PredictiveValidationStatus,
    QuantileType,
    validate_quantiles,
)
from market_ai_hub.services.build_info import build_fingerprint
from market_ai_hub.services.horizon import (
    HorizonSpec,
    HorizonUnsupportedError,
    parse_horizon,
)
from market_ai_hub.services.market_session import quote_freshness
from market_ai_hub.services.reproducibility import (
    DEFAULT_SEED,
    forecast_config_hash,
    input_hash,
    model_revision_local,
    sampling_metadata,
)

log = logging.getLogger(__name__)

MODEL_ID = "amazon/chronos-2"
MODEL_CACHE = project_root() / "models" / "cache" / "chronos-2"

CHRONOS2_QUANTILES = [0.01, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 0.99]
_Q_IDX = {0.1: 2, 0.5: 10, 0.9: 18}


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
        """多步預測：回傳 {"path": {"p10": [...], "p50": [...], "p90": [...]}}，長度 = horizon。"""
        quantiles = quantiles or [0.1, 0.5, 0.9]
        self.load()
        if isinstance(series, pd.Series):
            series = series.to_numpy(dtype=float)
        arr = np.asarray(series, dtype=float)
        context = torch.tensor(arr, dtype=torch.float32).view(1, 1, -1)
        out = self._pipeline.predict(context, prediction_length=horizon)
        t = out[0].cpu().numpy()
        t = t.reshape(1, len(CHRONOS2_QUANTILES), horizon)
        path = {}
        for q in quantiles:
            i = _Q_IDX[q]
            path[f"p{int(q * 100)}"] = [float(v) for v in t[0, i, :]]
        return {"path": path}


def _calendar_dates(symbol: str, last_ts, steps: int) -> dict:
    """依 symbol 產生 future-only forecast anchor（V1.2，見 services/calendar.forecast_anchor）。"""
    from market_ai_hub.services.calendar import forecast_anchor

    return forecast_anchor(symbol, last_ts, steps)


def chronos_forecast(
    adapter: ChronosAdapter,
    symbol: str,
    closes: pd.Series,
    horizon: str = "1d",
    horizon_steps: int = 7,
    data_grade: str = "RESEARCH_PROXY",
    data_frequency: str = "1d",
    seed: int | None = None,
) -> ForecastOutput:
    spec: HorizonSpec = parse_horizon(horizon, data_frequency)
    if not spec.supported:
        raise HorizonUnsupportedError(spec.reason)
    steps = spec.effective_horizon_steps
    seed = DEFAULT_SEED if seed is None else seed

    r = adapter.predict(closes, horizon=steps)
    path_q = r["path"]
    last = float(closes.iloc[-1])
    anchor = _calendar_dates(symbol, closes.index[-1], steps)
    dates = anchor["forecast_target_dates"]

    # V1.3 reproducibility（Chronos-2 為 deterministic quantile，無 MC sampling）
    input_hash_v = input_hash(closes)
    cfg_hash = forecast_config_hash(MODEL_ID, horizon, steps, [0.1, 0.5, 0.9], seed, data_frequency)
    revision = model_revision_local(MODEL_ID, MODEL_CACHE)
    if revision == "unknown":
        from market_ai_hub.services.reproducibility import model_revision_remote

        revision = model_revision_remote(MODEL_ID)

    # V1.3 market open / quote freshness
    freshened = quote_freshness(symbol, closes.index[-1])

    forecast_path = [
        {
            "step": i + 1,
            "date": dates[i],
            "p10": path_q["p10"][i],
            "p50": path_q["p50"][i],
            "p90": path_q["p90"][i],
        }
        for i in range(steps)
    ]
    terminal = path_q["p50"][-1]
    expected_return = (terminal - last) / last if last else 0.0
    direction = "up" if expected_return > 0 else ("down" if expected_return < 0 else "flat")

    quantiles = {"p10": path_q["p10"][-1], "p50": terminal, "p90": path_q["p90"][-1]}
    q_valid, q_reason = validate_quantiles(quantiles)
    warnings = [] if q_valid else [f"quantile contract violated: {q_reason}"]

    fo = ForecastOutput(
        model="chronos-2",
        symbol=symbol,
        as_of=datetime.now(timezone.utc),
        horizon=horizon,
        point_forecast=terminal,
        expected_return=expected_return,
        quantiles=quantiles,
        direction=direction,
        confidence=float(1.0 - (path_q["p90"][-1] - path_q["p10"][-1]) / (abs(last) + 1e-9)),
        data_grade=DataGrade(data_grade),
        requested_horizon=horizon,
        effective_horizon_steps=steps,
        data_frequency=data_frequency,
        horizon_applied=True,
        forecast_path=forecast_path,
        forecast_dates=dates,
        terminal_forecast=terminal,
        model_role=ModelRole.BASE_MODEL.value,
        engineering_status=EngineeringStatus.PASS.value,
        predictive_validation_status=PredictiveValidationStatus.UNVALIDATED.value,
        eligible_for_price_reference=True,
        eligible_for_direction_vote=False,
        eligible_for_ensemble_weighting=True,
        model_task=ModelTask.PRICE_FORECAST.value,
        quantile_type=QuantileType.PREDICTIVE.value if q_valid else QuantileType.NOT_AVAILABLE.value,
        quantile_valid=q_valid,
        quantile_invalid_reason="" if q_valid else q_reason,
        target_calendar=anchor["target_calendar"],
        target_trading_dates=dates,
        calendar_grade=anchor["calendar_grade"],
        forecast_origin=anchor["forecast_origin"],
        last_observed_trading_date=anchor["last_observed_trading_date"],
        forecast_target_dates=dates,
        exchange_timezone=anchor["exchange_timezone"],
        calendar_name=anchor["calendar_name"],
        calendar_source=anchor["calendar_source"],
        calendar_verified=anchor["calendar_verified"],
        calendar_last_verified=anchor["calendar_last_verified"],
        inference_seed=seed,
        input_data_hash=input_hash_v,
        forecast_config_hash=cfg_hash,
        model_revision=revision,
        model_build_id=build_fingerprint()["build_id"],
        deterministic_mode=True,
        forecast_stochastic=False,
        sampling_config=sampling_metadata(deterministic=True),
        market_open=freshened["market_open"],
        tradable_now=freshened["tradable_now"],
        source_timestamp=freshened["source_timestamp"],
        received_at=freshened["received_at"],
        quote_age_seconds=freshened["quote_age_seconds"],
        freshness_status=freshened["freshness_status"],
        session_status=freshened["session_status"],
        quote_live=freshened["quote_live"],
        usable_for_live_decision=freshened["usable_for_live_decision"],
        model_metadata={"quantile_source": "chronos-2 native 21 quantiles"},
        warnings=warnings,
    )
    return fo.attach_build(build_fingerprint())
