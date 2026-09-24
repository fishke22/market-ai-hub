"""W3.1 — outcome maturity / evaluation-as-of / homogeneous-scope governance.

This module is an additive gate in front of the closed V2-I 2I.1 metric engine.
It does not fit calibration models and does not create probability evidence.

Only V2-H audit records are consumed.  A sample is usable only when:
- prediction sealed a label window at forecast time;
- the full horizon is mature by evaluation_as_of;
- the bound outcome was available after label-window end but no later than evaluation_as_of;
- target/model/version/event/label/sample-origin scope is exact and homogeneous;
- duplicate logical samples and superseded selections are rejected.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from market_ai_hub.research.v2 import calibration_evaluation as CE
from market_ai_hub.research.v2.prediction_audit import (
    PREDICTION_SAMPLE_ORIGINS,
    PredictionAuditDB,
    canonical_json,
)

W3_EVALUATION_GOVERNANCE_SCHEMA_VERSION = "W3.1"

GOVERNANCE_BLOCKING_REASONS = frozenset({
    "OUTCOME_BEFORE_HORIZON_END",
    "OUTCOME_SCOPE_MISMATCH",
    "DUPLICATE_LOGICAL_SAMPLE",
    "MIXED_OR_WRONG_SCOPE",
    "SUPERSEDED_SAMPLE_SELECTED",
})
GOVERNANCE_NON_BLOCKING_REASONS = frozenset({
    "MATURITY_UNKNOWN",
    "NOT_MATURE_AT_EVALUATION_AS_OF",
    "OUTCOME_NOT_AVAILABLE_AT_EVALUATION_AS_OF",
    "UNKNOWN_SAMPLE_ORIGIN",
    "INACTIVE_PREDICTION",
    "MISSING_OUTCOME",
})


class EvaluationGovernanceError(ValueError):
    """Typed W3 governance contract error."""


def _aware(name: str, dt: datetime | None) -> datetime:
    if dt is None:
        raise EvaluationGovernanceError(f"{name} is required")
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise EvaluationGovernanceError(f"{name} must be timezone-aware")
    return dt.astimezone(timezone.utc)


def _hash(namespace: str, payload: dict) -> str:
    return sha256(f"{namespace}|{canonical_json(payload)}".encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class EvaluationScope:
    target_family: str
    instrument: str
    horizon: str
    model: str
    model_version: str
    artifact_type: str
    calibration_domain: str
    probability_type: str
    event_definition_id: str
    label_type: str
    sample_origin: str
    partition_role: str

    def __post_init__(self) -> None:
        required = {
            "target_family": self.target_family,
            "instrument": self.instrument,
            "horizon": self.horizon,
            "model": self.model,
            "model_version": self.model_version,
            "artifact_type": self.artifact_type,
            "label_type": self.label_type,
            "sample_origin": self.sample_origin,
            "partition_role": self.partition_role,
        }
        missing = [k for k, v in required.items() if not str(v).strip()]
        if missing:
            raise EvaluationGovernanceError("scope fields required: " + ",".join(missing))
        if self.sample_origin not in PREDICTION_SAMPLE_ORIGINS or self.sample_origin == "UNKNOWN":
            raise EvaluationGovernanceError(
                f"governed scope requires explicit sample_origin, got {self.sample_origin!r}"
            )
        if self.partition_role not in CE.PARTITION_ROLES:
            raise EvaluationGovernanceError(f"unknown partition_role: {self.partition_role!r}")
        if self.artifact_type == "EVENT_PROBABILITY":
            prob_required = {
                "calibration_domain": self.calibration_domain,
                "probability_type": self.probability_type,
                "event_definition_id": self.event_definition_id,
            }
            missing_prob = [k for k, v in prob_required.items() if not str(v).strip()]
            if missing_prob:
                raise EvaluationGovernanceError(
                    "probability scope fields required: " + ",".join(missing_prob)
                )

    @property
    def scope_id(self) -> str:
        return "w3_scope_" + _hash("evaluation_scope", asdict(self))

    def model_dump(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class GovernanceRejection:
    prediction_id: str = ""
    forecast_artifact_id: str = ""
    outcome_id: str = ""
    reason: str = ""
    detail: str = ""

    def model_dump(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class GovernedEvaluationManifest:
    scope: EvaluationScope
    evaluation_as_of: datetime
    window_start: datetime
    window_end: datetime
    members: list[CE.EvaluationMember]
    rejected: list[GovernanceRejection] = field(default_factory=list)
    base_rejected: list[CE.EvaluationRejection] = field(default_factory=list)
    coverage: dict[str, Any] = field(default_factory=dict)
    schema_version: str = W3_EVALUATION_GOVERNANCE_SCHEMA_VERSION
    dataset_id: str = ""

    def __post_init__(self) -> None:
        _aware("evaluation_as_of", self.evaluation_as_of)
        _aware("window_start", self.window_start)
        _aware("window_end", self.window_end)
        if self.window_end < self.window_start:
            raise EvaluationGovernanceError("window_end < window_start")
        object.__setattr__(
            self,
            "members",
            sorted(self.members, key=lambda m: (m.prediction_id, m.forecast_artifact_id, m.outcome_id)),
        )
        object.__setattr__(
            self,
            "rejected",
            sorted(
                self.rejected,
                key=lambda r: (r.prediction_id, r.forecast_artifact_id, r.outcome_id, r.reason),
            ),
        )

    def identity_payload(self) -> dict:
        d = asdict(self)
        d.pop("dataset_id", None)
        return d

    def blocked_rejections(self) -> list[GovernanceRejection]:
        return [r for r in self.rejected if r.reason in GOVERNANCE_BLOCKING_REASONS]

    def base_blocked_rejections(self) -> list[CE.EvaluationRejection]:
        return [r for r in self.base_rejected if r.reason in CE.BLOCKING_PAIRING_REJECTIONS]

    def is_blocked(self) -> bool:
        return bool(self.blocked_rejections() or self.base_blocked_rejections())

    def model_dump(self) -> dict:
        return asdict(self)


def _logical_sample_key(pred: Any, art: Any, scope: EvaluationScope) -> tuple:
    return (
        scope.scope_id,
        pred.forecast_origin,
        pred.label_window_id,
        art.label_type,
    )


def _expected_label_dates(predictions: list[Any]) -> tuple[list[str] | None, str]:
    """Return expected daily label-window ids only when calendar semantics are knowable."""
    if not predictions:
        return [], "EMPTY"
    ids = sorted({str(p.label_window_id) for p in predictions if str(p.label_window_id)})
    if not ids or any(len(x) != 10 or x[4] != "-" or x[7] != "-" for x in ids):
        return None, "LABEL_WINDOW_ID_NOT_DATE"
    calendar_ids = {str(p.calendar_id) for p in predictions}
    if len(calendar_ids) != 1:
        return None, "MIXED_CALENDAR"
    cal = next(iter(calendar_ids))
    start, end = ids[0], ids[-1]
    try:
        import pandas as pd
        from market_ai_hub.services.calendar import is_ose_derivatives_session, is_session
        days = [d.strftime("%Y-%m-%d") for d in pd.date_range(start, end, freq="D")]
        if cal in ("OSE_DERIVATIVES", "OSE/JPX_DERIVATIVES"):
            expected = [d for d in days if is_ose_derivatives_session(d)]
        elif cal in ("XTAI", "TAIFEX", "TAIFEX_DERIVATIVES"):
            expected = [d for d in days if is_session("^TWII", d)]
        elif cal in ("XTKS", "TSE"):
            expected = [d for d in days if is_session("^N225", d)]
        else:
            return None, "CALENDAR_NOT_SUPPORTED"
        return expected, "CALENDAR_DERIVED"
    except Exception:
        return None, "CALENDAR_UNAVAILABLE"


def _coverage(predictions: list[Any], members: list[CE.EvaluationMember],
              rejections: list[GovernanceRejection],
              base_rejected: list[CE.EvaluationRejection]) -> dict[str, Any]:
    expected, expected_status = _expected_label_dates(predictions)
    observed = sorted({str(p.label_window_id) for p in predictions if str(p.label_window_id)})
    missing_days = None if expected is None else sorted(set(expected) - set(observed))
    intervals = sorted(
        [
            (_aware("label_window_start", p.label_window_start),
             _aware("label_window_end", p.label_window_end),
             p.prediction_id)
            for p in predictions
            if p.label_window_start is not None and p.label_window_end is not None
        ],
        key=lambda x: (x[0], x[1], x[2]),
    )
    overlap_pairs = 0
    for i in range(len(intervals)):
        for j in range(i + 1, len(intervals)):
            if intervals[j][0] < intervals[i][1] and intervals[i][0] < intervals[j][1]:
                overlap_pairs += 1
    reasons: dict[str, int] = {}
    for r in rejections:
        reasons[r.reason] = reasons.get(r.reason, 0) + 1
    for r in base_rejected:
        reasons[r.reason] = reasons.get(r.reason, 0) + 1
    return {
        "candidate_prediction_count": len(predictions),
        "valid_sample_count": len(members),
        "missing_outcome_count": reasons.get("MISSING_OUTCOME", 0),
        "event_count": len({p.label_window_id for p in predictions if p.label_window_id}),
        "observed_label_window_ids": observed,
        "expected_label_window_status": expected_status,
        "expected_label_window_count": None if expected is None else len(expected),
        "missing_days": missing_days,
        "missing_day_count": None if missing_days is None else len(missing_days),
        "overlapping_horizon_pair_count": overlap_pairs,
        "rejection_counts": dict(sorted(reasons.items())),
    }


def build_governed_evaluation_dataset(
    db: PredictionAuditDB,
    *,
    prediction_ids: list[str],
    evaluation_as_of: datetime,
    target_family: str,
    instrument: str,
    horizon: str,
    model: str,
    model_version: str,
    artifact_type: str,
    partition_role: str,
    window_start: datetime,
    window_end: datetime,
    label_type: str,
    sample_origin: str,
    calibration_domain: str = "",
    probability_type: str = "",
    event_definition_id: str = "",
) -> GovernedEvaluationManifest:
    """Build a W3-governed dataset from the existing 2I.1 pairing engine."""
    eval_cutoff = _aware("evaluation_as_of", evaluation_as_of)
    _aware("window_start", window_start)
    _aware("window_end", window_end)

    scope = EvaluationScope(
        target_family=target_family,
        instrument=instrument,
        horizon=horizon,
        model=model,
        model_version=model_version,
        artifact_type=artifact_type,
        calibration_domain=calibration_domain,
        probability_type=probability_type,
        event_definition_id=event_definition_id,
        label_type=label_type,
        sample_origin=sample_origin,
        partition_role=partition_role,
    )

    base = CE.build_evaluation_dataset(
        db,
        prediction_ids=prediction_ids,
        target_family=target_family,
        instrument=instrument,
        horizon=horizon,
        model=model,
        model_version=model_version,
        artifact_type=artifact_type,
        partition_role=partition_role,
        window_start=window_start,
        window_end=window_end,
        calibration_domain=calibration_domain,
        probability_type=probability_type,
        event_definition_id=event_definition_id,
    )

    selected_predictions: list[Any] = []
    pred_by_id: dict[str, Any] = {}
    for pid in sorted(set(prediction_ids)):
        pred = db.get_prediction(pid)
        if pred is not None:
            selected_predictions.append(pred)
            pred_by_id[pid] = pred

    superseded_ids = {p.supersedes_id for p in selected_predictions if p.supersedes_id}
    rejected: list[GovernanceRejection] = []
    eligible: list[CE.EvaluationMember] = []
    seen_keys: dict[tuple, CE.EvaluationMember] = {}

    for member in base.members:
        pred = pred_by_id.get(member.prediction_id)
        art = db.get_forecast_artifact(member.forecast_artifact_id)
        outs = [o for o in db.get_outcomes(member.prediction_id) if o.outcome_id == member.outcome_id]
        out = outs[0] if outs else None
        if pred is None or art is None or out is None:
            rejected.append(GovernanceRejection(
                member.prediction_id, member.forecast_artifact_id, member.outcome_id,
                "MIXED_OR_WRONG_SCOPE", "bound records unavailable during governance check",
            ))
            continue
        if pred.prediction_id in superseded_ids:
            rejected.append(GovernanceRejection(
                pred.prediction_id, art.forecast_artifact_id, out.outcome_id,
                "SUPERSEDED_SAMPLE_SELECTED", "a selected prediction supersedes this prediction",
            ))
            continue
        if pred.status != "PENDING":
            rejected.append(GovernanceRejection(
                pred.prediction_id, art.forecast_artifact_id, out.outcome_id,
                "INACTIVE_PREDICTION", pred.status,
            ))
            continue
        if pred.sample_origin == "UNKNOWN":
            rejected.append(GovernanceRejection(
                pred.prediction_id, art.forecast_artifact_id, out.outcome_id,
                "UNKNOWN_SAMPLE_ORIGIN", "prediction did not seal forward/retrospective provenance",
            ))
            continue
        if pred.sample_origin != sample_origin or art.label_type != label_type:
            rejected.append(GovernanceRejection(
                pred.prediction_id, art.forecast_artifact_id, out.outcome_id,
                "MIXED_OR_WRONG_SCOPE",
                f"sample_origin={pred.sample_origin!r}, label_type={art.label_type!r}",
            ))
            continue
        if not pred.label_window_id or pred.label_window_start is None or pred.label_window_end is None:
            rejected.append(GovernanceRejection(
                pred.prediction_id, art.forecast_artifact_id, out.outcome_id,
                "MATURITY_UNKNOWN", "prediction has no sealed label window",
            ))
            continue
        horizon_end = _aware("label_window_end", pred.label_window_end)
        if horizon_end > eval_cutoff:
            rejected.append(GovernanceRejection(
                pred.prediction_id, art.forecast_artifact_id, out.outcome_id,
                "NOT_MATURE_AT_EVALUATION_AS_OF",
                f"label_window_end={horizon_end.isoformat()} > evaluation_as_of={eval_cutoff.isoformat()}",
            ))
            continue
        out_available = _aware("outcome.available_at", out.available_at)
        if out_available < horizon_end:
            rejected.append(GovernanceRejection(
                pred.prediction_id, art.forecast_artifact_id, out.outcome_id,
                "OUTCOME_BEFORE_HORIZON_END",
                f"outcome.available_at={out_available.isoformat()} < label_window_end={horizon_end.isoformat()}",
            ))
            continue
        if out_available > eval_cutoff:
            rejected.append(GovernanceRejection(
                pred.prediction_id, art.forecast_artifact_id, out.outcome_id,
                "OUTCOME_NOT_AVAILABLE_AT_EVALUATION_AS_OF",
                f"outcome.available_at={out_available.isoformat()} > evaluation_as_of={eval_cutoff.isoformat()}",
            ))
            continue
        if out.target_period != pred.label_window_id:
            rejected.append(GovernanceRejection(
                pred.prediction_id, art.forecast_artifact_id, out.outcome_id,
                "OUTCOME_SCOPE_MISMATCH",
                f"target_period={out.target_period!r} != label_window_id={pred.label_window_id!r}",
            ))
            continue

        key = _logical_sample_key(pred, art, scope)
        if key in seen_keys:
            prior = seen_keys[key]
            rejected.extend([
                GovernanceRejection(
                    prior.prediction_id, prior.forecast_artifact_id, prior.outcome_id,
                    "DUPLICATE_LOGICAL_SAMPLE", str(key),
                ),
                GovernanceRejection(
                    member.prediction_id, member.forecast_artifact_id, member.outcome_id,
                    "DUPLICATE_LOGICAL_SAMPLE", str(key),
                ),
            ])
            eligible = [x for x in eligible if x != prior]
            continue
        seen_keys[key] = member
        eligible.append(member)

    cov = _coverage(selected_predictions, eligible, rejected, base.rejected)
    manifest = GovernedEvaluationManifest(
        scope=scope,
        evaluation_as_of=evaluation_as_of,
        window_start=window_start,
        window_end=window_end,
        members=eligible,
        rejected=rejected,
        base_rejected=base.rejected,
        coverage=cov,
    )
    return replace(
        manifest,
        dataset_id="w3_ds_" + _hash("governed_evaluation_dataset", manifest.identity_payload()),
    )


def evaluate_governed_manifest(db: PredictionAuditDB,
                               manifest: GovernedEvaluationManifest) -> CE.EvaluationResult:
    """Run the closed 2I.1 metrics only after W3 governance passes."""
    governance_blocking = manifest.blocked_rejections()
    if governance_blocking:
        reasons = sorted({r.reason for r in governance_blocking})
        return CE.EvaluationResult(
            status="BLOCKED",
            artifact_type=manifest.scope.artifact_type,
            dataset_id=manifest.dataset_id,
            partition_role=manifest.scope.partition_role,
            sample_count=0,
            reason="W3:" + ";".join(reasons),
        )

    base_blocking = manifest.base_blocked_rejections()
    if base_blocking:
        reasons = sorted({r.reason for r in base_blocking})
        return CE.EvaluationResult(
            status="BLOCKED",
            artifact_type=manifest.scope.artifact_type,
            dataset_id=manifest.dataset_id,
            partition_role=manifest.scope.partition_role,
            sample_count=0,
            reason="2I.1:" + ";".join(reasons),
        )

    filtered = CE.EvaluationDatasetManifest(
        members=manifest.members,
        target_family=manifest.scope.target_family,
        instrument=manifest.scope.instrument,
        horizon=manifest.scope.horizon,
        model=manifest.scope.model,
        model_version=manifest.scope.model_version,
        artifact_type=manifest.scope.artifact_type,
        partition_role=manifest.scope.partition_role,
        window_start=manifest.window_start,
        window_end=manifest.window_end,
        calibration_domain=manifest.scope.calibration_domain,
        probability_type=manifest.scope.probability_type,
        event_definition_id=manifest.scope.event_definition_id,
        label_types=[manifest.scope.label_type] if manifest.members else [],
        rejected=[],
    )
    filtered = replace(
        filtered,
        dataset_id=CE.evaluation_dataset_identity(filtered.identity_payload()),
    )
    result = CE.evaluate_manifest(db, filtered)
    return replace(result, dataset_id=manifest.dataset_id)


def governance_readiness(manifest: GovernedEvaluationManifest) -> dict[str, Any]:
    """Metadata-only readiness. Never claims calibration."""
    if manifest.is_blocked():
        state = "BLOCKED"
    elif not manifest.members:
        state = "INSUFFICIENT_EVIDENCE"
    else:
        state = "READY_FOR_EVALUATION"
    return {
        "governance_schema_version": W3_EVALUATION_GOVERNANCE_SCHEMA_VERSION,
        "dataset_id": manifest.dataset_id,
        "scope_id": manifest.scope.scope_id,
        "evaluation_as_of": manifest.evaluation_as_of.isoformat(),
        "state": state,
        "valid_sample_count": len(manifest.members),
        "coverage": manifest.coverage,
        "CALIBRATION_FITTING": "NOT_STARTED",
        "CALIBRATED": False,
    }
