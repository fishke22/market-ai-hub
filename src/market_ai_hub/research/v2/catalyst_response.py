"""V2-F — Catalyst Response Scaffold (hardened 2F.2, descriptive, non-causal).

RESEARCH ONLY. Point-in-time CatalystObservation + post-catalyst TargetResponseWindow +
deterministic realized-response descriptive assessment + pre-event expected-response baseline
residual + descriptive response-path metrics.

2F.2 hardening:
- baseline bound to response target identity/time-stream; baseline timestamps mandatory + ordered;
  baseline source/provenance mandatory; unknown-provenance baseline never publishes a verified residual
- MACRO_RELEASE release-time truth machine-enforced
- catalyst kind/semantics consistency; structural enums/measurement validated; futures UNKNOWN series blocked
- deterministic response_id (caller label cannot change semantic identity); full catalyst semantic fingerprint
- response-path collision/eligibility/state-stream/anchor rules with deterministic blocked-path identity

Invariants preserved: CATALYST ASSOCIATION != CAUSATION; RESPONSE != PREDICTION; RESIDUAL != ALPHA;
causal_status fixed NOT_ESTABLISHED; no beta/Granger/lag; POST_CATALYST only; DAILY target only;
prior-US close != LIVE; no Direction/Risk/CHASE/Extension mapping.

Schema: V2_CATALYST_RESPONSE_SCHEMA_VERSION = "2F.2".
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field as dfield, asdict
from datetime import datetime
from hashlib import sha256
from typing import Any

from market_ai_hub.research.v2.asof import (
    ensure_utc_aware, normalize_instrument, normalize_family,
    STALENESS_STATUS, CONTEXT_ROLE, AVAILABILITY_STATUS, REVISION_STATUS, QUALITY_STATUS,
)
from market_ai_hub.research.v2.state_machine import StateEvaluationContext

V2_CATALYST_RESPONSE_SCHEMA_VERSION = "2F.2"

CATALYST_KINDS = ("MARKET_MOVE", "MACRO_RELEASE", "POLICY_EVENT", "OBSERVED_EVENT", "SCHEDULE_ONLY")
MEASUREMENT_KINDS = ("RETURN", "LEVEL_CHANGE", "BPS_CHANGE", "SURPRISE", "EVENT_ONLY")
_NUMERIC_MEASUREMENTS = ("RETURN", "LEVEL_CHANGE", "BPS_CHANGE", "SURPRISE")
OBSERVATION_SEMANTICS = ("OBSERVED", "SCHEDULE_ONLY", "SCENARIO", "FORECAST", "ACTUAL_FUTURE")
ASSOCIATION_STATUSES = ("DESCRIPTIVE_AVAILABLE", "REFERENCE_CONTEXT_ONLY", "UNVERIFIED", "BLOCKED")
RESIDUAL_STATUSES = ("DESCRIPTIVE_RESPONSE_RESIDUAL", "NOT_AVAILABLE", "UNVERIFIED_BASELINE")
WINDOW_KINDS = ("POST_CATALYST",)
CATALYST_FREQUENCIES = ("DAILY", "IRREGULAR")

PATH_STATUSES = ("DESCRIPTIVE_AVAILABLE", "BLOCKED", "NOT_AVAILABLE")

PROVENANCE_STATUS = ("AUTHORITATIVE", "VERIFIED_INPUT", "UNKNOWN")
_TRUSTED = ("AUTHORITATIVE", "VERIFIED_INPUT")
ASOF_STATUSES = ("ASOF_VERIFIED", "TEMPORAL_UNVERIFIED", "LEGACY_TEMPORAL_UNVERIFIED")
ROLL_STATUSES = ("NONE", "ROLL_BOUNDARY", "UNKNOWN", "NOT_APPLICABLE")
SERIES_SEMANTICS = ("CONTINUOUS", "CONTRACT", "CASH", "INDEX", "UNKNOWN")

_ASOF_RANK = {"ASOF_VERIFIED": 2, "TEMPORAL_UNVERIFIED": 1, "LEGACY_TEMPORAL_UNVERIFIED": 0}

BLOCKED_CATALYST_NOT_OBSERVED = "BLOCKED_CATALYST_NOT_OBSERVED"
BLOCKED_NON_OBSERVED_CATALYST_SOURCE = "BLOCKED_NON_OBSERVED_CATALYST_SOURCE"
BLOCKED_CATALYST_UNAVAILABLE = "BLOCKED_CATALYST_UNAVAILABLE"
BLOCKED_CATALYST_ID_COLLISION = "BLOCKED_CATALYST_ID_COLLISION"
BLOCKED_RESPONSE_ID_COLLISION = "BLOCKED_RESPONSE_ID_COLLISION"
BLOCKED_PRE_CATALYST_WINDOW = "BLOCKED_PRE_CATALYST_WINDOW"
BLOCKED_FUTURE_EVIDENCE = "BLOCKED_FUTURE_EVIDENCE"
BLOCKED_TEMPORAL_EVIDENCE_PROVENANCE = "BLOCKED_TEMPORAL_EVIDENCE_PROVENANCE"
BLOCKED_IDENTITY_MISMATCH = "BLOCKED_IDENTITY_MISMATCH"
BLOCKED_ROLL_PROVENANCE = "BLOCKED_ROLL_PROVENANCE"
BLOCKED_SERIES_SEMANTICS_MISMATCH = "BLOCKED_SERIES_SEMANTICS_MISMATCH"
BLOCKED_UNSUPPORTED_CATALYST_FREQUENCY = "BLOCKED_UNSUPPORTED_CATALYST_FREQUENCY"
BLOCKED_BASELINE_TEMPORAL_LEAKAGE = "BLOCKED_BASELINE_TEMPORAL_LEAKAGE"
BLOCKED_BASELINE_TEMPORAL_PROVENANCE = "BLOCKED_BASELINE_TEMPORAL_PROVENANCE"
BLOCKED_BASELINE_SOURCE_PROVENANCE = "BLOCKED_BASELINE_SOURCE_PROVENANCE"
BLOCKED_BASELINE_IDENTITY_MISMATCH = "BLOCKED_BASELINE_IDENTITY_MISMATCH"
BLOCKED_SOURCE_PROVENANCE = "BLOCKED_SOURCE_PROVENANCE"
BLOCKED_CONTEXT_CONTRACT = "BLOCKED_CONTEXT_CONTRACT"
BLOCKED_RELEASE_TIME_PROVENANCE = "BLOCKED_RELEASE_TIME_PROVENANCE"
BLOCKED_STATE_STREAM_MISMATCH = "BLOCKED_STATE_STREAM_MISMATCH"
BLOCKED_RESPONSE_ANCHOR_MISMATCH = "BLOCKED_RESPONSE_ANCHOR_MISMATCH"
BLOCKED_INELIGIBLE_RESPONSE_ASSESSMENT = "BLOCKED_INELIGIBLE_RESPONSE_ASSESSMENT"
BLOCKED_PATH_HORIZON_ORDER = "BLOCKED_PATH_HORIZON_ORDER"
INVALID_INPUT = "INVALID_INPUT"


def _least_verified(asofs: list[str]) -> str:
    return min(asofs, key=lambda s: _ASOF_RANK[s]) if asofs else "LEGACY_TEMPORAL_UNVERIFIED"


def _canonical(xs: list[str]) -> list[str]:
    return sorted({x for x in xs if x})


def _finite(x: Any) -> bool:
    return isinstance(x, (int, float)) and math.isfinite(x)


def _positive(x: Any) -> bool:
    return _finite(x) and x > 0


def _is_futures(ctx: StateEvaluationContext) -> bool:
    return normalize_family(ctx.target_family) == "OSAKA_MICRO" and ctx.instrument_role == "DIRECT"


def _id_fp(parts: list[str]) -> str:
    return sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


def _require_nonempty(name: str, value: Any) -> None:
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError(f"{name} must be non-empty")


# ── CatalystObservation (§12) ──
@dataclass
class CatalystObservation:
    catalyst_id: str = ""
    catalyst_kind: str = "OBSERVED_EVENT"
    factor_name: str = ""
    measurement_kind: str = "EVENT_ONLY"
    magnitude: float | None = None
    unit: str = ""
    event_timestamp: datetime | None = None
    available_at: datetime | None = None
    release_timestamp: datetime | None = None
    provider: str = ""
    source_type: str = ""
    source_schema_version: str = ""
    source_version: str = ""
    source_snapshot_ids: list[str] = dfield(default_factory=list)
    frequency: str = "DAILY"
    calendar_id: str = ""
    availability_status: str = "AVAILABLE"
    quality_status: str = "UNKNOWN"
    staleness_status: str = "UNKNOWN"
    context_role: str = "LIVE"
    asof_status: str = "LEGACY_TEMPORAL_UNVERIFIED"
    provenance_status: str = "UNKNOWN"
    revision_status: str = "UNKNOWN"
    observation_semantics: str = "OBSERVED"

    def __post_init__(self):
        _require_nonempty("catalyst_id", self.catalyst_id)
        _require_nonempty("factor_name", self.factor_name)
        if self.catalyst_kind not in CATALYST_KINDS:
            raise ValueError(f"unknown catalyst_kind: {self.catalyst_kind!r}")
        if self.measurement_kind not in MEASUREMENT_KINDS:
            raise ValueError(f"unknown measurement_kind: {self.measurement_kind!r}")
        if self.observation_semantics not in OBSERVATION_SEMANTICS:
            raise ValueError(f"unknown observation_semantics: {self.observation_semantics!r}")
        if self.frequency not in CATALYST_FREQUENCIES:
            raise ValueError(f"unsupported catalyst frequency: {self.frequency!r}")
        if self.provenance_status not in PROVENANCE_STATUS:
            raise ValueError(f"unknown provenance_status: {self.provenance_status!r}")
        if self.asof_status not in ASOF_STATUSES:
            raise ValueError(f"unknown asof_status: {self.asof_status!r}")
        if self.availability_status not in AVAILABILITY_STATUS:
            raise ValueError(f"unknown availability_status: {self.availability_status!r}")
        if self.quality_status not in QUALITY_STATUS:
            raise ValueError(f"unknown quality_status: {self.quality_status!r}")
        if self.staleness_status not in STALENESS_STATUS:
            raise ValueError(f"unknown staleness_status: {self.staleness_status!r}")
        if self.context_role not in CONTEXT_ROLE:
            raise ValueError(f"unknown context_role: {self.context_role!r}")
        if self.revision_status not in REVISION_STATUS:
            raise ValueError(f"unknown revision_status: {self.revision_status!r}")
        # measurement semantics (§19)
        if self.measurement_kind in _NUMERIC_MEASUREMENTS:
            if self.magnitude is None or not _finite(self.magnitude):
                raise ValueError(f"{self.measurement_kind} requires finite magnitude")
            _require_nonempty("unit", self.unit)
        else:  # EVENT_ONLY
            self.magnitude = None
            self.unit = ""
        for name in ("event_timestamp", "available_at", "release_timestamp"):
            v = getattr(self, name)
            if v is not None:
                if v.tzinfo is None:
                    raise ValueError(f"{name} must be tz-aware")
                setattr(self, name, ensure_utc_aware(v))
        self.factor_name = normalize_family(self.factor_name)

    def model_dump(self) -> dict:
        return asdict(self)


# ── TargetResponseEndpoint (§20) ──
@dataclass
class TargetResponseEndpoint:
    instrument: str = ""
    target_family: str = ""
    instrument_role: str = "DIRECT"
    calendar_id: str = ""
    frequency: str = "DAILY"
    value: float | None = None
    event_timestamp: datetime | None = None
    available_at: datetime | None = None
    source_type: str = ""
    source_schema_version: str = ""
    source_version: str = ""
    source_snapshot_ids: list[str] = dfield(default_factory=list)
    asof_status: str = "LEGACY_TEMPORAL_UNVERIFIED"
    provenance_status: str = "UNKNOWN"
    series_semantics: str = "UNKNOWN"
    roll_status: str = "UNKNOWN"

    def __post_init__(self):
        if self.frequency != "DAILY":
            raise ValueError("2F.2 target response frequency must be DAILY")
        if self.value is None or not _positive(self.value):
            raise ValueError("endpoint value must be finite > 0")
        if self.provenance_status not in PROVENANCE_STATUS:
            raise ValueError(f"unknown provenance_status: {self.provenance_status!r}")
        if self.asof_status not in ASOF_STATUSES:
            raise ValueError(f"unknown asof_status: {self.asof_status!r}")
        if self.roll_status not in ROLL_STATUSES:
            raise ValueError(f"unknown roll_status: {self.roll_status!r}")
        if self.series_semantics not in SERIES_SEMANTICS:
            raise ValueError(f"unknown series_semantics: {self.series_semantics!r}")
        for name in ("event_timestamp", "available_at"):
            v = getattr(self, name)
            if v is None:
                raise ValueError(f"TargetResponseEndpoint.{name} must be non-null")
            if v.tzinfo is None:
                raise ValueError(f"{name} must be tz-aware")
            setattr(self, name, ensure_utc_aware(v))
        self.instrument = normalize_instrument(self.instrument)
        self.target_family = normalize_family(self.target_family)

    def model_dump(self) -> dict:
        return asdict(self)


# ── ExpectedResponseBaselineEvidence (§31) ──
@dataclass
class ExpectedResponseBaselineEvidence:
    baseline_id: str = ""
    target_family: str = ""
    instrument: str = ""
    instrument_role: str = "DIRECT"
    calendar_id: str = ""
    frequency: str = "DAILY"
    horizon: str = "1d"
    expected_response: float | None = None
    fit_window_end: datetime | None = None
    baseline_available_at: datetime | None = None
    source_type: str = ""
    source_schema_version: str = ""
    source_version: str = ""
    source_snapshot_ids: list[str] = dfield(default_factory=list)
    asof_status: str = "LEGACY_TEMPORAL_UNVERIFIED"
    provenance_status: str = "UNKNOWN"
    validation_status: str = "HYPOTHESIS_ONLY"

    def __post_init__(self):
        _require_nonempty("baseline_id", self.baseline_id)
        if self.expected_response is None or not _finite(self.expected_response):
            raise ValueError("expected_response must be finite")
        if self.asof_status not in ASOF_STATUSES:
            raise ValueError(f"unknown asof_status: {self.asof_status!r}")
        if self.provenance_status not in PROVENANCE_STATUS:
            raise ValueError(f"unknown provenance_status: {self.provenance_status!r}")
        if self.validation_status != "HYPOTHESIS_ONLY":
            raise ValueError("baseline validation_status is frozen to HYPOTHESIS_ONLY")
        for name in ("fit_window_end", "baseline_available_at"):
            v = getattr(self, name)
            if v is not None:
                if v.tzinfo is None:
                    raise ValueError(f"{name} must be tz-aware")
                setattr(self, name, ensure_utc_aware(v))
        self.instrument = normalize_instrument(self.instrument)
        self.target_family = normalize_family(self.target_family)

    def model_dump(self) -> dict:
        return asdict(self)


# ── CatalystResponseAssessment (§26) ──
@dataclass
class CatalystResponseAssessment:
    assessment_id: str = ""
    catalyst_id: str = ""
    catalyst_kind: str = ""
    factor_name: str = ""
    catalyst_context_role: str = ""
    catalyst_staleness_status: str = ""
    revision_status: str = ""
    instrument: str = ""
    target_family: str = ""
    instrument_role: str = "DIRECT"
    calendar_id: str = ""
    frequency: str = "DAILY"
    horizon: str = "1d"
    feature_cutoff_timestamp: datetime | None = None
    state_origin: datetime | None = None
    response_id: str = ""
    response_label: str = ""
    response_window_start: datetime | None = None
    response_window_end: datetime | None = None
    response_available_at: datetime | None = None
    response_return: float | None = None
    response_delay_seconds: float | None = None
    association_status: str = "UNVERIFIED"
    causal_status: str = "NOT_ESTABLISHED"
    expected_response: float | None = None
    response_residual: float | None = None
    residual_status: str = "NOT_AVAILABLE"
    context_source_snapshot_ids: list[str] = dfield(default_factory=list)
    catalyst_source_snapshot_ids: list[str] = dfield(default_factory=list)
    response_start_source_snapshot_ids: list[str] = dfield(default_factory=list)
    response_end_source_snapshot_ids: list[str] = dfield(default_factory=list)
    baseline_source_snapshot_ids: list[str] = dfield(default_factory=list)
    source_snapshot_ids: list[str] = dfield(default_factory=list)
    derived_asof_status: str = "LEGACY_TEMPORAL_UNVERIFIED"
    block_reason_codes: list[str] = dfield(default_factory=list)
    catalyst_fingerprint: str = ""
    response_start_fingerprint: str = ""
    response_end_fingerprint: str = ""
    baseline_fingerprint: str = ""
    schema_version: str = V2_CATALYST_RESPONSE_SCHEMA_VERSION
    policy_version: str = "2F.2"

    def model_dump(self) -> dict:
        return asdict(self)


# ── CatalystResponsePath (§36/§37) ──
@dataclass
class CatalystResponsePath:
    path_id: str = ""
    path_status: str = "NOT_AVAILABLE"
    block_reason_codes: list[str] = dfield(default_factory=list)
    assessment_ids: list[str] = dfield(default_factory=list)
    catalyst_id: str = ""
    catalyst_fingerprint: str = ""
    instrument: str = ""
    target_family: str = ""
    instrument_role: str = "DIRECT"
    calendar_id: str = ""
    frequency: str = "DAILY"
    horizon: str = "1d"
    response_returns_by_horizon: dict[str, float] = dfield(default_factory=dict)
    absolute_response_by_horizon: dict[str, float] = dfield(default_factory=dict)
    peak_absolute_response: float | None = None
    peak_response_point_id: str = ""
    terminal_absolute_response: float | None = None
    terminal_to_peak_abs_ratio: float | None = None
    time_to_peak_seconds: float | None = None
    source_snapshot_ids: list[str] = dfield(default_factory=list)
    derived_asof_status: str = "LEGACY_TEMPORAL_UNVERIFIED"
    schema_version: str = V2_CATALYST_RESPONSE_SCHEMA_VERSION

    def model_dump(self) -> dict:
        return asdict(self)


# ── validation ──
def _validate_catalyst(catalyst: CatalystObservation, ctx: StateEvaluationContext) -> list[str]:
    if catalyst.catalyst_kind == "SCHEDULE_ONLY" or catalyst.observation_semantics == "SCHEDULE_ONLY":
        return [BLOCKED_CATALYST_NOT_OBSERVED]
    if catalyst.observation_semantics in ("SCENARIO", "FORECAST", "ACTUAL_FUTURE"):
        return [BLOCKED_NON_OBSERVED_CATALYST_SOURCE]
    if catalyst.availability_status != "AVAILABLE":
        return [BLOCKED_CATALYST_UNAVAILABLE]
    if catalyst.context_role == "UNAVAILABLE" or catalyst.quality_status == "CRITICAL":
        return [BLOCKED_CATALYST_UNAVAILABLE]
    if catalyst.event_timestamp is None or catalyst.available_at is None:
        return [BLOCKED_TEMPORAL_EVIDENCE_PROVENANCE]
    if ensure_utc_aware(catalyst.event_timestamp) > ensure_utc_aware(catalyst.available_at):
        return [BLOCKED_TEMPORAL_EVIDENCE_PROVENANCE]
    cutoff = ctx.feature_cutoff_timestamp
    if cutoff is not None and ensure_utc_aware(catalyst.available_at) > ensure_utc_aware(cutoff):
        return [BLOCKED_FUTURE_EVIDENCE]
    # macro release time truth (§10/§11/§12)
    if catalyst.catalyst_kind == "MACRO_RELEASE":
        if catalyst.release_timestamp is None:
            return [BLOCKED_RELEASE_TIME_PROVENANCE]
        if ensure_utc_aware(catalyst.release_timestamp) > ensure_utc_aware(catalyst.available_at):
            return [BLOCKED_RELEASE_TIME_PROVENANCE]
    for name in ("source_type", "source_schema_version", "source_version", "provider"):
        if not getattr(catalyst, name) or not str(getattr(catalyst, name)).strip():
            return [BLOCKED_SOURCE_PROVENANCE]
    return []


def _validate_endpoint(ep: TargetResponseEndpoint, ctx: StateEvaluationContext) -> list[str]:
    for name in ("instrument", "target_family", "instrument_role", "calendar_id", "frequency"):
        if not getattr(ep, name) or not str(getattr(ep, name)).strip():
            return [BLOCKED_IDENTITY_MISMATCH]
    if (normalize_instrument(ep.instrument) != normalize_instrument(ctx.instrument)
            or normalize_family(ep.target_family) != normalize_family(ctx.target_family)
            or ep.instrument_role != ctx.instrument_role
            or ep.calendar_id != ctx.calendar_id
            or ep.frequency != ctx.frequency):
        return [BLOCKED_IDENTITY_MISMATCH]
    if ensure_utc_aware(ep.event_timestamp) > ensure_utc_aware(ep.available_at):
        return [BLOCKED_TEMPORAL_EVIDENCE_PROVENANCE]
    cutoff = ctx.feature_cutoff_timestamp
    if cutoff is not None and ensure_utc_aware(ep.available_at) > ensure_utc_aware(cutoff):
        return [BLOCKED_FUTURE_EVIDENCE]
    for name in ("source_type", "source_schema_version", "source_version"):
        if not getattr(ep, name) or not str(getattr(ep, name)).strip():
            return [BLOCKED_SOURCE_PROVENANCE]
    return []


def _validate_baseline(baseline: ExpectedResponseBaselineEvidence, ctx: StateEvaluationContext,
                       catalyst: CatalystObservation) -> list[str]:
    for name in ("instrument", "target_family", "instrument_role", "calendar_id", "frequency", "horizon"):
        if not getattr(baseline, name) or not str(getattr(baseline, name)).strip():
            return [BLOCKED_BASELINE_IDENTITY_MISMATCH]
    if (normalize_instrument(baseline.instrument) != normalize_instrument(ctx.instrument)
            or normalize_family(baseline.target_family) != normalize_family(ctx.target_family)
            or baseline.instrument_role != ctx.instrument_role
            or baseline.calendar_id != ctx.calendar_id
            or baseline.frequency != ctx.frequency
            or baseline.horizon != ctx.horizon):
        return [BLOCKED_BASELINE_IDENTITY_MISMATCH]
    if baseline.fit_window_end is None or baseline.baseline_available_at is None:
        return [BLOCKED_BASELINE_TEMPORAL_PROVENANCE]
    if ensure_utc_aware(baseline.fit_window_end) > ensure_utc_aware(baseline.baseline_available_at):
        return [BLOCKED_BASELINE_TEMPORAL_PROVENANCE]
    if ensure_utc_aware(baseline.baseline_available_at) > ensure_utc_aware(catalyst.available_at):
        return [BLOCKED_BASELINE_TEMPORAL_LEAKAGE]
    if ensure_utc_aware(baseline.fit_window_end) > ensure_utc_aware(catalyst.event_timestamp):
        return [BLOCKED_BASELINE_TEMPORAL_LEAKAGE]
    for name in ("source_type", "source_schema_version", "source_version"):
        if not getattr(baseline, name) or not str(getattr(baseline, name)).strip():
            return [BLOCKED_BASELINE_SOURCE_PROVENANCE]
    return []


# ── fingerprints ──
def _catalyst_fp(c: CatalystObservation) -> str:
    d = {
        "id": c.catalyst_id, "kind": c.catalyst_kind, "factor": c.factor_name,
        "meas": c.measurement_kind, "mag": str(c.magnitude), "unit": c.unit,
        "event": c.event_timestamp.isoformat() if c.event_timestamp else "",
        "avail": c.available_at.isoformat() if c.available_at else "",
        "rel": c.release_timestamp.isoformat() if c.release_timestamp else "",
        "provider": c.provider, "src": c.source_type, "schema": c.source_schema_version,
        "ver": c.source_version, "snaps": "|".join(_canonical(c.source_snapshot_ids)),
        "freq": c.frequency, "cal": c.calendar_id,
        "avail_status": c.availability_status, "quality": c.quality_status,
        "staleness": c.staleness_status, "role": c.context_role,
        "asof": c.asof_status, "prov": c.provenance_status, "rev": c.revision_status,
        "semantics": c.observation_semantics,
    }
    return _id_fp([f"{k}={v}" for k, v in sorted(d.items())])


def _endpoint_fp(ep: TargetResponseEndpoint) -> str:
    d = {
        "inst": normalize_instrument(ep.instrument), "fam": normalize_family(ep.target_family),
        "role": ep.instrument_role, "cal": ep.calendar_id, "freq": ep.frequency,
        "val": str(ep.value),
        "event": ep.event_timestamp.isoformat() if ep.event_timestamp else "",
        "avail": ep.available_at.isoformat() if ep.available_at else "",
        "src": ep.source_type, "schema": ep.source_schema_version, "ver": ep.source_version,
        "snaps": "|".join(_canonical(ep.source_snapshot_ids)),
        "asof": ep.asof_status, "prov": ep.provenance_status,
        "series": ep.series_semantics, "roll": ep.roll_status,
    }
    return _id_fp([f"{k}={v}" for k, v in sorted(d.items())])


def _baseline_fp(b: ExpectedResponseBaselineEvidence) -> str:
    d = {
        "id": b.baseline_id, "inst": normalize_instrument(b.instrument), "fam": normalize_family(b.target_family),
        "role": b.instrument_role, "cal": b.calendar_id, "freq": b.frequency, "hor": b.horizon,
        "exp": str(b.expected_response),
        "fit": b.fit_window_end.isoformat() if b.fit_window_end else "",
        "avail": b.baseline_available_at.isoformat() if b.baseline_available_at else "",
        "src": b.source_type, "schema": b.source_schema_version, "ver": b.source_version,
        "snaps": "|".join(_canonical(b.source_snapshot_ids)),
        "asof": b.asof_status, "prov": b.provenance_status, "val": b.validation_status,
    }
    return _id_fp([f"{k}={v}" for k, v in sorted(d.items())])


def _response_id(catalyst: CatalystObservation, ctx: StateEvaluationContext,
                 start: TargetResponseEndpoint, end: TargetResponseEndpoint) -> str:
    parts = [
        _catalyst_fp(catalyst),
        normalize_instrument(ctx.instrument), normalize_family(ctx.target_family),
        ctx.instrument_role, ctx.calendar_id, ctx.frequency, ctx.horizon,
        ctx.feature_cutoff_timestamp.isoformat() if ctx.feature_cutoff_timestamp else "",
        ctx.state_origin.isoformat() if ctx.state_origin else "",
        _endpoint_fp(start), _endpoint_fp(end),
        V2_CATALYST_RESPONSE_SCHEMA_VERSION,
    ]
    return "v2f_resp_" + _id_fp(parts)


def _assessment_identity(a: CatalystResponseAssessment) -> str:
    parts = [
        a.catalyst_fingerprint,
        normalize_instrument(a.instrument), normalize_family(a.target_family),
        a.instrument_role, a.calendar_id, a.frequency, a.horizon,
        a.feature_cutoff_timestamp.isoformat() if a.feature_cutoff_timestamp else "",
        a.state_origin.isoformat() if a.state_origin else "",
        a.response_id, a.response_start_fingerprint, a.response_end_fingerprint,
        a.baseline_fingerprint,
        a.response_window_start.isoformat() if a.response_window_start else "",
        a.response_window_end.isoformat() if a.response_window_end else "",
        str(a.response_return), str(a.response_delay_seconds),
        str(a.expected_response), str(a.response_residual), a.residual_status,
        a.association_status, a.causal_status, a.revision_status,
        "|".join(_canonical(a.source_snapshot_ids)),
        a.derived_asof_status,
        "|".join(_canonical(a.block_reason_codes)),
        V2_CATALYST_RESPONSE_SCHEMA_VERSION, a.policy_version,
    ]
    return _id_fp(parts)


# ── evaluation ──
def evaluate_catalyst_response(
    context: StateEvaluationContext,
    catalyst: CatalystObservation,
    start: TargetResponseEndpoint,
    end: TargetResponseEndpoint,
    baseline: ExpectedResponseBaselineEvidence | None = None,
    response_label: str = "",
) -> CatalystResponseAssessment:
    a = CatalystResponseAssessment(
        catalyst_id=catalyst.catalyst_id, catalyst_kind=catalyst.catalyst_kind,
        factor_name=catalyst.factor_name, catalyst_context_role=catalyst.context_role,
        catalyst_staleness_status=catalyst.staleness_status, revision_status=catalyst.revision_status,
        instrument=context.instrument, target_family=context.target_family,
        instrument_role=context.instrument_role, calendar_id=context.calendar_id,
        frequency=context.frequency, horizon=context.horizon,
        feature_cutoff_timestamp=context.feature_cutoff_timestamp, state_origin=context.state_origin,
        response_label=response_label,
        context_source_snapshot_ids=_canonical(context.source_snapshot_ids),
        catalyst_source_snapshot_ids=_canonical(catalyst.source_snapshot_ids),
        response_start_source_snapshot_ids=_canonical(start.source_snapshot_ids),
        response_end_source_snapshot_ids=_canonical(end.source_snapshot_ids),
        baseline_source_snapshot_ids=_canonical(baseline.source_snapshot_ids) if baseline else [],
    )
    a.catalyst_fingerprint = _catalyst_fp(catalyst)
    a.response_start_fingerprint = _endpoint_fp(start)
    a.response_end_fingerprint = _endpoint_fp(end)
    a.baseline_fingerprint = _baseline_fp(baseline) if baseline else ""
    a.source_snapshot_ids = _canonical(a.context_source_snapshot_ids + a.catalyst_source_snapshot_ids
                                       + a.response_start_source_snapshot_ids
                                       + a.response_end_source_snapshot_ids
                                       + a.baseline_source_snapshot_ids)
    a.derived_asof_status = _least_verified(
        [context.asof_status, catalyst.asof_status, start.asof_status, end.asof_status]
        + ([baseline.asof_status] if baseline else []))
    a.response_id = _response_id(catalyst, context, start, end)

    def block(reason):
        a.association_status = "BLOCKED"
        a.block_reason_codes = [reason]
        a.assessment_id = _assessment_identity(a)
        return a

    if context.validate_contract():
        return block(BLOCKED_CONTEXT_CONTRACT)

    cat_reasons = _validate_catalyst(catalyst, context)
    if cat_reasons:
        return block(cat_reasons[0])

    for ep in (start, end):
        for r in _validate_endpoint(ep, context):
            return block(r)

    # futures roll / series (§22)
    if _is_futures(context):
        if start.roll_status != "NONE" or end.roll_status != "NONE":
            return block(BLOCKED_ROLL_PROVENANCE)
        if start.series_semantics == "UNKNOWN" or end.series_semantics == "UNKNOWN":
            return block(BLOCKED_SERIES_SEMANTICS_MISMATCH)
    if start.series_semantics != end.series_semantics:
        return block(BLOCKED_SERIES_SEMANTICS_MISMATCH)

    cat_avail = ensure_utc_aware(catalyst.available_at)
    start_ev = ensure_utc_aware(start.event_timestamp)
    end_ev = ensure_utc_aware(end.event_timestamp)
    if start_ev < cat_avail:
        return block(BLOCKED_PRE_CATALYST_WINDOW)
    if not (start_ev < end_ev):
        return block(BLOCKED_TEMPORAL_EVIDENCE_PROVENANCE)

    if catalyst.provenance_status == "UNKNOWN" or start.provenance_status == "UNKNOWN" or end.provenance_status == "UNKNOWN":
        a.association_status = "UNVERIFIED"
        a.assessment_id = _assessment_identity(a)
        return a

    response_return = (end.value / start.value) - 1.0
    response_delay = (start_ev - cat_avail).total_seconds()
    response_available_at = max(cat_avail, ensure_utc_aware(start.available_at),
                                ensure_utc_aware(end.available_at))
    a.response_window_start = start_ev
    a.response_window_end = end_ev
    a.response_available_at = response_available_at
    a.response_return = response_return
    a.response_delay_seconds = response_delay
    a.association_status = ("REFERENCE_CONTEXT_ONLY" if catalyst.context_role == "PREVIOUS_SESSION_REFERENCE"
                            else "DESCRIPTIVE_AVAILABLE")

    if baseline is not None:
        bl_reasons = _validate_baseline(baseline, context, catalyst)
        if bl_reasons:
            return block(bl_reasons[0])
        if baseline.provenance_status == "UNKNOWN":
            a.residual_status = "UNVERIFIED_BASELINE"
            a.expected_response = None
            a.response_residual = None
        else:
            a.expected_response = baseline.expected_response
            a.response_residual = response_return - baseline.expected_response
            a.residual_status = "DESCRIPTIVE_RESPONSE_RESIDUAL"

    a.causal_status = "NOT_ESTABLISHED"
    a.assessment_id = _assessment_identity(a)
    return a


# ── response path ──
def _path_blocked(path: CatalystResponsePath, reason: str, assessment_ids: list[str]) -> CatalystResponsePath:
    path.path_status = "BLOCKED"
    path.block_reason_codes = [reason]
    path.assessment_ids = _canonical(assessment_ids)
    path.path_id = _path_identity(path)
    return path


def summarize_response_path(assessments: list[CatalystResponseAssessment]) -> CatalystResponsePath:
    if not assessments:
        return CatalystResponsePath()
    first = assessments[0]
    path = CatalystResponsePath(
        catalyst_id=first.catalyst_id, catalyst_fingerprint=first.catalyst_fingerprint,
        instrument=first.instrument, target_family=first.target_family,
        instrument_role=first.instrument_role, calendar_id=first.calendar_id,
        frequency=first.frequency, horizon=first.horizon,
    )
    ids = _canonical([a.assessment_id for a in assessments])

    # eligibility (§31)
    for a in assessments:
        if a.association_status not in ("DESCRIPTIVE_AVAILABLE", "REFERENCE_CONTEXT_ONLY"):
            return _path_blocked(path, BLOCKED_INELIGIBLE_RESPONSE_ASSESSMENT, ids)

    # same catalyst (id + fingerprint) (§29)
    for a in assessments:
        if a.catalyst_id != first.catalyst_id or a.catalyst_fingerprint != first.catalyst_fingerprint:
            return _path_blocked(path, BLOCKED_CATALYST_ID_COLLISION, ids)

    # same target identity + state stream (§35)
    for a in assessments:
        if (normalize_instrument(a.instrument) != normalize_instrument(first.instrument)
                or normalize_family(a.target_family) != normalize_family(first.target_family)
                or a.instrument_role != first.instrument_role
                or a.calendar_id != first.calendar_id
                or a.frequency != first.frequency
                or a.horizon != first.horizon):
            return _path_blocked(path, BLOCKED_IDENTITY_MISMATCH, ids)
        if (a.feature_cutoff_timestamp is None or first.feature_cutoff_timestamp is None
                or ensure_utc_aware(a.feature_cutoff_timestamp) != ensure_utc_aware(first.feature_cutoff_timestamp)
                or a.state_origin is None or first.state_origin is None
                or ensure_utc_aware(a.state_origin) != ensure_utc_aware(first.state_origin)):
            return _path_blocked(path, BLOCKED_STATE_STREAM_MISMATCH, ids)

    # same response anchor (§37)
    for a in assessments:
        if a.response_start_fingerprint != first.response_start_fingerprint:
            return _path_blocked(path, BLOCKED_RESPONSE_ANCHOR_MISMATCH, ids)

    # response_id collision (§28) — same id + different payload
    seen: dict[str, CatalystResponseAssessment] = {}
    for a in assessments:
        if a.response_id in seen:
            if asdict(seen[a.response_id]) != asdict(a):
                return _path_blocked(path, BLOCKED_RESPONSE_ID_COLLISION, ids)
            continue
        seen[a.response_id] = a

    sorted_assessments = sorted(seen.values(), key=lambda a: ensure_utc_aware(a.response_window_end))

    # strictly increasing end times (§38)
    prev_end = None
    for a in sorted_assessments:
        cur_end = ensure_utc_aware(a.response_window_end)
        if prev_end is not None and cur_end <= prev_end:
            return _path_blocked(path, BLOCKED_PATH_HORIZON_ORDER, ids)
        prev_end = cur_end

    for a in sorted_assessments:
        path.response_returns_by_horizon[a.response_id] = a.response_return
        path.absolute_response_by_horizon[a.response_id] = abs(a.response_return)

    abs_vals = list(path.absolute_response_by_horizon.values())
    peak = max(abs_vals)
    path.peak_absolute_response = peak
    peak_id = [k for k, v in path.absolute_response_by_horizon.items() if v == peak][0]
    path.peak_response_point_id = peak_id
    path.terminal_absolute_response = abs_vals[-1]
    if peak > 0:
        path.terminal_to_peak_abs_ratio = abs_vals[-1] / peak
    first_start = ensure_utc_aware(sorted_assessments[0].response_window_start)
    peak_end = ensure_utc_aware(seen[peak_id].response_window_end)
    path.time_to_peak_seconds = (peak_end - first_start).total_seconds()

    path.assessment_ids = _canonical([a.assessment_id for a in sorted_assessments])
    path.source_snapshot_ids = _canonical([sid for a in sorted_assessments for sid in a.source_snapshot_ids])
    path.derived_asof_status = _least_verified([a.derived_asof_status for a in sorted_assessments])
    path.path_status = "DESCRIPTIVE_AVAILABLE"
    path.path_id = _path_identity(path)
    return path


def _path_identity(p: CatalystResponsePath) -> str:
    parts = [
        p.path_status, p.catalyst_id, p.catalyst_fingerprint,
        normalize_instrument(p.instrument), normalize_family(p.target_family),
        p.instrument_role, p.calendar_id, p.frequency, p.horizon,
        "|".join(_canonical(p.assessment_ids)),
        "|".join(_canonical(p.block_reason_codes)),
        "|".join(f"{k}={v}" for k, v in sorted(p.response_returns_by_horizon.items())),
        str(p.peak_absolute_response), p.peak_response_point_id,
        str(p.terminal_absolute_response), str(p.terminal_to_peak_abs_ratio),
        str(p.time_to_peak_seconds),
        "|".join(_canonical(p.source_snapshot_ids)),
        p.derived_asof_status, V2_CATALYST_RESPONSE_SCHEMA_VERSION,
    ]
    return _id_fp(parts)
