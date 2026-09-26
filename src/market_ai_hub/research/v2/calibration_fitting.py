"""W4.1 governed probability calibration fitting.

Consumes only W3.1 governed EVENT_PROBABILITY manifests backed by the
append-only PredictionAuditDB. FINAL_OOS is never used for fitting or
parameter selection. Synthetic tests prove the engine only.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

import numpy as np
import yaml

from market_ai_hub.config.runtime_paths import data_root, project_root
from market_ai_hub.research.price_probability_map import CalibrationEvidence
from market_ai_hub.research.v2 import calibration_evaluation as CE
from market_ai_hub.research.v2 import evaluation_governance as EG
from market_ai_hub.research.v2 import prediction_audit as PA

W4_CALIBRATION_FITTING_SCHEMA_VERSION = "W4.1"
DEFAULT_PROTOCOL_ID = "w4_ppm_sigmoid_v1"
DEFAULT_PROTOCOL_PATH = project_root() / "config" / "calibration_protocols.yaml"

FIT_STATUSES = (
    "CALIBRATED",
    "EVALUATED_UNCALIBRATED",
    "INSUFFICIENT_EVIDENCE",
    "BLOCKED",
    "ERROR",
)
SUPPORTED_PPM_TYPES = frozenset({"TERMINAL", "TOUCH", "FIRST_PASSAGE"})


class CalibrationFittingError(Exception):
    """Fail-closed W4 fitting contract violation."""


@dataclass(frozen=True)
class CalibrationProtocol:
    protocol_id: str
    method: str
    method_version: str
    calibration_domain: str
    supported_probability_types: tuple[str, ...]
    sample_origin: str
    fit_partition_role: str
    validation_partition_role: str
    min_fit_samples: int
    min_validation_samples: int
    min_final_oos_samples: int
    min_class_count: int
    min_calendar_span_days: int
    require_zero_overlap_pairs: bool
    bootstrap_replicates: int
    bootstrap_seed: int
    confidence_level: float
    require_ci_nondegradation: bool
    clip_epsilon: float
    l2_identity_penalty: float
    max_iterations: int
    tolerance: float
    max_brier_delta: float
    max_log_loss_delta: float
    max_ece_delta: float
    require_strict_improvement: bool
    strict_improvement_epsilon: float
    schema_version: str = W4_CALIBRATION_FITTING_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.method != "SIGMOID":
            raise CalibrationFittingError(f"unsupported calibration method: {self.method!r}")
        if self.calibration_domain != "PRICE_DISTRIBUTION":
            raise CalibrationFittingError("W4.1 PPM fitting requires PRICE_DISTRIBUTION")
        if not self.supported_probability_types:
            raise CalibrationFittingError("supported_probability_types is empty")
        if not set(self.supported_probability_types).issubset(SUPPORTED_PPM_TYPES):
            raise CalibrationFittingError("unsupported PPM probability type")
        if self.sample_origin != "FORWARD_PRECOMMITTED":
            raise CalibrationFittingError("W4.1 fitting requires FORWARD_PRECOMMITTED")
        if self.fit_partition_role != "CALIBRATION":
            raise CalibrationFittingError("fit partition must be CALIBRATION")
        if self.validation_partition_role != "VALIDATION":
            raise CalibrationFittingError("validation partition must be VALIDATION")
        if min(self.min_fit_samples, self.min_validation_samples, self.min_final_oos_samples) < 2:
            raise CalibrationFittingError("sample minimum too small")
        if self.min_class_count < 1 or self.min_calendar_span_days < 1:
            raise CalibrationFittingError("class/span minimum must be positive")
        if self.bootstrap_replicates < 100 or not (0.5 < self.confidence_level < 1.0):
            raise CalibrationFittingError("invalid bootstrap confidence protocol")
        if not (0.0 < self.clip_epsilon < 0.5):
            raise CalibrationFittingError("invalid clip_epsilon")
        if self.l2_identity_penalty < 0.0 or self.max_iterations < 1 or self.tolerance <= 0.0:
            raise CalibrationFittingError("invalid optimizer protocol")

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SigmoidModel:
    slope: float
    intercept: float
    clip_epsilon: float
    converged: bool
    iterations: int

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class CalibrationFitResult:
    status: str
    reason: str
    artifact_id: str
    protocol: CalibrationProtocol
    calibration_dataset_id: str
    validation_dataset_id: str
    final_oos_dataset_id: str = ""
    scope: dict[str, Any] = field(default_factory=dict)
    model: SigmoidModel | None = None
    raw_validation_metrics: dict[str, float] = field(default_factory=dict)
    calibrated_validation_metrics: dict[str, float] = field(default_factory=dict)
    acceptance: dict[str, Any] = field(default_factory=dict)
    evidence: CalibrationEvidence | None = None
    schema_version: str = W4_CALIBRATION_FITTING_SCHEMA_VERSION

    def __post_init__(self) -> None:
        if self.status not in FIT_STATUSES:
            raise CalibrationFittingError(f"unknown fit status: {self.status!r}")

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


def load_protocol(protocol_id: str = DEFAULT_PROTOCOL_ID,
                  path: str | Path | None = None) -> CalibrationProtocol:
    p = Path(path) if path is not None else DEFAULT_PROTOCOL_PATH
    payload = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    if str(payload.get("schema_version")) != W4_CALIBRATION_FITTING_SCHEMA_VERSION:
        raise CalibrationFittingError("calibration protocol schema mismatch")
    raw = (payload.get("protocols") or {}).get(protocol_id)
    if not isinstance(raw, dict):
        raise CalibrationFittingError(f"unknown calibration protocol: {protocol_id}")
    acceptance = raw.get("acceptance") or {}
    return CalibrationProtocol(
        protocol_id=protocol_id,
        method=str(raw.get("method") or ""),
        method_version=str(raw.get("method_version") or ""),
        calibration_domain=str(raw.get("calibration_domain") or ""),
        supported_probability_types=tuple(str(x).upper() for x in raw.get("supported_probability_types") or []),
        sample_origin=str(raw.get("sample_origin") or ""),
        fit_partition_role=str(raw.get("fit_partition_role") or ""),
        validation_partition_role=str(raw.get("validation_partition_role") or ""),
        min_fit_samples=int(raw.get("min_fit_samples") or 0),
        min_validation_samples=int(raw.get("min_validation_samples") or 0),
        min_final_oos_samples=int(raw.get("min_final_oos_samples") or 0),
        min_class_count=int(raw.get("min_class_count") or 0),
        min_calendar_span_days=int(raw.get("min_calendar_span_days") or 0),
        require_zero_overlap_pairs=bool(raw.get("require_zero_overlap_pairs", True)),
        bootstrap_replicates=int(raw.get("bootstrap_replicates") or 0),
        bootstrap_seed=int(raw.get("bootstrap_seed") or 0),
        confidence_level=float(raw.get("confidence_level") or 0.0),
        require_ci_nondegradation=bool(raw.get("require_ci_nondegradation", True)),
        clip_epsilon=float(raw.get("clip_epsilon") or 0.0),
        l2_identity_penalty=float(raw.get("l2_identity_penalty") or 0.0),
        max_iterations=int(raw.get("max_iterations") or 0),
        tolerance=float(raw.get("tolerance") or 0.0),
        max_brier_delta=float(acceptance.get("max_brier_delta") or 0.0),
        max_log_loss_delta=float(acceptance.get("max_log_loss_delta") or 0.0),
        max_ece_delta=float(acceptance.get("max_ece_delta") or 0.0),
        require_strict_improvement=bool(acceptance.get("require_strict_improvement", True)),
        strict_improvement_epsilon=float(acceptance.get("strict_improvement_epsilon") or 0.0),
    )


def _scope_payload(scope: EG.EvaluationScope) -> dict[str, Any]:
    d = asdict(scope)
    d.pop("partition_role", None)
    return d


def _validate_manifest_pair(cal: EG.GovernedEvaluationManifest,
                            val: EG.GovernedEvaluationManifest,
                            protocol: CalibrationProtocol) -> None:
    if cal.scope.partition_role != protocol.fit_partition_role:
        raise CalibrationFittingError("fit manifest must be CALIBRATION")
    if val.scope.partition_role != protocol.validation_partition_role:
        raise CalibrationFittingError("validation manifest must be VALIDATION")
    if _scope_payload(cal.scope) != _scope_payload(val.scope):
        raise CalibrationFittingError("calibration/validation scope mismatch")
    if cal.scope.artifact_type != "EVENT_PROBABILITY":
        raise CalibrationFittingError("W4.1 fits EVENT_PROBABILITY only")
    if cal.scope.calibration_domain != protocol.calibration_domain:
        raise CalibrationFittingError("calibration domain mismatch")
    if cal.scope.probability_type.upper() not in protocol.supported_probability_types:
        raise CalibrationFittingError("probability type not pre-registered")
    if cal.scope.sample_origin != protocol.sample_origin:
        raise CalibrationFittingError("sample origin not pre-registered")
    if cal.is_blocked() or val.is_blocked():
        raise CalibrationFittingError("W3 governance blocked manifest")
    if cal.base_blocked_rejections() or val.base_blocked_rejections():
        raise CalibrationFittingError("2I.1 pairing blocked manifest")
    if cal.window_end > val.window_start:
        raise CalibrationFittingError("calibration/validation windows overlap")
    for name, manifest in (("calibration", cal), ("validation", val)):
        span_days = (manifest.window_end - manifest.window_start).total_seconds() / 86400.0
        if span_days < protocol.min_calendar_span_days:
            raise CalibrationFittingError(f"{name} calendar span below pre-registered minimum")
    if protocol.require_zero_overlap_pairs:
        if int(cal.coverage.get("overlapping_horizon_pair_count") or 0) != 0:
            raise CalibrationFittingError("calibration horizon overlap requires purge")
        if int(val.coverage.get("overlapping_horizon_pair_count") or 0) != 0:
            raise CalibrationFittingError("validation horizon overlap requires purge")


def _member_pairs(db: PA.PredictionAuditDB,
                  manifest: EG.GovernedEvaluationManifest
                  ) -> tuple[list[tuple[float, float]], tuple[str, str]]:
    pairs: list[tuple[float, float]] = []
    distributions: set[tuple[str, str]] = set()
    for member in manifest.members:
        art = db.get_forecast_artifact(member.forecast_artifact_id)
        if art is None or art.prediction_id != member.prediction_id:
            raise CalibrationFittingError("forecast artifact binding missing")
        if art.artifact_type != "EVENT_PROBABILITY":
            raise CalibrationFittingError("non-probability artifact in governed manifest")
        if art.value is None or not math.isfinite(float(art.value)) or not 0.0 <= float(art.value) <= 1.0:
            raise CalibrationFittingError("invalid probability value")
        if not art.distribution_id or not art.distribution_version:
            raise CalibrationFittingError("probability artifact missing distribution identity")
        distributions.add((art.distribution_id, art.distribution_version))
        outs = [o for o in db.get_outcomes(member.prediction_id) if o.outcome_id == member.outcome_id]
        if len(outs) != 1 or outs[0].forecast_artifact_id != member.forecast_artifact_id:
            raise CalibrationFittingError("outcome binding missing or ambiguous")
        y = outs[0].actual_value
        if y not in (0, 0.0, 1, 1.0):
            raise CalibrationFittingError("calibration requires binary outcomes")
        pairs.append((float(art.value), float(y)))
    if len(distributions) != 1:
        raise CalibrationFittingError("mixed or missing distribution identity")
    return pairs, next(iter(distributions))


def _class_counts(pairs: list[tuple[float, float]]) -> tuple[int, int]:
    pos = sum(1 for _, y in pairs if y == 1.0)
    return pos, len(pairs) - pos


def _sigmoid(z: np.ndarray) -> np.ndarray:
    out = np.empty_like(z, dtype=float)
    pos = z >= 0
    out[pos] = 1.0 / (1.0 + np.exp(-z[pos]))
    ez = np.exp(z[~pos])
    out[~pos] = ez / (1.0 + ez)
    return out


def fit_sigmoid(pairs: list[tuple[float, float]],
                protocol: CalibrationProtocol) -> SigmoidModel:
    eps = protocol.clip_epsilon
    p = np.asarray([x for x, _ in pairs], dtype=float)
    y = np.asarray([y for _, y in pairs], dtype=float)
    p = np.clip(p, eps, 1.0 - eps)
    x = np.log(p / (1.0 - p))
    theta = np.asarray([1.0, 0.0], dtype=float)
    converged = False
    iterations = 0
    for i in range(protocol.max_iterations):
        iterations = i + 1
        z = theta[0] * x + theta[1]
        q = _sigmoid(z)
        w = q * (1.0 - q)
        grad = np.asarray([
            np.sum((q - y) * x) + protocol.l2_identity_penalty * (theta[0] - 1.0),
            np.sum(q - y) + protocol.l2_identity_penalty * theta[1],
        ])
        h = np.asarray([
            [np.sum(w * x * x) + protocol.l2_identity_penalty, np.sum(w * x)],
            [np.sum(w * x), np.sum(w) + protocol.l2_identity_penalty],
        ])
        try:
            delta = np.linalg.solve(h, grad)
        except np.linalg.LinAlgError as exc:
            raise CalibrationFittingError("sigmoid optimizer singular") from exc
        theta_next = theta - delta
        if not np.all(np.isfinite(theta_next)):
            raise CalibrationFittingError("sigmoid optimizer nonfinite")
        theta = theta_next
        if float(np.max(np.abs(delta))) <= protocol.tolerance:
            converged = True
            break
    return SigmoidModel(
        slope=float(theta[0]),
        intercept=float(theta[1]),
        clip_epsilon=eps,
        converged=converged,
        iterations=iterations,
    )


def calibrate_probability(model: SigmoidModel, probability: float) -> float:
    p = float(probability)
    if not math.isfinite(p) or not 0.0 <= p <= 1.0:
        raise CalibrationFittingError("probability outside [0,1]")
    pc = min(1.0 - model.clip_epsilon, max(model.clip_epsilon, p))
    x = math.log(pc / (1.0 - pc))
    z = model.slope * x + model.intercept
    if z >= 0:
        return float(1.0 / (1.0 + math.exp(-z)))
    ez = math.exp(z)
    return float(ez / (1.0 + ez))


def _reliability_summary(pairs: list[tuple[float, float]]) -> tuple[float, float, list[dict[str, Any]]]:
    n = len(pairs)
    bins = CE.reliability_bins(pairs)
    ece = sum((b.count / n) * float(b.gap) for b in bins if b.count and b.gap is not None)
    mce = max((float(b.gap) for b in bins if b.count and b.gap is not None), default=0.0)
    return float(ece), float(mce), [b.model_dump() for b in bins]


def _calibration_diagnostic(pairs: list[tuple[float, float]],
                            protocol: CalibrationProtocol) -> dict[str, Any]:
    try:
        model = fit_sigmoid(pairs, protocol)
        return {
            "status": "AVAILABLE" if model.converged else "NOT_CONVERGED",
            "calibration_slope": model.slope if model.converged else None,
            "calibration_intercept": model.intercept if model.converged else None,
        }
    except CalibrationFittingError:
        return {
            "status": "NOT_AVAILABLE",
            "calibration_slope": None,
            "calibration_intercept": None,
        }


def _metrics(pairs: list[tuple[float, float]],
             protocol: CalibrationProtocol) -> dict[str, Any]:
    n = len(pairs)
    ece, mce, bins = _reliability_summary(pairs)
    out: dict[str, Any] = {
        "sample_count": n,
        "brier_score": float(CE.brier_score(pairs)),
        "log_loss": float(CE.log_loss(pairs)),
        "ece": ece,
        "mce": mce,
        "base_rate": float(sum(y for _, y in pairs) / n),
        "mean_probability": float(sum(p for p, _ in pairs) / n),
        "reliability_bins": bins,
        "regime_stability_status": "NOT_AVAILABLE_SCOPE_HAS_NO_REGIME_LABEL",
    }
    out.update(_calibration_diagnostic(pairs, protocol))
    return out


def _metric_triplet(pairs: list[tuple[float, float]]) -> tuple[float, float, float]:
    ece, _, _ = _reliability_summary(pairs)
    return float(CE.brier_score(pairs)), float(CE.log_loss(pairs)), ece


def _paired_delta_ci(raw_pairs: list[tuple[float, float]],
                     calibrated_pairs: list[tuple[float, float]],
                     protocol: CalibrationProtocol) -> dict[str, dict[str, float]]:
    if len(raw_pairs) != len(calibrated_pairs) or not raw_pairs:
        raise CalibrationFittingError("paired bootstrap requires equal non-empty samples")
    n = len(raw_pairs)
    rng = np.random.default_rng(protocol.bootstrap_seed)
    deltas = {"brier": [], "log_loss": [], "ece": []}
    for _ in range(protocol.bootstrap_replicates):
        idx = rng.integers(0, n, size=n)
        raw = [raw_pairs[int(i)] for i in idx]
        cal = [calibrated_pairs[int(i)] for i in idx]
        rb, rl, re = _metric_triplet(raw)
        cb, cl, ce = _metric_triplet(cal)
        deltas["brier"].append(cb - rb)
        deltas["log_loss"].append(cl - rl)
        deltas["ece"].append(ce - re)
    alpha = (1.0 - protocol.confidence_level) / 2.0
    out: dict[str, dict[str, float]] = {}
    for name, values in deltas.items():
        arr = np.asarray(values, dtype=float)
        out[name] = {
            "lower": float(np.quantile(arr, alpha)),
            "upper": float(np.quantile(arr, 1.0 - alpha)),
            "mean": float(np.mean(arr)),
            "confidence_level": protocol.confidence_level,
            "replicates": float(protocol.bootstrap_replicates),
        }
    return out


def _acceptance(raw_metrics: dict[str, Any],
                calibrated_metrics: dict[str, Any],
                model: SigmoidModel,
                protocol: CalibrationProtocol,
                delta_ci: dict[str, dict[str, float]]) -> dict[str, Any]:
    nondegrade = {
        "brier": calibrated_metrics["brier_score"] <= raw_metrics["brier_score"] + protocol.max_brier_delta,
        "log_loss": calibrated_metrics["log_loss"] <= raw_metrics["log_loss"] + protocol.max_log_loss_delta,
        "ece": calibrated_metrics["ece"] <= raw_metrics["ece"] + protocol.max_ece_delta,
        "monotone_slope": model.slope >= 0.0,
    }
    ci_nondegrade = {
        "brier": delta_ci["brier"]["upper"] <= protocol.max_brier_delta,
        "log_loss": delta_ci["log_loss"]["upper"] <= protocol.max_log_loss_delta,
        "ece": delta_ci["ece"]["upper"] <= protocol.max_ece_delta,
    }
    improvements = {
        "brier": raw_metrics["brier_score"] - calibrated_metrics["brier_score"],
        "log_loss": raw_metrics["log_loss"] - calibrated_metrics["log_loss"],
        "ece": raw_metrics["ece"] - calibrated_metrics["ece"],
    }
    strict = any(v > protocol.strict_improvement_epsilon for v in improvements.values())
    accepted = (
        all(nondegrade.values())
        and (all(ci_nondegrade.values()) or not protocol.require_ci_nondegradation)
        and (strict or not protocol.require_strict_improvement)
    )
    return {
        "accepted": accepted,
        "nondegrade": nondegrade,
        "ci_nondegrade": ci_nondegrade,
        "delta_ci": delta_ci,
        "improvements": improvements,
    }


def _member_time_bounds(db: PA.PredictionAuditDB,
                        manifest: EG.GovernedEvaluationManifest) -> tuple[Any, Any]:
    predictions = [db.get_prediction(m.prediction_id) for m in manifest.members]
    if not predictions or any(p is None for p in predictions):
        raise CalibrationFittingError("manifest prediction missing during purge-gap check")
    max_label_end = max(p.label_window_end for p in predictions if p.label_window_end is not None)
    min_origin = min(p.forecast_origin for p in predictions if p.forecast_origin is not None)
    return max_label_end, min_origin


def _require_purge_gap(db: PA.PredictionAuditDB,
                       earlier: EG.GovernedEvaluationManifest,
                       later: EG.GovernedEvaluationManifest,
                       label: str) -> None:
    earlier_end, _ = _member_time_bounds(db, earlier)
    _, later_origin = _member_time_bounds(db, later)
    if earlier_end is None or later_origin is None or earlier_end > later_origin:
        raise CalibrationFittingError(f"{label} label-window purge gap violated")


def _insufficient_evidence(cal: EG.GovernedEvaluationManifest,
                           val: EG.GovernedEvaluationManifest,
                           protocol: CalibrationProtocol,
                           reason: str,
                           validation_count: int) -> CalibrationFitResult:
    scope = cal.scope
    evidence = CalibrationEvidence(
        status="INSUFFICIENT_EVIDENCE",
        calibration_domain=scope.calibration_domain,
        probability_type=scope.probability_type.upper(),
        method="sigmoid",
        method_version=protocol.method_version,
        calibration_version=W4_CALIBRATION_FITTING_SCHEMA_VERSION,
        model_id=scope.model,
        model_version=scope.model_version,
        dataset_version=f"{cal.dataset_id}:{val.dataset_id}",
        protocol_version=protocol.protocol_id,
        target_family=scope.target_family,
        instrument=scope.instrument,
        horizon=scope.horizon,
        scope="SINGLE_INSTRUMENT",
        fit_window_start=cal.window_start.astimezone(timezone.utc).isoformat(),
        fit_window_end=cal.window_end.astimezone(timezone.utc).isoformat(),
        evaluation_window_start=val.window_start.astimezone(timezone.utc).isoformat(),
        evaluation_window_end=val.window_end.astimezone(timezone.utc).isoformat(),
        fit_partition_role="CALIBRATION",
        sample_count=validation_count,
        effective_sample_count=validation_count,
        minimum_required_sample=protocol.min_validation_samples,
        sample_sufficiency_status="INSUFFICIENT",
        evaluated_at=val.evaluation_as_of.astimezone(timezone.utc).isoformat(),
        source="W4.1_PREDICTION_AUDIT_W3.1_GOVERNED",
        notes=reason,
    )
    return CalibrationFitResult(
        status="INSUFFICIENT_EVIDENCE",
        reason=reason,
        artifact_id="",
        protocol=protocol,
        calibration_dataset_id=cal.dataset_id,
        validation_dataset_id=val.dataset_id,
        scope=_scope_payload(scope),
        evidence=evidence,
    )


def fit_and_validate(
    db: PA.PredictionAuditDB,
    calibration_manifest: EG.GovernedEvaluationManifest,
    validation_manifest: EG.GovernedEvaluationManifest,
    *,
    protocol: CalibrationProtocol | None = None,
    store: "CalibrationArtifactStore | None" = None,
) -> CalibrationFitResult:
    protocol = protocol or load_protocol()
    _validate_manifest_pair(calibration_manifest, validation_manifest, protocol)
    _require_purge_gap(db, calibration_manifest, validation_manifest, "calibration/validation")

    fit_pairs, fit_dist = _member_pairs(db, calibration_manifest)
    val_pairs, val_dist = _member_pairs(db, validation_manifest)
    if fit_dist != val_dist:
        raise CalibrationFittingError("calibration/validation distribution mismatch")

    fit_pos, fit_neg = _class_counts(fit_pairs)
    val_pos, val_neg = _class_counts(val_pairs)
    if (
        len(fit_pairs) < protocol.min_fit_samples
        or len(val_pairs) < protocol.min_validation_samples
        or min(fit_pos, fit_neg, val_pos, val_neg) < protocol.min_class_count
    ):
        return _insufficient_evidence(
            calibration_manifest,
            validation_manifest,
            protocol,
            "SAMPLE_OR_CLASS_COUNT_BELOW_PRE_REGISTERED_MINIMUM",
            len(val_pairs),
        )

    model = fit_sigmoid(fit_pairs, protocol)
    if not model.converged:
        raise CalibrationFittingError("sigmoid optimizer did not converge")
    validation_max_label_end, _ = _member_time_bounds(db, validation_manifest)

    calibrated_pairs = [(calibrate_probability(model, p), y) for p, y in val_pairs]
    raw_metrics = _metrics(val_pairs, protocol)
    cal_metrics = _metrics(calibrated_pairs, protocol)
    delta_ci = _paired_delta_ci(val_pairs, calibrated_pairs, protocol)
    acceptance = _acceptance(raw_metrics, cal_metrics, model, protocol, delta_ci)
    accepted = bool(acceptance["accepted"])
    # VALIDATION can qualify a frozen candidate, but public CALIBRATED evidence
    # requires a separate one-use FINAL_OOS confirmation.
    status = "EVALUATED_UNCALIBRATED"
    scope = calibration_manifest.scope
    identity_payload = {
        "schema_version": W4_CALIBRATION_FITTING_SCHEMA_VERSION,
        "protocol": protocol.model_dump(),
        "scope": _scope_payload(scope),
        "calibration_dataset_id": calibration_manifest.dataset_id,
        "validation_dataset_id": validation_manifest.dataset_id,
        "distribution_id": fit_dist[0],
        "distribution_version": fit_dist[1],
        "model": model.model_dump(),
        "raw_validation_metrics": raw_metrics,
        "calibrated_validation_metrics": cal_metrics,
        "acceptance": acceptance,
    }
    artifact_id = "w4_cal_" + sha256(
        PA.canonical_json(identity_payload).encode("utf-8")
    ).hexdigest()[:16]

    evidence = CalibrationEvidence(
        status="EVALUATED_UNCALIBRATED",
        calibration_domain=scope.calibration_domain,
        probability_type=scope.probability_type.upper(),
        method="sigmoid",
        method_version=protocol.method_version,
        calibration_version=artifact_id,
        model_id=scope.model,
        model_version=scope.model_version,
        distribution_id=fit_dist[0],
        distribution_version=fit_dist[1],
        dataset_version=f"{calibration_manifest.dataset_id}:{validation_manifest.dataset_id}",
        protocol_version=protocol.protocol_id,
        target_family=scope.target_family,
        instrument=scope.instrument,
        horizon=scope.horizon,
        scope="SINGLE_INSTRUMENT",
        fit_window=f"{calibration_manifest.window_start.isoformat()}/{calibration_manifest.window_end.isoformat()}",
        evaluation_window=f"{validation_manifest.window_start.isoformat()}/{validation_manifest.window_end.isoformat()}",
        fit_window_start=calibration_manifest.window_start.astimezone(timezone.utc).isoformat(),
        fit_window_end=calibration_manifest.window_end.astimezone(timezone.utc).isoformat(),
        evaluation_window_start=validation_manifest.window_start.astimezone(timezone.utc).isoformat(),
        evaluation_window_end=validation_manifest.window_end.astimezone(timezone.utc).isoformat(),
        fit_partition_role="CALIBRATION",
        fold_id=f"{calibration_manifest.dataset_id}:{validation_manifest.dataset_id}",
        train_end=calibration_manifest.window_end.astimezone(timezone.utc).isoformat(),
        sample_count=len(val_pairs),
        effective_sample_count=len(val_pairs),
        minimum_required_sample=protocol.min_validation_samples,
        sample_sufficiency_status="SUFFICIENT",
        evaluated_at=validation_manifest.evaluation_as_of.astimezone(timezone.utc).isoformat(),
        source="W4.1_PREDICTION_AUDIT_W3.1_GOVERNED",
        metrics={
            "raw_validation": raw_metrics,
            "calibrated_validation": cal_metrics,
            "acceptance": acceptance,
            "fit_sample_count": len(fit_pairs),
            "fit_class_counts": {"positive": fit_pos, "negative": fit_neg},
            "validation_class_counts": {"positive": val_pos, "negative": val_neg},
            "validation_max_label_window_end": validation_max_label_end.astimezone(timezone.utc).isoformat(),
            "final_oos_consumed": False,
        },
        notes="VALIDATION_ONLY_ACCEPTANCE; FINAL_OOS_NOT_CONSUMED",
    )
    result = CalibrationFitResult(
        status=status,
        reason=("VALIDATION_CANDIDATE_ACCEPTED_FINAL_OOS_REQUIRED"
                if accepted else "VALIDATION_ACCEPTANCE_NOT_MET"),
        artifact_id=artifact_id,
        protocol=protocol,
        calibration_dataset_id=calibration_manifest.dataset_id,
        validation_dataset_id=validation_manifest.dataset_id,
        scope=_scope_payload(scope),
        model=model,
        raw_validation_metrics=raw_metrics,
        calibrated_validation_metrics=cal_metrics,
        acceptance=acceptance,
        evidence=evidence,
    )
    if store is not None:
        store.write(result)
    return result


def _validate_final_oos(
    candidate: CalibrationFitResult,
    final_manifest: EG.GovernedEvaluationManifest,
    protocol: CalibrationProtocol,
) -> None:
    if candidate.model is None or candidate.evidence is None:
        raise CalibrationFittingError("candidate has no fitted model/evidence")
    if not bool(candidate.acceptance.get("accepted")):
        raise CalibrationFittingError("validation candidate was not accepted")
    if final_manifest.scope.partition_role != "FINAL_OOS":
        raise CalibrationFittingError("final manifest must be FINAL_OOS")
    if _scope_payload(final_manifest.scope) != candidate.scope:
        raise CalibrationFittingError("candidate/final OOS scope mismatch")
    if final_manifest.scope.sample_origin != protocol.sample_origin:
        raise CalibrationFittingError("final OOS sample origin mismatch")
    if final_manifest.is_blocked() or final_manifest.base_blocked_rejections():
        raise CalibrationFittingError("final OOS governance blocked manifest")
    if protocol.require_zero_overlap_pairs and int(
        final_manifest.coverage.get("overlapping_horizon_pair_count") or 0
    ) != 0:
        raise CalibrationFittingError("final OOS horizon overlap requires purge")
    span_days = (final_manifest.window_end - final_manifest.window_start).total_seconds() / 86400.0
    if span_days < protocol.min_calendar_span_days:
        raise CalibrationFittingError("final OOS calendar span below pre-registered minimum")
    validation_end = candidate.evidence.evaluation_window_end
    final_start = final_manifest.window_start.astimezone(timezone.utc).isoformat()
    if validation_end and final_start < validation_end:
        raise CalibrationFittingError("FINAL_OOS overlaps validation window")


def finalize_with_final_oos(
    db: PA.PredictionAuditDB,
    candidate: CalibrationFitResult,
    final_manifest: EG.GovernedEvaluationManifest,
    *,
    store: "CalibrationArtifactStore",
) -> CalibrationFitResult:
    """Consume one untouched FINAL_OOS manifest exactly once.

    The fitted parameters are frozen in candidate. FINAL_OOS only confirms or
    rejects that frozen candidate; it never refits or selects parameters.
    """
    protocol = candidate.protocol
    _validate_final_oos(candidate, final_manifest, protocol)
    # Reconstruct the validation manifest is unnecessary: the frozen candidate records its
    # validation window, while member-level FINAL_OOS timing is checked below against that cutoff.
    final_pairs, final_dist = _member_pairs(db, final_manifest)
    _, final_min_origin = _member_time_bounds(db, final_manifest)
    validation_label_end_text = str(
        candidate.evidence.metrics.get("validation_max_label_window_end") or ""
    )
    if not validation_label_end_text:
        raise CalibrationFittingError("candidate missing validation label-window cutoff")
    validation_label_end = datetime.fromisoformat(validation_label_end_text)
    if validation_label_end > final_min_origin:
        raise CalibrationFittingError("validation/final OOS label-window purge gap violated")
    expected_dist = (candidate.evidence.distribution_id, candidate.evidence.distribution_version)
    if final_dist != expected_dist:
        raise CalibrationFittingError("candidate/final OOS distribution mismatch")
    pos, neg = _class_counts(final_pairs)
    if len(final_pairs) < protocol.min_final_oos_samples or min(pos, neg) < protocol.min_class_count:
        raise CalibrationFittingError("FINAL_OOS_SAMPLE_OR_CLASS_COUNT_BELOW_PRE_REGISTERED_MINIMUM")

    calibrated_pairs = [(calibrate_probability(candidate.model, p), y) for p, y in final_pairs]
    raw_metrics = _metrics(final_pairs, protocol)
    cal_metrics = _metrics(calibrated_pairs, protocol)
    delta_ci = _paired_delta_ci(final_pairs, calibrated_pairs, protocol)
    acceptance = _acceptance(raw_metrics, cal_metrics, candidate.model, protocol, delta_ci)
    accepted = bool(acceptance["accepted"])

    payload = {
        "schema_version": W4_CALIBRATION_FITTING_SCHEMA_VERSION,
        "candidate_artifact_id": candidate.artifact_id,
        "final_oos_dataset_id": final_manifest.dataset_id,
        "scope": candidate.scope,
        "distribution_id": final_dist[0],
        "distribution_version": final_dist[1],
        "raw_final_oos_metrics": raw_metrics,
        "calibrated_final_oos_metrics": cal_metrics,
        "acceptance": acceptance,
    }
    artifact_id = "w4_final_" + sha256(
        PA.canonical_json(payload).encode("utf-8")
    ).hexdigest()[:16]
    store.claim_final_oos(
        final_manifest.dataset_id,
        candidate_artifact_id=candidate.artifact_id,
        final_artifact_id=artifact_id,
    )

    base = candidate.evidence
    status = "CALIBRATED" if accepted else "EVALUATED_UNCALIBRATED"
    evidence = CalibrationEvidence(
        status=status,
        calibration_domain=base.calibration_domain,
        probability_type=base.probability_type,
        method=base.method,
        method_version=base.method_version,
        calibration_version=artifact_id,
        model_id=base.model_id,
        model_version=base.model_version,
        distribution_id=base.distribution_id,
        distribution_version=base.distribution_version,
        dataset_version=f"{base.dataset_version}:{final_manifest.dataset_id}",
        protocol_version=base.protocol_version,
        target_family=base.target_family,
        instrument=base.instrument,
        horizon=base.horizon,
        scope=base.scope,
        fit_window=base.fit_window,
        evaluation_window=base.evaluation_window,
        fit_window_start=base.fit_window_start,
        fit_window_end=base.fit_window_end,
        evaluation_window_start=base.evaluation_window_start,
        evaluation_window_end=base.evaluation_window_end,
        fit_partition_role=base.fit_partition_role,
        fold_id=f"{base.fold_id}:{final_manifest.dataset_id}",
        train_end=base.train_end,
        sample_count=len(final_pairs),
        effective_sample_count=len(final_pairs),
        minimum_required_sample=protocol.min_final_oos_samples,
        sample_sufficiency_status="SUFFICIENT",
        evaluated_at=final_manifest.evaluation_as_of.astimezone(timezone.utc).isoformat(),
        source="W4.1_FINAL_OOS_ONE_USE",
        metrics={
            "validation_candidate_artifact_id": candidate.artifact_id,
            "validation_acceptance": candidate.acceptance,
            "raw_final_oos": raw_metrics,
            "calibrated_final_oos": cal_metrics,
            "final_oos_acceptance": acceptance,
            "final_oos_dataset_id": final_manifest.dataset_id,
            "final_oos_window_start": final_manifest.window_start.astimezone(timezone.utc).isoformat(),
            "final_oos_window_end": final_manifest.window_end.astimezone(timezone.utc).isoformat(),
            "final_oos_class_counts": {"positive": pos, "negative": neg},
            "final_oos_consumed": True,
        },
        notes="FROZEN_CANDIDATE; FINAL_OOS_CONSUMED_ONCE; NO_REFIT",
    )
    result = CalibrationFitResult(
        status=status,
        reason=("FINAL_OOS_ACCEPTED_PRE_REGISTERED_RULE"
                if accepted else "FINAL_OOS_ACCEPTANCE_NOT_MET"),
        artifact_id=artifact_id,
        protocol=protocol,
        calibration_dataset_id=candidate.calibration_dataset_id,
        validation_dataset_id=candidate.validation_dataset_id,
        final_oos_dataset_id=final_manifest.dataset_id,
        scope=candidate.scope,
        model=candidate.model,
        raw_validation_metrics=raw_metrics,
        calibrated_validation_metrics=cal_metrics,
        acceptance=acceptance,
        evidence=evidence,
    )
    store.write(result)
    return result


class CalibrationArtifactStore:
    """Content-addressed local W4 artifact store."""

    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root) if root is not None else data_root() / "audit" / "calibration_fitting"

    def path_for(self, artifact_id: str) -> Path:
        if not artifact_id.startswith(("w4_cal_", "w4_final_")):
            raise CalibrationFittingError("invalid calibration artifact id")
        return self.root / f"{artifact_id}.json"

    def claim_final_oos(self, dataset_id: str, *, candidate_artifact_id: str,
                        final_artifact_id: str) -> Path:
        if not dataset_id.startswith("w3_ds_"):
            raise CalibrationFittingError("invalid final OOS dataset id")
        directory = self.root / "final_oos_consumed"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{dataset_id}.json"
        payload = PA.canonical_json({
            "schema_version": W4_CALIBRATION_FITTING_SCHEMA_VERSION,
            "dataset_id": dataset_id,
            "candidate_artifact_id": candidate_artifact_id,
            "final_artifact_id": final_artifact_id,
        })
        try:
            with path.open("x", encoding="utf-8") as fh:
                fh.write(payload)
        except FileExistsError as exc:
            raise CalibrationFittingError("FINAL_OOS_ALREADY_CONSUMED") from exc
        return path

    def write(self, result: CalibrationFitResult) -> Path:
        if not result.artifact_id:
            raise CalibrationFittingError("cannot persist artifact without artifact_id")
        path = self.path_for(result.artifact_id)
        payload = result.model_dump()
        text = PA.canonical_json(payload)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            if path.read_text(encoding="utf-8") != text:
                raise CalibrationFittingError("calibration artifact id collision")
            return path
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
        return path

    def read_payload(self, artifact_id: str) -> dict[str, Any]:
        return json.loads(self.path_for(artifact_id).read_text(encoding="utf-8"))


def schema_version() -> str:
    return W4_CALIBRATION_FITTING_SCHEMA_VERSION
