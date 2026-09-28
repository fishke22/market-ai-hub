"""Chronos-2 adapter（spec §5 + V1 remediation + V1.1）。

- model_task = PRICE_FORECAST（真 predictive quantile 來源之一）
- predict 回傳 per-step path（每步 p10/p50/p90）
- quantile contract：output 建立時驗證 p10<=p50<=p90；invalid 標記且不得進 ensemble
- forecast_dates：^N225 用 TSE（XTKS）日曆；其他 symbol 用 weekend-only 近似並標 calendar_grade
"""
from __future__ import annotations

from dataclasses import dataclass

import logging
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Mapping, Sequence

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
from market_ai_hub.services.model_governance import (
    expected_model_revision,
    verify_loaded_revision,
)
from market_ai_hub.services.reproducibility import (
    DEFAULT_SEED,
    forecast_config_hash,
    input_hash,
    sampling_metadata,
)

log = logging.getLogger(__name__)

MODEL_ID = "amazon/chronos-2"
MODEL_CACHE = project_root() / "models" / "cache" / "chronos-2"

CHRONOS2_QUANTILES = [0.01, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8, 0.85, 0.9, 0.95, 0.99]
_Q_IDX = {0.1: 2, 0.5: 10, 0.9: 18}

class ChronosCovariateContractError(ValueError):
    """Fail-closed P3-A covariate contract violation."""


@dataclass(frozen=True)
class ChronosPastCovariate:
    """Causal past-only covariate with per-observation PIT provenance."""

    values: pd.Series | np.ndarray | Sequence[float]
    event_time: Sequence[datetime] | pd.DatetimeIndex
    available_at: Sequence[datetime] | pd.DatetimeIndex
    source_hashes: Sequence[str]
    feature_version: str


def _aware_utc_iso(value: datetime, *, field: str) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ChronosCovariateContractError(f"{field}: timezone-aware datetime required")
    return value.astimezone(timezone.utc).isoformat()


def _hash_json(payload: object) -> str:
    raw = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _validate_target(series: pd.Series | np.ndarray | list) -> np.ndarray:
    arr = np.asarray(series, dtype=float)
    if arr.ndim != 1 or arr.size < 1:
        raise ChronosCovariateContractError("target must be a non-empty 1-D series")
    if not np.isfinite(arr).all():
        raise ChronosCovariateContractError("target contains non-finite values")
    return arr


def prepare_chronos_past_covariates(
    target: pd.Series | np.ndarray | list,
    past_covariates: Mapping[str, ChronosPastCovariate],
    *,
    decision_time: datetime,
) -> tuple[dict[str, np.ndarray], dict]:
    """Validate P3-A PIT semantics and return Chronos-native covariates + identity."""
    target_arr = _validate_target(target)
    decision_iso = _aware_utc_iso(decision_time, field="decision_time")
    decision_utc = decision_time.astimezone(timezone.utc)
    target_index_hash = None
    if isinstance(target, pd.Series):
        target_index_hash = _hash_json([str(x) for x in target.index])
    if not past_covariates:
        raise ChronosCovariateContractError("past_covariates cannot be empty")

    prepared: dict[str, np.ndarray] = {}
    identities: list[dict] = []
    for raw_name in sorted(past_covariates):
        name = str(raw_name).strip()
        if not name or name == "target":
            raise ChronosCovariateContractError("covariate name is empty or reserved")
        cov = past_covariates[raw_name]
        if not isinstance(cov, ChronosPastCovariate):
            raise ChronosCovariateContractError(
                f"{name}: ChronosPastCovariate with PIT provenance is required"
            )
        feature_version = str(cov.feature_version or "").strip()
        if not feature_version:
            raise ChronosCovariateContractError(f"{name}: feature_version is required")

        values = np.asarray(cov.values, dtype=float)
        if values.ndim != 1 or values.size != target_arr.size:
            raise ChronosCovariateContractError(
                f"{name}: values length must equal target history length {target_arr.size}"
            )
        if not np.isfinite(values).all():
            raise ChronosCovariateContractError(f"{name}: non-finite covariate value")

        event_times = list(cov.event_time)
        available_times = list(cov.available_at)
        source_hashes = [str(x).strip() for x in cov.source_hashes]
        if len(event_times) != target_arr.size or len(available_times) != target_arr.size:
            raise ChronosCovariateContractError(
                f"{name}: event_time/available_at length must equal target history length"
            )
        if len(source_hashes) != target_arr.size or any(not x for x in source_hashes):
            raise ChronosCovariateContractError(
                f"{name}: one non-empty source_hash is required per observation"
            )

        event_iso: list[str] = []
        available_iso: list[str] = []
        event_utc: list[datetime] = []
        for i, (event, available) in enumerate(zip(event_times, available_times)):
            event_s = _aware_utc_iso(event, field=f"{name}.event_time[{i}]")
            available_s = _aware_utc_iso(available, field=f"{name}.available_at[{i}]")
            event_u = event.astimezone(timezone.utc)
            available_u = available.astimezone(timezone.utc)
            if event_u > available_u:
                raise ChronosCovariateContractError(
                    f"{name}[{i}]: event_time exceeds available_at"
                )
            if available_u > decision_utc:
                raise ChronosCovariateContractError(
                    f"{name}[{i}]: FUTURE_AVAILABLE_AT exceeds decision_time"
                )
            event_utc.append(event_u)
            event_iso.append(event_s)
            available_iso.append(available_s)
        if any(b <= a for a, b in zip(event_utc, event_utc[1:])):
            raise ChronosCovariateContractError(
                f"{name}: event_time must be strictly increasing with no duplicates"
            )

        if isinstance(target, pd.Series) and isinstance(cov.values, pd.Series):
            if not target.index.equals(cov.values.index):
                raise ChronosCovariateContractError(
                    f"{name}: pandas index must exactly match target index"
                )

        value_hash = hashlib.sha256(
            np.asarray(values, dtype=np.float32).tobytes()
        ).hexdigest()
        provenance = {
            "name": name,
            "feature_version": feature_version,
            "observation_count": int(values.size),
            "first_event_time": event_iso[0],
            "last_event_time": event_iso[-1],
            "max_available_at": max(available_iso),
            "value_hash": value_hash,
            "source_hash": _hash_json(source_hashes),
        }
        provenance["identity_hash"] = _hash_json(
            {
                **provenance,
                "event_time": event_iso,
                "available_at": available_iso,
                "source_hashes": source_hashes,
            }
        )
        prepared[name] = values
        identities.append(provenance)

    identity = {
        "contract": "CHRONOS2_PAST_ONLY_PIT_P3A",
        "decision_time": decision_iso,
        "covariate_names": [x["name"] for x in identities],
        "covariate_count": len(identities),
        "target_index_hash": target_index_hash,
        "covariates": identities,
    }
    identity["identity_hash"] = _hash_json(identity)
    return prepared, identity


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

    def status_shallow(self) -> str:
        """不 load weights、不 import chronos（health/status 用）。回 LOADED_READY / AVAILABLE_NOT_LOADED / UNAVAILABLE。"""
        if self._pipeline is not None:
            return "LOADED_READY"
        import importlib.util

        pkg_ok = importlib.util.find_spec("chronos") is not None
        cache_ok = MODEL_CACHE.exists() and any(MODEL_CACHE.rglob("*"))
        if pkg_ok or cache_ok:
            return "AVAILABLE_NOT_LOADED"
        return "UNAVAILABLE"

    def load(self) -> None:
        if self._pipeline is not None:
            return
        from chronos import BaseChronosPipeline  # 延遲 import，避免模組級成本

        revision = expected_model_revision("chronos-2")
        self._pipeline = BaseChronosPipeline.from_pretrained(
            MODEL_ID,
            revision=revision,
            device_map=self.device,
            cache_dir=str(MODEL_CACHE),
        )
        self._revision_evidence = verify_loaded_revision("chronos-2", self._pipeline)
        log.info("chronos-2 loaded on %s revision=%s verified=%s", self.device, revision, self._revision_evidence["local_verified"])

    def predict(
        self,
        series: pd.Series | np.ndarray | list,
        horizon: int = 7,
        quantiles: list[float] | None = None,
        *,
        past_covariates: Mapping[str, ChronosPastCovariate] | None = None,
        future_covariates: Mapping[str, object] | None = None,
        decision_time: datetime | None = None,
    ) -> dict:
        """多步預測；P3-A 僅允許有完整 PIT provenance 的 past-only covariates。"""
        quantiles = quantiles or [0.1, 0.5, 0.9]
        unsupported = sorted(set(quantiles) - set(_Q_IDX))
        if unsupported:
            raise ValueError(f"unsupported Chronos quantiles: {unsupported}")
        if horizon < 1:
            raise ValueError("horizon must be >= 1")
        if future_covariates is not None:
            raise ChronosCovariateContractError(
                "FUTURE_COVARIATES_BLOCKED_P3A: only past-only covariates are allowed"
            )

        arr = _validate_target(series)
        covariate_identity: dict | None = None
        prepared_covariates: dict[str, np.ndarray] | None = None
        if past_covariates is not None:
            if decision_time is None:
                raise ChronosCovariateContractError(
                    "decision_time is required when past_covariates are provided"
                )
            prepared_covariates, covariate_identity = prepare_chronos_past_covariates(
                series,
                past_covariates,
                decision_time=decision_time,
            )

        self.load()
        if prepared_covariates is None:
            context = torch.tensor(arr, dtype=torch.float32).view(1, 1, -1)
            out = self._pipeline.predict(context, prediction_length=horizon)
        else:
            out = self._pipeline.predict(
                [{
                    "target": arr,
                    "past_covariates": prepared_covariates,
                }],
                prediction_length=horizon,
            )
        t = out[0].cpu().numpy()
        if t.size != len(CHRONOS2_QUANTILES) * horizon:
            raise RuntimeError(
                f"unexpected Chronos output size={t.size}; "
                f"expected={len(CHRONOS2_QUANTILES) * horizon}"
            )
        t = t.reshape(1, len(CHRONOS2_QUANTILES), horizon)
        path = {}
        for q in quantiles:
            i = _Q_IDX[q]
            path[f"p{int(q * 100)}"] = [float(v) for v in t[0, i, :]]
        metadata = {
            "covariate_contract": "CHRONOS2_PAST_ONLY_PIT_P3A",
            "past_only_covariates_used": prepared_covariates is not None,
            "future_covariates_allowed": False,
            "covariate_identity": covariate_identity,
        }
        self._last_predict_metadata = metadata
        return {"path": path, "metadata": metadata}


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
    past_covariates: Mapping[str, ChronosPastCovariate] | None = None,
    future_covariates: Mapping[str, object] | None = None,
    decision_time: datetime | None = None,
) -> ForecastOutput:
    spec: HorizonSpec = parse_horizon(horizon, data_frequency)
    if not spec.supported:
        raise HorizonUnsupportedError(spec.reason)
    steps = spec.effective_horizon_steps
    seed = DEFAULT_SEED if seed is None else seed

    if past_covariates is not None or future_covariates is not None:
        r = adapter.predict(
            closes,
            horizon=steps,
            past_covariates=past_covariates,
            future_covariates=future_covariates,
            decision_time=decision_time,
        )
    else:
        r = adapter.predict(closes, horizon=steps)
    path_q = r["path"]
    adapter_metadata = dict(
        r.get("metadata") or getattr(adapter, "_last_predict_metadata", {}) or {}
    )
    last = float(closes.iloc[-1])
    anchor = _calendar_dates(symbol, closes.index[-1], steps)
    dates = anchor["forecast_target_dates"]

    # V1.3 reproducibility（Chronos-2 為 deterministic quantile，無 MC sampling）
    base_input_hash = input_hash(closes)
    covariate_identity = adapter_metadata.get("covariate_identity")
    input_hash_v = (
        hashlib.sha256(
            f"{base_input_hash}|{covariate_identity.get('identity_hash')}".encode("utf-8")
        ).hexdigest()[:16]
        if isinstance(covariate_identity, dict) and covariate_identity.get("identity_hash")
        else base_input_hash
    )
    base_cfg_hash = forecast_config_hash(
        MODEL_ID,
        horizon,
        steps,
        [0.1, 0.5, 0.9],
        seed,
        data_frequency,
    )
    cfg_hash = hashlib.sha256(
        (
            f"{base_cfg_hash}|past_only_covariates={past_covariates is not None}"
            "|future_covariates=false"
        ).encode("utf-8")
    ).hexdigest()[:16]
    revision = getattr(adapter, "_revision_evidence", {}).get("expected_revision") or expected_model_revision("chronos-2")

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
        model_metadata={
            "quantile_source": "chronos-2 native 21 quantiles",
            "revision_evidence": getattr(adapter, "_revision_evidence", {}),
            "upstream_supports_covariates": True,
            "adapter_implements_covariates": True,
            "adapter_implements_past_only_covariates": True,
            "future_covariates_allowed_p3a": False,
            "past_only_covariates_used": past_covariates is not None,
            "covariate_identity": covariate_identity,
        },
        warnings=warnings,
    )
    return fo.attach_build(build_fingerprint())
