"""Accuracy v2 P2 nested chronological research engine.

The preregistration is frozen in config/accuracy_v2_p2_protocol.yaml and was
pushed before this module was implemented or any candidate model was fit.

P2 is research-only.  Outer-fold results are development information; the
exposed HPQ1 final window is quarantined; promotion evidence can begin only on
new publication origins from 2026-09-28 onward.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
import hashlib
import json
import math
from pathlib import Path
import time
from typing import Any, Callable

import numpy as np
import pandas as pd

from market_ai_hub.automation.data_lake import default_data_root
from market_ai_hub.integrations.yuanta.resolver import ose_last_trading_date
from market_ai_hub.models.baseline_ml import BaselineClassifier
from market_ai_hub.research.accuracy_v2_p1 import jpx_report_publication_for_session
from market_ai_hub.research.accuracy_v2_p2 import P2Protocol, load_p2_protocol
from market_ai_hub.research.historical_prequential import load_jnu_public_source_frame
from market_ai_hub.services.resource_governor import interactive_n_jobs

P2_PREREG_COMMIT = "53386f54740e2bcd0706140f6c4df5aeb80facab"
P2_ENGINE_SCHEMA_VERSION = "AV2P2E.1"


@dataclass(frozen=True)
class P2Sample:
    origin_date: date
    target_date: date
    contract_month: str
    partition: str
    decision_time: datetime
    label_available_at: datetime
    origin_price: float
    actual_price: float
    target_return: float
    features: dict[str, float]
    source_hash: str
    target_source_hash: str

    @property
    def sample_id(self) -> str:
        payload = {
            "origin_date": str(self.origin_date),
            "target_date": str(self.target_date),
            "contract_month": self.contract_month,
            "decision_time": self.decision_time.isoformat(),
            "label_available_at": self.label_available_at.isoformat(),
            "origin_price": self.origin_price,
            "actual_price": self.actual_price,
            "features": self.features,
            "source_hash": self.source_hash,
            "target_source_hash": self.target_source_hash,
        }
        raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()[:24]


@dataclass(frozen=True)
class P2Fold:
    fold_id: int
    train: tuple[P2Sample, ...]
    test: tuple[P2Sample, ...]


def _normalize_source_frame(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"contract_month", "date", "settlement"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"missing P2 source columns: {sorted(missing)}")
    df = frame.copy()
    df["contract_month"] = df["contract_month"].astype(str)
    df["date"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    df["settlement"] = pd.to_numeric(df["settlement"], errors="coerce")
    if "source_hash" not in df.columns:
        df["source_hash"] = ""
    df["source_hash"] = df["source_hash"].fillna("").astype(str)
    df = df.dropna(subset=["date", "settlement"])
    df = df[np.isfinite(df["settlement"]) & (df["settlement"] > 0)]
    return (
        df.sort_values(["contract_month", "date", "source_hash"])
        .drop_duplicates(["contract_month", "date"], keep="last")
        .reset_index(drop=True)
    )


def _partition(origin: date, protocol: P2Protocol) -> str | None:
    if origin <= protocol.development_origin_end:
        return "DEVELOPMENT"
    if protocol.quarantine_start <= origin <= protocol.quarantine_end:
        return "EXPOSED_QUARANTINE"
    if origin >= protocol.final_holdout_start:
        return "FINAL_FORWARD"
    return None


def _feature_names(protocol: P2Protocol) -> list[str]:
    return [str(x) for x in protocol.raw["feature_set"]["names"]]


def _make_features(
    settlements: pd.Series,
    *,
    publication_day_of_week: int,
    days_to_expiry: int,
) -> dict[str, float] | None:
    returns = settlements.astype(float).pct_change(fill_method=None).dropna()
    if len(returns) < 20:
        return None
    features: dict[str, float] = {}
    for lag in range(1, 6):
        features[f"lag_return_{lag}"] = float(returns.iloc[-lag])
    last5 = returns.iloc[-5:]
    last20 = returns.iloc[-20:]
    features["rolling_mean_return_5"] = float(last5.mean())
    features["rolling_volatility_5"] = float(last5.std(ddof=1))
    features["rolling_volatility_20"] = float(last20.std(ddof=1))
    features["publication_day_of_week"] = float(publication_day_of_week)
    features["days_to_contract_expiry"] = float(days_to_expiry)
    if not all(math.isfinite(v) for v in features.values()):
        return None
    return features


def build_p2_samples(
    frame: pd.DataFrame | None = None,
    *,
    protocol: P2Protocol | None = None,
    publication_fn: Callable[[str | date], datetime] = jpx_report_publication_for_session,
) -> list[P2Sample]:
    """Build one causal exact-contract sample per publication origin.

    The current exact-contract settlement must already be public at decision
    time.  The label is the next *published* exact-contract observation, not a
    guessed next OSE session settlement.
    """
    p = protocol or load_p2_protocol()
    df = _normalize_source_frame(load_jnu_public_source_frame() if frame is None else frame)
    candidates: dict[date, list[P2Sample]] = {}
    history_len = int(p.raw["history_len"])

    for contract, group in df.groupby("contract_month", sort=True):
        if len(contract) != 6 or not contract.isdigit():
            continue
        expiry = ose_last_trading_date(int(contract[:4]), int(contract[4:]))
        g = group.sort_values("date").reset_index(drop=True)
        for pos in range(history_len - 1, len(g) - 1):
            origin_date = g.loc[pos, "date"]
            target_date = g.loc[pos + 1, "date"]
            if origin_date > expiry or target_date > expiry:
                continue
            part = _partition(origin_date, p)
            if part is None:
                continue

            origin_publication = publication_fn(origin_date)
            decision_time = origin_publication + timedelta(minutes=5)
            label_available_at = publication_fn(target_date)
            if label_available_at <= decision_time:
                # If holiday aggregation makes two rows simultaneously public,
                # the latter is not a future target from this decision point.
                continue

            context = g.iloc[pos - history_len + 1 : pos + 1]
            if len(context) != history_len:
                continue
            features = _make_features(
                context["settlement"],
                publication_day_of_week=decision_time.weekday(),
                days_to_expiry=(expiry - origin_date).days,
            )
            if features is None:
                continue
            origin_price = float(g.loc[pos, "settlement"])
            actual_price = float(g.loc[pos + 1, "settlement"])
            target_return = actual_price / origin_price - 1.0
            if not math.isfinite(target_return):
                continue
            sample = P2Sample(
                origin_date=origin_date,
                target_date=target_date,
                contract_month=contract,
                partition=part,
                decision_time=decision_time,
                label_available_at=label_available_at,
                origin_price=origin_price,
                actual_price=actual_price,
                target_return=float(target_return),
                features=features,
                source_hash=str(g.loc[pos, "source_hash"]),
                target_source_hash=str(g.loc[pos + 1, "source_hash"]),
            )
            candidates.setdefault(origin_date, []).append(sample)

    out: list[P2Sample] = []
    for origin_date in sorted(candidates):
        # YYYYMM lexical order is expiry order; choose nearest exact contract.
        out.append(sorted(candidates[origin_date], key=lambda x: x.contract_month)[0])
    return out


def source_fingerprint(samples: list[P2Sample]) -> str:
    payload = [
        {
            "sample_id": x.sample_id,
            "partition": x.partition,
            "target_return": x.target_return,
        }
        for x in samples
    ]
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def chronological_folds(
    samples: list[P2Sample],
    *,
    minimum_train_origins: int,
    test_origins_per_fold: int,
    maximum_folds: int,
    embargo_origins: int,
) -> list[P2Fold]:
    """Expanding folds with an origin embargo and true label-availability purge."""
    ordered = sorted(samples, key=lambda x: (x.decision_time, x.origin_date, x.contract_month))
    folds: list[P2Fold] = []
    for fold_id in range(maximum_folds):
        test_start = minimum_train_origins + embargo_origins + fold_id * test_origins_per_fold
        if test_start >= len(ordered):
            break
        test_end = min(len(ordered), test_start + test_origins_per_fold)
        test = ordered[test_start:test_end]
        if not test:
            break
        train_end = max(0, test_start - embargo_origins)
        cutoff = test[0].decision_time
        train = [x for x in ordered[:train_end] if x.label_available_at <= cutoff]
        if len(train) < minimum_train_origins:
            continue
        folds.append(P2Fold(fold_id=fold_id, train=tuple(train), test=tuple(test)))
    return folds


def _xy(samples: tuple[P2Sample, ...] | list[P2Sample], protocol: P2Protocol) -> tuple[pd.DataFrame, np.ndarray]:
    names = _feature_names(protocol)
    X = pd.DataFrame([[s.features[n] for n in names] for s in samples], columns=names)
    y = np.asarray([s.target_return for s in samples], dtype=float)
    return X, y


def _fit_predict_ridge(
    train: tuple[P2Sample, ...] | list[P2Sample],
    test: tuple[P2Sample, ...] | list[P2Sample],
    *,
    alpha: float,
    protocol: P2Protocol,
) -> np.ndarray:
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    X_train, y_train = _xy(train, protocol)
    X_test, _ = _xy(test, protocol)
    model = Pipeline([
        ("scale", StandardScaler()),
        ("ridge", Ridge(alpha=float(alpha), fit_intercept=True)),
    ])
    model.fit(X_train, y_train)
    return np.asarray(model.predict(X_test), dtype=float)


def _fit_predict_lightgbm(
    train: tuple[P2Sample, ...] | list[P2Sample],
    test: tuple[P2Sample, ...] | list[P2Sample],
    *,
    setting: dict[str, Any],
    seed: int,
    protocol: P2Protocol,
) -> np.ndarray:
    import lightgbm as lgb

    X_train, y_train = _xy(train, protocol)
    X_test, _ = _xy(test, protocol)
    params = {
        **setting,
        "objective": "regression_l1",
        "random_state": int(seed),
        "n_jobs": interactive_n_jobs(),
        "verbosity": -1,
    }
    model = lgb.LGBMRegressor(**params)
    model.fit(X_train, y_train)
    return np.asarray(model.predict(X_test), dtype=float)


def _family_settings(protocol: P2Protocol, family: str) -> list[dict[str, Any]]:
    raw = protocol.raw["model_families"]
    if family == "ridge_return":
        return [{"alpha": float(x)} for x in raw[family]["alphas"]]
    if family == "lightgbm_return":
        return [dict(x) for x in raw[family]["settings"]]
    raise KeyError(family)


def _predict_family(
    family: str,
    train: tuple[P2Sample, ...] | list[P2Sample],
    test: tuple[P2Sample, ...] | list[P2Sample],
    setting: dict[str, Any],
    *,
    protocol: P2Protocol,
) -> np.ndarray:
    seed = int(protocol.raw["search_budget"]["seeds"][0])
    if family == "ridge_return":
        return _fit_predict_ridge(train, test, alpha=float(setting["alpha"]), protocol=protocol)
    if family == "lightgbm_return":
        return _fit_predict_lightgbm(train, test, setting=setting, seed=seed, protocol=protocol)
    raise KeyError(family)


def _tune_family(
    family: str,
    train_samples: tuple[P2Sample, ...] | list[P2Sample],
    *,
    protocol: P2Protocol,
    outer_fold_id: int | str,
) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    cfg = protocol.raw["chronological_validation"]
    inner = cfg["inner"]
    purge = cfg["purge"]
    folds = chronological_folds(
        list(train_samples),
        minimum_train_origins=int(inner["minimum_train_origins"]),
        test_origins_per_fold=int(inner["validation_origins_per_fold"]),
        maximum_folds=int(inner["maximum_folds"]),
        embargo_origins=int(purge["embargo_origins"]),
    )
    settings = _family_settings(protocol, family)
    max_settings = int(protocol.raw["search_budget"]["maximum_settings_per_family"])
    trials: list[dict[str, Any]] = []
    for setting_index, setting in enumerate(settings[:max_settings]):
        actual: list[float] = []
        predicted: list[float] = []
        planned = sum(len(f.test) for f in folds)
        failures: list[str] = []
        for fold in folds:
            actual.extend(float(s.target_return) for s in fold.test)
            try:
                pred = _predict_family(family, fold.train, fold.test, setting, protocol=protocol)
                if len(pred) != len(fold.test) or not np.isfinite(pred).all():
                    raise ValueError("nonfinite or wrong-length prediction")
                predicted.extend(float(x) for x in pred)
            except Exception as exc:
                failures.append(f"inner_fold_{fold.fold_id}:{type(exc).__name__}:{exc}")
        coverage = float(len(predicted) / planned) if planned else 0.0
        observed_mae = (
            float(np.mean(np.abs(np.asarray(predicted) - np.asarray(actual[:len(predicted)]))))
            if predicted else None
        )
        eligible = bool(
            planned > 0
            and coverage >= float(protocol.raw["selection"]["required_inner_same_origin_coverage"])
            and not failures
        )
        trial = {
            "outer_fold_id": outer_fold_id,
            "family": family,
            "setting_index": setting_index,
            "setting": setting,
            "seed": int(protocol.raw["search_budget"]["seeds"][0]),
            "planned_inner_origins": planned,
            "predicted_inner_origins": len(predicted),
            "coverage": coverage,
            "observed_mae_return": observed_mae,
            "eligible": eligible,
            "status": "OK" if eligible else "FAILED_OR_INCOMPLETE",
            "failures": failures,
        }
        trials.append(trial)
    eligible_trials = [t for t in trials if t["eligible"] and t["observed_mae_return"] is not None]
    if not eligible_trials:
        return None, trials
    # Preregistered tie rule: lowest inner OOF MAE, then config order.
    best = min(eligible_trials, key=lambda x: (x["observed_mae_return"], x["setting_index"]))
    return dict(best["setting"]), trials


def _direction_class(value: float, threshold: float) -> int:
    return 1 if value > threshold else (-1 if value < -threshold else 0)


def _fit_predict_logistic(
    train: tuple[P2Sample, ...],
    test: tuple[P2Sample, ...],
    *,
    protocol: P2Protocol,
) -> tuple[list[int | None], list[dict[str, float] | None], str | None]:
    X_train, y_return = _xy(train, protocol)
    X_test, _ = _xy(test, protocol)
    threshold = float(protocol.raw["model_families"]["logistic_direction"]["flat_threshold"])
    y = np.asarray([_direction_class(x, threshold) for x in y_return], dtype=int)
    if len(np.unique(y)) < 2:
        return [None] * len(test), [None] * len(test), "training_labels_single_class"
    try:
        model = BaselineClassifier("lr")
        model.fit(X_train, y)
        pred = [int(x) for x in model.predict(X_test)]
        raw = np.asarray(model.predict_proba(X_test), dtype=float)
        classes = [int(x) for x in model.model.classes_]
        probs = []
        for row in raw:
            mapping = {str(c): 0.0 for c in (-1, 0, 1)}
            for c, value in zip(classes, row):
                mapping[str(c)] = float(value)
            probs.append(mapping)
        return pred, probs, None
    except Exception as exc:
        return [None] * len(test), [None] * len(test), f"{type(exc).__name__}:{exc}"


def _majority_class(train: tuple[P2Sample, ...], threshold: float) -> int:
    labels = np.asarray([_direction_class(x.target_return, threshold) for x in train], dtype=int)
    values, counts = np.unique(labels, return_counts=True)
    return int(values[int(np.argmax(counts))])


def _circular_block_bootstrap(
    deltas: np.ndarray,
    *,
    block_length: int,
    replicates: int,
    confidence: float,
    seed: int,
) -> dict[str, Any]:
    values = np.asarray(deltas, dtype=float)
    n = len(values)
    out = {
        "n": n,
        "block_length": int(block_length),
        "replicates": int(replicates),
        "confidence": float(confidence),
        "ci_lower": None,
        "ci_upper": None,
    }
    if n < 5 or not np.isfinite(values).all():
        return out
    blocks = int(np.ceil(n / block_length))
    rng = np.random.default_rng(seed)
    starts = rng.integers(0, n, size=(replicates, blocks))
    offsets = np.arange(block_length, dtype=int)
    idx = (starts[:, :, None] + offsets[None, None, :]) % n
    idx = idx.reshape(replicates, -1)[:, :n]
    means = values[idx].mean(axis=1)
    alpha = (1.0 - confidence) / 2.0
    out["ci_lower"] = float(np.quantile(means, alpha))
    out["ci_upper"] = float(np.quantile(means, 1.0 - alpha))
    return out


def _return_metrics(rows: list[dict[str, Any]], pred_key: str, protocol: P2Protocol) -> dict[str, Any]:
    total = len(rows)
    observed = [r for r in rows if r.get(pred_key) is not None and math.isfinite(float(r[pred_key]))]
    coverage = float(len(observed) / total) if total else 0.0
    out: dict[str, Any] = {
        "n_planned": total,
        "n_predicted": len(observed),
        "same_origin_coverage": coverage,
        "mae_return": None,
        "rmse_return": None,
        "tail_absolute_error_p90": None,
        "direction_accuracy": None,
        "delta_candidate_minus_naive_mae": None,
        "paired_delta_ci": None,
    }
    if not observed:
        return out
    actual = np.asarray([float(r["actual_return"]) for r in observed], dtype=float)
    pred = np.asarray([float(r[pred_key]) for r in observed], dtype=float)
    error = pred - actual
    abs_error = np.abs(error)
    naive_abs = np.abs(actual)
    delta = abs_error - naive_abs
    threshold = float(protocol.raw["model_families"]["logistic_direction"]["flat_threshold"])
    pred_cls = np.asarray([_direction_class(x, threshold) for x in pred], dtype=int)
    actual_cls = np.asarray([_direction_class(x, threshold) for x in actual], dtype=int)
    uncertainty = protocol.raw["uncertainty"]
    out.update({
        "mae_return": float(abs_error.mean()),
        "rmse_return": float(np.sqrt(np.mean(error ** 2))),
        "tail_absolute_error_p90": float(np.quantile(abs_error, 0.9)),
        "direction_accuracy": float((pred_cls == actual_cls).mean()),
        "delta_candidate_minus_naive_mae": float(delta.mean()),
        "paired_delta_ci": _circular_block_bootstrap(
            delta,
            block_length=int(uncertainty["block_length_publication_origins"]),
            replicates=int(uncertainty["replicates"]),
            confidence=float(uncertainty["confidence"]),
            seed=int(uncertainty["seed"]),
        ),
    })
    return out


def _direction_metrics(rows: list[dict[str, Any]], protocol: P2Protocol) -> dict[str, Any]:
    threshold = float(protocol.raw["model_families"]["logistic_direction"]["flat_threshold"])
    total = len(rows)
    observed = [r for r in rows if r.get("logistic_class") is not None and r.get("logistic_prob") is not None]
    if not observed:
        return {"n_planned": total, "n_predicted": 0, "coverage": 0.0, "log_loss": None,
                "balanced_accuracy": None, "majority_accuracy": None}
    y_true = np.asarray([_direction_class(float(r["actual_return"]), threshold) for r in observed], dtype=int)
    y_pred = np.asarray([int(r["logistic_class"]) for r in observed], dtype=int)
    losses = []
    for y, row in zip(y_true, observed):
        p = max(1e-15, float(row["logistic_prob"].get(str(int(y)), 0.0)))
        losses.append(-math.log(p))
    from sklearn.metrics import balanced_accuracy_score
    return {
        "n_planned": total,
        "n_predicted": len(observed),
        "coverage": float(len(observed) / total) if total else 0.0,
        "log_loss": float(np.mean(losses)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, y_pred)),
        "majority_accuracy": float(np.mean([
            int(r["majority_class"]) == _direction_class(float(r["actual_return"]), threshold)
            for r in observed
        ])),
    }


def _selection_from_metrics(
    metrics: dict[str, dict[str, Any]],
    protocol: P2Protocol,
) -> str:
    required_coverage = float(protocol.raw["selection"]["required_outer_same_origin_coverage"])
    candidates = []
    for family in protocol.raw["selection"]["eligible_return_candidates"]:
        m = metrics.get(family) or {}
        if (
            m.get("mae_return") is not None
            and float(m.get("same_origin_coverage") or 0.0) >= required_coverage
            and float(m.get("delta_candidate_minus_naive_mae") or 0.0) < 0.0
        ):
            candidates.append((family, float(m["mae_return"])))
    if not candidates:
        return "zero_return_naive"
    candidates.sort(key=lambda x: x[1])
    if len(candidates) > 1:
        tolerance = float(protocol.raw["selection"]["tie_tolerance"])
        if abs(candidates[0][1] - candidates[1][1]) <= tolerance:
            preference = str(protocol.raw["selection"]["tie_preference"])
            if any(x[0] == preference for x in candidates[:2]):
                return preference
    return candidates[0][0]


def run_p2_development(
    frame: pd.DataFrame | None = None,
    *,
    protocol: P2Protocol | None = None,
    publication_fn: Callable[[str | date], datetime] = jpx_report_publication_for_session,
) -> dict[str, Any]:
    p = protocol or load_p2_protocol()
    started = time.monotonic()
    samples = build_p2_samples(frame, protocol=p, publication_fn=publication_fn)
    development = [x for x in samples if x.partition == "DEVELOPMENT"]
    quarantine = [x for x in samples if x.partition == "EXPOSED_QUARANTINE"]
    final = [x for x in samples if x.partition == "FINAL_FORWARD"]
    cfg = p.raw["chronological_validation"]
    outer_cfg = cfg["outer"]
    purge = cfg["purge"]
    outer_folds = chronological_folds(
        development,
        minimum_train_origins=int(outer_cfg["minimum_train_origins"]),
        test_origins_per_fold=int(outer_cfg["test_origins_per_fold"]),
        maximum_folds=int(outer_cfg["maximum_folds"]),
        embargo_origins=int(purge["embargo_origins"]),
    )
    if not outer_folds:
        return {
            "status": "DATA_NOT_READY",
            "schema_version": P2_ENGINE_SCHEMA_VERSION,
            "protocol_id": p.protocol_id,
            "protocol_hash": p.hash,
            "prereg_commit": P2_PREREG_COMMIT,
            "sample_counts": {
                "development": len(development),
                "exposed_quarantine": len(quarantine),
                "final_forward": len(final),
            },
            "reason": "INSUFFICIENT_DEVELOPMENT_ORIGINS_FOR_OUTER_WALK_FORWARD",
            "evidence_grade": "ENGINEERING_ONLY",
        }

    rows: list[dict[str, Any]] = []
    trial_ledger: list[dict[str, Any]] = []
    wall_budget = float(p.raw["search_budget"]["maximum_wall_seconds"])
    for fold in outer_folds:
        if time.monotonic() - started > wall_budget:
            return {
                "status": "RUNTIME_BUDGET_EXCEEDED",
                "protocol_id": p.protocol_id,
                "protocol_hash": p.hash,
                "prereg_commit": P2_PREREG_COMMIT,
                "trial_ledger": trial_ledger,
                "outer_oof_ledger": rows,
            }
        chosen: dict[str, dict[str, Any] | None] = {}
        for family in ("ridge_return", "lightgbm_return"):
            setting, trials = _tune_family(family, fold.train, protocol=p, outer_fold_id=fold.fold_id)
            chosen[family] = setting
            trial_ledger.extend(trials)

        family_predictions: dict[str, list[float | None]] = {}
        family_errors: dict[str, str | None] = {}
        for family in ("ridge_return", "lightgbm_return"):
            setting = chosen[family]
            if setting is None:
                family_predictions[family] = [None] * len(fold.test)
                family_errors[family] = "NO_ELIGIBLE_INNER_SETTING"
                continue
            try:
                pred = _predict_family(family, fold.train, fold.test, setting, protocol=p)
                if len(pred) != len(fold.test) or not np.isfinite(pred).all():
                    raise ValueError("nonfinite or wrong-length prediction")
                family_predictions[family] = [float(x) for x in pred]
                family_errors[family] = None
            except Exception as exc:
                family_predictions[family] = [None] * len(fold.test)
                family_errors[family] = f"{type(exc).__name__}:{exc}"

        logistic_class, logistic_prob, logistic_error = _fit_predict_logistic(fold.train, fold.test, protocol=p)
        majority = _majority_class(
            fold.train,
            float(p.raw["model_families"]["logistic_direction"]["flat_threshold"]),
        )
        for i, sample in enumerate(fold.test):
            rows.append({
                "outer_fold_id": fold.fold_id,
                "origin_date": str(sample.origin_date),
                "target_date": str(sample.target_date),
                "contract_month": sample.contract_month,
                "sample_id": sample.sample_id,
                "decision_time": sample.decision_time.isoformat(),
                "label_available_at": sample.label_available_at.isoformat(),
                "actual_return": sample.target_return,
                "zero_return_naive": 0.0,
                "ridge_return": family_predictions["ridge_return"][i],
                "lightgbm_return": family_predictions["lightgbm_return"][i],
                "ridge_setting": chosen["ridge_return"],
                "lightgbm_setting": chosen["lightgbm_return"],
                "ridge_error": family_errors["ridge_return"],
                "lightgbm_error": family_errors["lightgbm_return"],
                "logistic_class": logistic_class[i],
                "logistic_prob": logistic_prob[i],
                "logistic_error": logistic_error,
                "majority_class": majority,
                "train_origin_count": len(fold.train),
                "quarantine_used_for_fit": False,
            })

    metrics = {
        family: _return_metrics(rows, family, p)
        for family in ("zero_return_naive", "ridge_return", "lightgbm_return")
    }
    selected_family = _selection_from_metrics(metrics, p)
    selected_setting: dict[str, Any] | None = None
    final_tuning_trials: list[dict[str, Any]] = []
    if selected_family in {"ridge_return", "lightgbm_return"}:
        selected_setting, final_tuning_trials = _tune_family(
            selected_family, tuple(development), protocol=p, outer_fold_id="FULL_DEVELOPMENT"
        )
        trial_ledger.extend(final_tuning_trials)
        if selected_setting is None:
            selected_family = "zero_return_naive"

    result = {
        "status": "OK",
        "schema_version": P2_ENGINE_SCHEMA_VERSION,
        "protocol_id": p.protocol_id,
        "protocol_hash": p.hash,
        "prereg_commit": P2_PREREG_COMMIT,
        "source_fingerprint_development": source_fingerprint(development),
        "sample_counts": {
            "development": len(development),
            "exposed_quarantine": len(quarantine),
            "final_forward": len(final),
        },
        "quarantine_policy": {
            "used_for_fit": False,
            "used_for_selection": False,
            "used_for_claim": False,
        },
        "outer_fold_count": len(outer_folds),
        "outer_oof_origin_count": len(rows),
        "outer_oof_ledger": rows,
        "trial_ledger": trial_ledger,
        "metrics": metrics,
        "direction_diagnostic": _direction_metrics(rows, p),
        "selection": {
            "family": selected_family,
            "setting": selected_setting,
            "rule": p.raw["selection"]["rule"],
            "development_information_only": True,
        },
        "runtime_seconds": float(time.monotonic() - started),
        "evidence_grade": "DEVELOPMENT_INFORMATION_ONLY",
        "not_final_holdout_evidence": True,
        "not_calibration_evidence": True,
        "not_trading_edge": True,
    }
    raw = json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    result["development_result_id"] = hashlib.sha256(raw).hexdigest()[:24]
    return result


def _artifact_dir(data_root: Path | None = None) -> Path:
    root = data_root or default_data_root()
    return root / "research" / "accuracy_v2_p2" / load_p2_protocol().protocol_id


def save_development_selection(result: dict[str, Any], data_root: Path | None = None) -> Path:
    if result.get("status") != "OK" or result.get("evidence_grade") != "DEVELOPMENT_INFORMATION_ONLY":
        raise ValueError("only completed development results can be frozen")
    out_dir = _artifact_dir(data_root)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "development_selection.json"
    encoded = json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n"
    if path.exists():
        current = path.read_text(encoding="utf-8")
        if current != encoded:
            raise RuntimeError("DEVELOPMENT_SELECTION_ALREADY_FROZEN")
        return path
    path.write_text(encoded, encoding="utf-8")
    return path


def evaluate_final_holdout(
    development_result: dict[str, Any],
    frame: pd.DataFrame | None = None,
    *,
    protocol: P2Protocol | None = None,
    publication_fn: Callable[[str | date], datetime] = jpx_report_publication_for_session,
) -> dict[str, Any]:
    p = protocol or load_p2_protocol()
    if development_result.get("protocol_hash") != p.hash:
        raise ValueError("development result protocol hash mismatch")
    if development_result.get("prereg_commit") != P2_PREREG_COMMIT:
        raise ValueError("development result prereg commit mismatch")
    selection = development_result.get("selection") or {}
    family = str(selection.get("family") or "")
    setting = selection.get("setting")
    samples = build_p2_samples(frame, protocol=p, publication_fn=publication_fn)
    development = [x for x in samples if x.partition == "DEVELOPMENT"]
    final = [x for x in samples if x.partition == "FINAL_FORWARD"]
    required = int(p.raw["promotion"]["required_final_origin_count"])
    if family == "zero_return_naive":
        return {
            "status": p.raw["promotion"]["failed_improvement_status"],
            "reason": "DEVELOPMENT_SELECTION_KEPT_BASELINE",
            "evidence_grade": "DEVELOPMENT_INFORMATION_ONLY",
            "final_not_opened": True,
            "final_origin_count": len(final),
            "required_final_origin_count": required,
            "protocol_hash": p.hash,
            "prereg_commit": P2_PREREG_COMMIT,
            "not_final_holdout_evidence": True,
            "not_calibration_evidence": True,
            "not_trading_edge": True,
        }
    if len(final) < required:
        return {
            "status": p.raw["promotion"]["insufficient_data_status"],
            "reason": "NEW_FORWARD_ORIGINS_BELOW_PRE_REGISTERED_MINIMUM",
            "final_origin_count": len(final),
            "required_final_origin_count": required,
            "protocol_hash": p.hash,
            "prereg_commit": P2_PREREG_COMMIT,
            "not_calibration_evidence": True,
            "not_trading_edge": True,
        }
    if family not in {"ridge_return", "lightgbm_return"} or not isinstance(setting, dict):
        raise ValueError("invalid frozen P2 selection")

    try:
        pred = _predict_family(family, tuple(development), tuple(final), dict(setting), protocol=p)
        predictions = [float(x) if math.isfinite(float(x)) else None for x in pred]
    except Exception as exc:
        predictions = [None] * len(final)
        model_error = f"{type(exc).__name__}:{exc}"
    else:
        model_error = None
    rows = [
        {
            "origin_date": str(s.origin_date),
            "target_date": str(s.target_date),
            "contract_month": s.contract_month,
            "sample_id": s.sample_id,
            "actual_return": s.target_return,
            "zero_return_naive": 0.0,
            family: predictions[i],
            "model_error": model_error,
        }
        for i, s in enumerate(final)
    ]
    metrics = _return_metrics(rows, family, p)
    coverage_ok = metrics["same_origin_coverage"] >= float(
        p.raw["promotion"]["required_same_origin_coverage"]
    )
    ci = metrics.get("paired_delta_ci") or {}
    ci_upper = ci.get("ci_upper")
    delta_ok = (
        metrics.get("delta_candidate_minus_naive_mae") is not None
        and metrics["delta_candidate_minus_naive_mae"] < 0.0
    )
    ci_ok = (
        ci_upper is not None
        and float(ci_upper) < float(p.raw["promotion"]["required_delta_ci_upper_below"])
    )
    passed = bool(coverage_ok and delta_ok and ci_ok)
    return {
        "status": (
            p.raw["promotion"]["success_status"]
            if passed
            else p.raw["promotion"]["failed_improvement_status"]
        ),
        "family": family,
        "setting": setting,
        "final_origin_count": len(final),
        "required_final_origin_count": required,
        "metrics": metrics,
        "protocol_hash": p.hash,
        "prereg_commit": P2_PREREG_COMMIT,
        "development_result_id": development_result.get("development_result_id"),
        "source_fingerprint_final": source_fingerprint(final),
        "records": rows,
        "evidence_grade": "NEW_FORWARD_P2_FINAL" if passed else "NEW_FORWARD_P2_NO_IMPROVEMENT",
        "not_calibration_evidence": True,
        "not_trading_edge": True,
    }


def save_final_evidence(result: dict[str, Any], data_root: Path | None = None) -> Path:
    if result.get("status") not in {"PREDICTIVE_GAIN_CANDIDATE", "NO_IMPROVEMENT"}:
        raise ValueError("final evidence can be sealed only after preregistered minimum is reached")
    if int(result.get("final_origin_count") or 0) < int(result.get("required_final_origin_count") or 0):
        raise ValueError("cannot seal under-minimum final evidence")
    out_dir = _artifact_dir(data_root)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "final_evidence.json"
    encoded = json.dumps(result, sort_keys=True, indent=2, allow_nan=False) + "\n"
    if path.exists():
        current = path.read_text(encoding="utf-8")
        if current != encoded:
            raise RuntimeError("P2_FINAL_EVIDENCE_ALREADY_OPENED")
        return path
    path.write_text(encoded, encoding="utf-8")
    return path
