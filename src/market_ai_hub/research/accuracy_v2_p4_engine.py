"""Accuracy v2 P4 robust analysis path for periods with no new forward outcome.

This package does not promote a new point champion.  It preserves the P2 zero-return
baseline and adds development-only risk/interval diagnostics plus a fixed LightGBM
quantile challenger.  Post-development public history may be used as current causal
feature context, never as labels for reselection or a new performance claim.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import math
import time
from typing import Any

import numpy as np
import pandas as pd

from market_ai_hub.integrations.open_source_research import open_source_adapter_status
from market_ai_hub.integrations.yuanta.resolver import ose_last_trading_date
from market_ai_hub.research.accuracy_v2_p1 import jpx_report_publication_for_session
from market_ai_hub.research.accuracy_v2_p2 import load_p2_protocol
from market_ai_hub.research.accuracy_v2_p2_engine import (
    P2Sample,
    _feature_names,
    _make_features,
    build_p2_samples,
    chronological_folds,
)
from market_ai_hub.research.accuracy_v2_p4 import P4Protocol, load_p4_protocol
from market_ai_hub.research.future_data_acquisition import future_data_readiness
from market_ai_hub.services.calendar import next_ose_derivatives_sessions
from market_ai_hub.services.jnu_direct import load_direct_micro_settlements


P4_ENGINE_SCHEMA_VERSION = "AV2P4E.1"
_ANALYSIS_CACHE: dict[str, dict[str, Any]] = {}
_MAX_CACHE_ENTRIES = 8


def _finite(values: list[float] | np.ndarray) -> np.ndarray:
    arr = np.asarray(values, dtype=float)
    return arr[np.isfinite(arr)]


def _higher_quantile(values: list[float] | np.ndarray, probability: float) -> float:
    """Finite-sample upper empirical quantile used by the fixed conformal rule."""
    arr = np.sort(_finite(values))
    if len(arr) == 0:
        raise ValueError("quantile requires finite values")
    p = min(max(float(probability), 0.0), 1.0)
    rank = int(math.ceil((len(arr) + 1) * p))
    rank = min(max(rank, 1), len(arr))
    return float(arr[rank - 1])


def ewma_return_volatility(returns: pd.Series, decay_lambda: float) -> float:
    arr = _finite(pd.Series(returns, dtype=float).to_numpy())
    if len(arr) == 0:
        raise ValueError("EWMA volatility requires finite returns")
    lam = float(decay_lambda)
    if not 0.0 < lam < 1.0:
        raise ValueError("EWMA decay must be in (0,1)")
    variance = float(arr[0] ** 2)
    for value in arr[1:]:
        variance = lam * variance + (1.0 - lam) * float(value ** 2)
    return float(math.sqrt(max(variance, 0.0)))


def _interval_score(y: float, lower: float, upper: float, alpha: float) -> float:
    width = float(upper - lower)
    score = width
    if y < lower:
        score += (2.0 / alpha) * (lower - y)
    elif y > upper:
        score += (2.0 / alpha) * (y - upper)
    return float(score)


def development_conformal_diagnostic(
    samples: list[P2Sample],
    *,
    protocol: P4Protocol | None = None,
) -> dict[str, Any]:
    """Chronological development-only interval evaluation with label maturity."""
    p = protocol or load_p4_protocol()
    cfg = p.raw["conformal"]
    development = sorted(
        [s for s in samples if s.partition == "DEVELOPMENT"],
        key=lambda x: (x.decision_time, x.origin_date),
    )
    minimum = int(cfg["minimum_residual_count"])
    max_buffer = int(cfg["maximum_residual_buffer"])
    coverages = [float(x) for x in cfg["nominal_coverages"]]
    adaptive_cfg = cfg["adaptive_challenger"]
    target_alpha = float(adaptive_cfg["initial_alpha"])
    current_alpha = target_alpha
    gamma = float(adaptive_cfg["gamma"])
    alpha_min = float(adaptive_cfg["alpha_min"])
    alpha_max = float(adaptive_cfg["alpha_max"])

    residual_buffer: list[float] = []
    pending: list[dict[str, Any]] = []
    static_rows: dict[float, list[dict[str, float]]] = {c: [] for c in coverages}
    adaptive_rows: list[dict[str, float]] = []

    for sample in development:
        still_pending: list[dict[str, Any]] = []
        for item in pending:
            if item["label_available_at"] <= sample.decision_time:
                residual_buffer.append(float(item["residual"]))
                if len(residual_buffer) > max_buffer:
                    residual_buffer = residual_buffer[-max_buffer:]
                if item.get("adaptive_miss") is not None:
                    current_alpha = float(np.clip(
                        current_alpha + gamma * (target_alpha - float(item["adaptive_miss"])),
                        alpha_min,
                        alpha_max,
                    ))
            else:
                still_pending.append(item)
        pending = still_pending

        actual = float(sample.target_return)
        residual = abs(actual)  # zero-return baseline error
        adaptive_miss: float | None = None

        if len(residual_buffer) >= minimum:
            for coverage in coverages:
                alpha = 1.0 - coverage
                radius = _higher_quantile(residual_buffer, coverage)
                lower, upper = -radius, radius
                covered = float(lower <= actual <= upper)
                static_rows[coverage].append({
                    "covered": covered,
                    "width": upper - lower,
                    "score": _interval_score(actual, lower, upper, alpha),
                })

            radius = _higher_quantile(residual_buffer, 1.0 - current_alpha)
            lower, upper = -radius, radius
            adaptive_miss = float(not (lower <= actual <= upper))
            adaptive_rows.append({
                "covered": 1.0 - adaptive_miss,
                "width": upper - lower,
                "score": _interval_score(actual, lower, upper, target_alpha),
                "alpha_used": current_alpha,
            })

        pending.append({
            "label_available_at": sample.label_available_at,
            "residual": residual,
            "adaptive_miss": adaptive_miss,
        })

    metrics: dict[str, Any] = {}
    for coverage, rows in static_rows.items():
        key = f"{coverage:.2f}"
        metrics[key] = {
            "n": len(rows),
            "empirical_coverage": float(np.mean([r["covered"] for r in rows])) if rows else None,
            "mean_interval_width_return": float(np.mean([r["width"] for r in rows])) if rows else None,
            "mean_interval_score": float(np.mean([r["score"] for r in rows])) if rows else None,
        }
    adaptive = {
        "n": len(adaptive_rows),
        "target_coverage": 1.0 - target_alpha,
        "empirical_coverage": float(np.mean([r["covered"] for r in adaptive_rows])) if adaptive_rows else None,
        "mean_interval_width_return": float(np.mean([r["width"] for r in adaptive_rows])) if adaptive_rows else None,
        "mean_interval_score": float(np.mean([r["score"] for r in adaptive_rows])) if adaptive_rows else None,
        "final_alpha": current_alpha,
    }
    return {
        "status": "OK" if any(v["n"] for v in metrics.values()) else "INSUFFICIENT_DEVELOPMENT_HISTORY",
        "evidence_grade": "DEVELOPMENT_ONLY_INTERVAL_DIAGNOSTIC",
        "static": metrics,
        "adaptive": adaptive,
        "development_origin_count": len(development),
        "quarantine_used": False,
        "final_forward_used": False,
        "not_calibrated_probability": True,
        "not_predictive_gain": True,
    }


def _pinball_loss(actual: np.ndarray, predicted: np.ndarray, alpha: float) -> float:
    error = actual - predicted
    loss = np.maximum(float(alpha) * error, (float(alpha) - 1.0) * error)
    return float(np.mean(loss))


def development_quantile_diagnostic(
    samples: list[P2Sample],
    *,
    protocol: P4Protocol | None = None,
) -> dict[str, Any]:
    """Fixed-setting chronological OOF quantile diagnostic on development only.

    This is package-validation evidence, not part of the current-analysis latency path.
    It performs no hyperparameter selection and never sees quarantine/final labels.
    """
    p4 = protocol or load_p4_protocol()
    p2 = load_p2_protocol()
    development = [s for s in samples if s.partition == "DEVELOPMENT"]
    outer = p2.raw["chronological_validation"]["outer"]
    purge = p2.raw["chronological_validation"]["purge"]
    folds = chronological_folds(
        development,
        minimum_train_origins=int(outer["minimum_train_origins"]),
        test_origins_per_fold=int(outer["test_origins_per_fold"]),
        maximum_folds=int(outer["maximum_folds"]),
        embargo_origins=int(purge["embargo_origins"]),
    )
    if not folds:
        return {
            "status": "INSUFFICIENT_DEVELOPMENT_HISTORY",
            "development_origin_count": len(development),
            "quarantine_used": False,
            "final_forward_used": False,
        }

    try:
        from lightgbm import LGBMRegressor
    except Exception as exc:
        return {
            "status": "MODEL_UNAVAILABLE",
            "reason": type(exc).__name__,
            "quarantine_used": False,
            "final_forward_used": False,
        }

    cfg = p4.raw["quantile_challenger"]
    setting = dict(cfg["setting"])
    names = _feature_names(p2)
    alphas = [float(x) for x in cfg["alphas"]]
    predictions: dict[float, list[float]] = {a: [] for a in alphas}
    actual: list[float] = []
    origin_ids: list[str] = []
    fit_count = 0
    started = time.perf_counter()

    for fold in folds:
        x_train = np.asarray([[s.features[n] for n in names] for s in fold.train], dtype=float)
        y_train = np.asarray([s.target_return for s in fold.train], dtype=float)
        x_test = np.asarray([[s.features[n] for n in names] for s in fold.test], dtype=float)
        if not np.isfinite(x_train).all() or not np.isfinite(y_train).all() or not np.isfinite(x_test).all():
            return {
                "status": "NONFINITE_FEATURE",
                "quarantine_used": False,
                "final_forward_used": False,
            }
        fold_preds: dict[float, np.ndarray] = {}
        for alpha in alphas:
            model = LGBMRegressor(
                objective="quantile",
                alpha=alpha,
                n_estimators=int(setting["n_estimators"]),
                learning_rate=float(setting["learning_rate"]),
                max_depth=int(setting["max_depth"]),
                num_leaves=int(setting["num_leaves"]),
                min_child_samples=int(setting["min_child_samples"]),
                reg_lambda=float(setting["reg_lambda"]),
                random_state=int(setting["random_state"]),
                n_jobs=1,
                verbosity=-1,
            )
            model.fit(x_train, y_train)
            fold_preds[alpha] = np.asarray(model.predict(x_test), dtype=float)
            fit_count += 1

        for i, sample in enumerate(fold.test):
            actual.append(float(sample.target_return))
            origin_ids.append(sample.sample_id)
            for alpha in alphas:
                predictions[alpha].append(float(fold_preds[alpha][i]))

    y = np.asarray(actual, dtype=float)
    pred = {a: np.asarray(v, dtype=float) for a, v in predictions.items()}
    crossing = (pred[0.10] > pred[0.50]) | (pred[0.50] > pred[0.90])
    interval_covered = (y >= pred[0.10]) & (y <= pred[0.90])
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    return {
        "status": "OK",
        "evidence_grade": "DEVELOPMENT_OOF_QUANTILE_DIAGNOSTIC",
        "development_origin_count": len(development),
        "outer_fold_count": len(folds),
        "oof_origin_count": len(y),
        "same_origin_coverage": float(len(y) / sum(len(f.test) for f in folds)) if folds else 0.0,
        "pinball_loss": {
            f"q{int(a * 100):02d}": _pinball_loss(y, pred[a], a)
            for a in alphas
        },
        "p10_p90_empirical_coverage": float(np.mean(interval_covered)) if len(y) else None,
        "mean_p10_p90_width_return": float(np.mean(pred[0.90] - pred[0.10])) if len(y) else None,
        "quantile_crossing_rate": float(np.mean(crossing)) if len(y) else None,
        "model_fit_count": fit_count,
        "elapsed_ms": elapsed_ms,
        "quarantine_used": False,
        "final_forward_used": False,
        "not_forward_evidence": True,
        "not_calibrated_probability": True,
        "not_point_champion_selection": True,
        "origin_digest": hashlib.sha256(
            json.dumps(origin_ids, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:24],
    }


def _fit_quantile_challenger(
    development: list[P2Sample],
    current_features: dict[str, float],
    *,
    protocol: P4Protocol,
) -> dict[str, Any]:
    cfg = protocol.raw["quantile_challenger"]
    names = _feature_names(load_p2_protocol())
    usable = [
        s for s in development
        if s.partition == "DEVELOPMENT" and all(name in s.features for name in names)
    ]
    if len(usable) < 32:
        return {
            "status": "INSUFFICIENT_DEVELOPMENT_HISTORY",
            "fit_origin_count": len(usable),
            "not_validated": True,
        }
    try:
        from lightgbm import LGBMRegressor
    except Exception as exc:
        return {"status": "MODEL_UNAVAILABLE", "reason": type(exc).__name__, "not_validated": True}

    x_train = np.asarray([[s.features[name] for name in names] for s in usable], dtype=float)
    y_train = np.asarray([s.target_return for s in usable], dtype=float)
    x_current = np.asarray([[current_features[name] for name in names]], dtype=float)
    if not np.isfinite(x_train).all() or not np.isfinite(y_train).all() or not np.isfinite(x_current).all():
        return {"status": "NONFINITE_FEATURE", "not_validated": True}

    setting = dict(cfg["setting"])
    predictions: dict[str, float] = {}
    started = time.perf_counter()
    for alpha in [float(x) for x in cfg["alphas"]]:
        model = LGBMRegressor(
            objective="quantile",
            alpha=alpha,
            n_estimators=int(setting["n_estimators"]),
            learning_rate=float(setting["learning_rate"]),
            max_depth=int(setting["max_depth"]),
            num_leaves=int(setting["num_leaves"]),
            min_child_samples=int(setting["min_child_samples"]),
            reg_lambda=float(setting["reg_lambda"]),
            random_state=int(setting["random_state"]),
            n_jobs=1,
            verbosity=-1,
        )
        model.fit(x_train, y_train)
        predictions[f"q{int(round(alpha * 100)):02d}"] = float(model.predict(x_current)[0])
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    values = [predictions["q10"], predictions["q50"], predictions["q90"]]
    if not all(math.isfinite(v) for v in values):
        return {"status": "NONFINITE_PREDICTION", "not_validated": True}
    if not values[0] <= values[1] <= values[2]:
        return {
            "status": "QUANTILE_CROSSING_BLOCKED",
            "return_quantiles": predictions,
            "fit_origin_count": len(usable),
            "elapsed_ms": elapsed_ms,
            "not_validated": True,
        }
    return {
        "status": "CHALLENGER_UNVALIDATED",
        "return_quantiles": predictions,
        "fit_origin_count": len(usable),
        "elapsed_ms": elapsed_ms,
        "model_fits": 3,
        "tuning": "NONE",
        "fit_partition": "DEVELOPMENT_ONLY",
        "may_replace_point_champion": False,
        "not_validated": True,
    }


def _content_key(series: pd.Series, meta: dict[str, Any], protocol: P4Protocol) -> str:
    payload = {
        "contract_month": meta.get("contract_month"),
        "latest_date": meta.get("latest_date"),
        "index": [str(x) for x in series.index],
        "values": [float(x) for x in series.to_numpy(dtype=float)],
        "p4_protocol_hash": protocol.hash,
        "p2_protocol_hash": load_p2_protocol().hash,
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()[:24]


def analyze_no_new_forward_outcome(
    *,
    current_series: pd.Series | None = None,
    current_meta: dict[str, Any] | None = None,
    samples: list[P2Sample] | None = None,
    protocol: P4Protocol | None = None,
    use_cache: bool = True,
) -> dict[str, Any]:
    """Build a useful current JNU analysis without claiming new forward evidence."""
    p = protocol or load_p4_protocol()
    series: pd.Series
    meta: dict[str, Any]
    if current_series is None or current_meta is None:
        series, meta = load_direct_micro_settlements("")
    else:
        series, meta = current_series.copy(), dict(current_meta)
    if meta.get("status") != "OK":
        return {"status": "DATA_NOT_READY", "data": meta}
    if len(series) < int(p.raw["baseline_analysis"]["minimum_history"]):
        return {
            "status": "INSUFFICIENT_HISTORY",
            "sample_count": len(series),
            "minimum": int(p.raw["baseline_analysis"]["minimum_history"]),
        }

    key = _content_key(series, meta, p)
    if use_cache and key in _ANALYSIS_CACHE:
        cached = dict(_ANALYSIS_CACHE[key])
        cached["cache_hit"] = True
        return cached

    started = time.perf_counter()
    p2 = load_p2_protocol()
    all_samples = build_p2_samples() if samples is None else list(samples)
    development = [s for s in all_samples if s.partition == "DEVELOPMENT"]

    month = str(meta["contract_month"])
    latest_date = str(meta["latest_date"])
    expiry = ose_last_trading_date(int(month[:4]), int(month[4:]))
    publication = jpx_report_publication_for_session(latest_date)
    current_features = _make_features(
        series,
        publication_day_of_week=publication.weekday(),
        days_to_expiry=(expiry - pd.Timestamp(latest_date).date()).days,
    )
    if current_features is None:
        return {"status": "INSUFFICIENT_FEATURE_HISTORY", "data": meta}
    names = _feature_names(p2)
    if set(current_features) != set(names):
        return {
            "status": "FEATURE_IDENTITY_MISMATCH",
            "expected": names,
            "actual": sorted(current_features),
        }

    returns = series.astype(float).pct_change(fill_method=None).dropna()
    vol_cfg = p.raw["volatility"]
    if len(returns) < int(vol_cfg["minimum_return_count"]):
        return {"status": "INSUFFICIENT_VOLATILITY_HISTORY", "data": meta}
    ewma_vol = ewma_return_volatility(returns, float(vol_cfg["decay_lambda"]))

    dev_vol = np.asarray(
        [float(s.features["rolling_volatility_20"]) for s in development if math.isfinite(float(s.features["rolling_volatility_20"]))],
        dtype=float,
    )
    vol_threshold = float(np.median(dev_vol)) if len(dev_vol) else None
    regime = (
        "HIGH_VOLATILITY"
        if vol_threshold is not None and current_features["rolling_volatility_20"] > vol_threshold
        else "LOW_VOLATILITY"
        if vol_threshold is not None
        else "UNKNOWN"
    )

    conformal = development_conformal_diagnostic(all_samples, protocol=p)
    residuals = [
        abs(float(s.target_return))
        for s in development
        if math.isfinite(float(s.target_return))
    ]
    conformal_cfg = p.raw["conformal"]
    max_buffer = int(conformal_cfg["maximum_residual_buffer"])
    residuals = residuals[-max_buffer:]
    primary_coverage = float(conformal_cfg["primary_nominal_coverage"])
    current_radius = (
        _higher_quantile(residuals, primary_coverage)
        if len(residuals) >= int(conformal_cfg["minimum_residual_count"])
        else None
    )

    quantile = _fit_quantile_challenger(development, current_features, protocol=p)
    reference = float(series.iloc[-1])
    if current_radius is not None:
        empirical_interval = {
            "status": "DEVELOPMENT_FIT_UNVALIDATED_FORWARD",
            "nominal_coverage": primary_coverage,
            "return_radius": current_radius,
            "lower_price": reference * (1.0 - current_radius),
            "upper_price": reference * (1.0 + current_radius),
            "not_probability": True,
        }
    else:
        empirical_interval = {"status": "INSUFFICIENT_DEVELOPMENT_HISTORY", "not_probability": True}

    q_prices: dict[str, float] = {}
    if quantile.get("status") == "CHALLENGER_UNVALIDATED":
        q_prices = {
            key_name: reference * (1.0 + float(value))
            for key_name, value in quantile["return_quantiles"].items()
        }
    quantile["price_quantiles"] = q_prices

    target_dates = next_ose_derivatives_sessions(latest_date, 1)
    next_session = target_dates[0] if target_dates else None
    label_available = (
        jpx_report_publication_for_session(next_session).isoformat()
        if next_session else None
    )
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    result = {
        "status": "OK",
        "schema_version": P4_ENGINE_SCHEMA_VERSION,
        "analysis_mode": "NO_NEW_FORWARD_OUTCOME_SAFE",
        "protocol_id": p.protocol_id,
        "protocol_hash": p.hash,
        "cache_identity": key,
        "cache_hit": False,
        "target": {
            "instrument": "JNU",
            "exact_contract": meta["quote_code"],
            "contract_month": month,
            "target_measure": p.raw["target_measure"],
            "next_session_date": next_session,
            "label_available_at": label_available,
        },
        "data": {
            "latest_date": latest_date,
            "latest_settlement": reference,
            "sample_count": int(len(series)),
            "series_semantics": meta.get("series_semantics"),
            "price_semantics": meta.get("price_semantics"),
        },
        "point_reference": {
            "method": "ZERO_RETURN_NAIVE_LAST_AVAILABLE_SETTLEMENT",
            "price": reference,
            "expected_return": 0.0,
            "champion_status": "BASELINE_RETAINED_NO_PREDICTIVE_GAIN",
        },
        "volatility": {
            "ewma_return_volatility": ewma_vol,
            "decay_lambda": float(vol_cfg["decay_lambda"]),
            "regime": regime,
            "development_regime_threshold": vol_threshold,
            "role": "DESCRIPTIVE_RISK_CONTEXT_ONLY",
        },
        "empirical_interval": empirical_interval,
        "conformal_development_diagnostic": conformal,
        "lightgbm_quantile_challenger": quantile,
        "decision_support": {
            "strong_direction_allowed": False,
            "abstain_reason": "NO_PREDICTIVE_GAIN_CANDIDATE",
            "baseline_analysis_allowed": True,
            "conditional_scenarios_allowed": True,
            "calibrated_probability_available": False,
            "not_trading_edge": True,
        },
        "forward_data_readiness": future_data_readiness(),
        "open_source_adapter_status": open_source_adapter_status(),
        "evidence_grade": "DEVELOPMENT_ONLY_PLUS_CURRENT_CAUSAL_CONTEXT",
        "development_label_count": len(development),
        "quarantine_used_for_fit": False,
        "quarantine_used_for_selection": False,
        "final_forward_used": False,
        "elapsed_ms": elapsed_ms,
    }
    if use_cache:
        if len(_ANALYSIS_CACHE) >= _MAX_CACHE_ENTRIES:
            _ANALYSIS_CACHE.pop(next(iter(_ANALYSIS_CACHE)))
        _ANALYSIS_CACHE[key] = dict(result)
    return result
