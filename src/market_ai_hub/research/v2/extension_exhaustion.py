"""V2-E — Daily Extension / Exhaustion Research Engine (hardened 2E.3).

RESEARCH ONLY. Point-in-time DAILY extension evaluator (ATR-normalized move from previous close),
typed Exhaustion component evidence, and a multi-component Exhaustion Warning research evaluator.

2E.3 hardening:
- derived extension availability = max(current/previous/ATR availability); late ATR cannot backdate
- extension/exhaustion must share the SAME state stream (identity + cutoff + origin)
- warning earliest-establishment from the earliest K distinct families (late 3rd family / same-family
  duplicate do NOT delay the warning); required confirmation set is auditable + deterministic
- component timestamps canonical UTC; full role-preserved lineage + ASOF on ALL statuses
- trusted-negative and conflict component IDs preserved; semantic IDs include full evidence lineage

Invariants preserved: EXTENSION != EXHAUSTION; EXHAUSTION_WARNING != REVERSAL/BEARISH/CHASE_STOP.
Schema: V2_EXTENSION_EXHAUSTION_SCHEMA_VERSION = "2E.3".
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field as dfield, asdict
from datetime import datetime
from hashlib import sha256
from typing import Any

from market_ai_hub.research.v2.asof import normalize_instrument, normalize_family, ensure_utc_aware
from market_ai_hub.research.v2.state_machine import StateEvaluationContext, StateEvidence

V2_EXTENSION_EXHAUSTION_SCHEMA_VERSION = "2E.3"

# ── enums ──
EXTENSION_STATES = ("NORMAL", "EXTENDED", "EXTREME")
EXTENSION_SIDES = ("UP", "DOWN", "FLAT")
CANONICAL_REFERENCE = "PREVIOUS_CLOSE"
ATR_METHOD = "EXISTING_MARKET_AI_HUB_ATR_EWM"

ASSESSMENT_STATUSES = ("EVALUATED", "UNVERIFIED", "BLOCKED")
EXHAUSTION_STATUSES = ("WARNING_ESTABLISHED", "INSUFFICIENT_CONFIRMATION",
                       "UNVERIFIED", "CONFLICT", "BLOCKED")

COMPONENT_FAMILIES = ("MOMENTUM_STALL", "PRICE_VOLUME_DIVERGENCE",
                      "STRUCTURAL_FAILURE", "OSCILLATOR_EXTREME")

PROVENANCE_STATUS = ("AUTHORITATIVE", "VERIFIED_INPUT", "UNKNOWN")
_TRUSTED = ("AUTHORITATIVE", "VERIFIED_INPUT")
ASOF_STATUSES = ("ASOF_VERIFIED", "TEMPORAL_UNVERIFIED", "LEGACY_TEMPORAL_UNVERIFIED")
ROLL_STATUSES = ("NONE", "ROLL_BOUNDARY", "UNKNOWN", "NOT_APPLICABLE")
SERIES_SEMANTICS = ("CONTINUOUS", "CONTRACT", "CASH", "INDEX", "UNKNOWN")

_ASOF_RANK = {"ASOF_VERIFIED": 2, "TEMPORAL_UNVERIFIED": 1, "LEGACY_TEMPORAL_UNVERIFIED": 0}

BLOCKED_ROLL_PROVENANCE = "BLOCKED_ROLL_PROVENANCE"
BLOCKED_SERIES_SEMANTICS_MISMATCH = "BLOCKED_SERIES_SEMANTICS_MISMATCH"
BLOCKED_ATR_POLICY_MISMATCH = "BLOCKED_ATR_POLICY_MISMATCH"
BLOCKED_SOURCE_PROVENANCE = "BLOCKED_SOURCE_PROVENANCE"
BLOCKED_IDENTITY_MISMATCH = "BLOCKED_IDENTITY_MISMATCH"
BLOCKED_CONTEXT_CONTRACT = "BLOCKED_CONTEXT_CONTRACT"
BLOCKED_TEMPORAL_EVIDENCE_PROVENANCE = "BLOCKED_TEMPORAL_EVIDENCE_PROVENANCE"
BLOCKED_FUTURE_EVIDENCE = "BLOCKED_FUTURE_EVIDENCE"
BLOCKED_COMPONENT_ID_COLLISION = "BLOCKED_COMPONENT_ID_COLLISION"
BLOCKED_DIRECT_FUTURE_OUTCOME_SOURCE = "BLOCKED_DIRECT_FUTURE_OUTCOME_SOURCE"
BLOCKED_STATE_STREAM_MISMATCH = "BLOCKED_STATE_STREAM_MISMATCH"
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


def _component_fp(c: "ExhaustionComponentEvidence") -> str:
    d = {
        "id": c.component_id, "family": c.family, "present": str(c.present),
        "inst": normalize_instrument(c.instrument), "fam": normalize_family(c.target_family),
        "role": c.instrument_role, "cal": c.calendar_id, "freq": c.frequency, "hor": c.horizon,
        "event": c.event_timestamp.isoformat() if c.event_timestamp else "",
        "avail": c.available_at.isoformat() if c.available_at else "",
        "src": c.source_type, "schema": c.source_schema_version, "ver": c.source_version,
        "snaps": "|".join(_canonical(c.source_snapshot_ids)),
        "asof": c.asof_status, "prov": c.provenance_status, "val": c.validation_status,
    }
    return _id_fp([f"{k}={v}" for k, v in sorted(d.items())])


# ── PointInTimeScalar ──
@dataclass
class PointInTimeScalar:
    name: str = ""
    value: float | None = None
    instrument: str = ""
    target_family: str = ""
    instrument_role: str = "DIRECT"
    calendar_id: str = ""
    frequency: str = "DAILY"
    horizon: str = "1d"
    series_semantics: str = "UNKNOWN"
    roll_status: str = "UNKNOWN"
    event_timestamp: datetime | None = None
    available_at: datetime | None = None
    source_type: str = ""
    source_schema_version: str = ""
    source_version: str = ""
    source_snapshot_ids: list[str] = dfield(default_factory=list)
    asof_status: str = "LEGACY_TEMPORAL_UNVERIFIED"
    provenance_status: str = "UNKNOWN"
    atr_period: int = 0
    atr_method: str = ""

    def __post_init__(self):
        if not self.name or not self.name.strip():
            raise ValueError("PointInTimeScalar.name must be non-empty")
        if self.value is None or not _finite(self.value):
            raise ValueError(f"PointInTimeScalar.value must be finite (got {self.value!r})")
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
                raise ValueError(f"PointInTimeScalar.{name} must be non-null")
            if v.tzinfo is None:
                raise ValueError(f"PointInTimeScalar.{name} must be tz-aware")
            setattr(self, name, ensure_utc_aware(v))
        self.instrument = normalize_instrument(self.instrument)
        self.target_family = normalize_family(self.target_family)

    def model_dump(self) -> dict:
        return asdict(self)


# ── DailyExtensionPolicy (frozen) ──
_FROZEN_EXT = dict(version="2E.3", scope="DAILY_RESEARCH_PROXY", reference_kind="PREVIOUS_CLOSE",
                   atr_period=14, atr_method=ATR_METHOD, extended_threshold_atr=1.0,
                   extreme_threshold_atr=2.0, validation_status="HYPOTHESIS_ONLY",
                   optimization_status="NOT_OPTIMIZED")


@dataclass
class DailyExtensionPolicy:
    version: str = "2E.3"
    scope: str = "DAILY_RESEARCH_PROXY"
    reference_kind: str = "PREVIOUS_CLOSE"
    atr_period: int = 14
    atr_method: str = ATR_METHOD
    extended_threshold_atr: float = 1.0
    extreme_threshold_atr: float = 2.0
    validation_status: str = "HYPOTHESIS_ONLY"
    optimization_status: str = "NOT_OPTIMIZED"

    def __post_init__(self):
        for k, v in _FROZEN_EXT.items():
            if getattr(self, k) != v:
                raise ValueError(f"DailyExtensionPolicy.{k} is frozen to {v!r}; got {getattr(self, k)!r}")

    def model_dump(self) -> dict:
        return asdict(self)


# ── DailyExtensionAssessment ──
@dataclass
class DailyExtensionAssessment:
    assessment_id: str = ""
    instrument: str = ""
    target_family: str = ""
    instrument_role: str = "DIRECT"
    calendar_id: str = ""
    frequency: str = "DAILY"
    horizon: str = "1d"
    feature_cutoff_timestamp: datetime | None = None
    state_origin: datetime | None = None
    current_price: float | None = None
    current_price_event_timestamp: datetime | None = None
    current_price_available_at: datetime | None = None
    extension_event_timestamp: datetime | None = None
    extension_available_at: datetime | None = None
    reference_price: float | None = None
    reference_kind: str = "PREVIOUS_CLOSE"
    atr_baseline: float | None = None
    signed_extension_units: float | None = None
    absolute_extension_units: float | None = None
    extension_side: str = "FLAT"
    extension_state: str | None = None
    assessment_status: str = "UNVERIFIED"
    validation_status: str = "HYPOTHESIS_ONLY"
    optimization_status: str = "NOT_OPTIMIZED"
    roll_status: str = "UNKNOWN"
    series_semantics: str = "UNKNOWN"
    context_source_snapshot_ids: list[str] = dfield(default_factory=list)
    current_price_source_snapshot_ids: list[str] = dfield(default_factory=list)
    reference_price_source_snapshot_ids: list[str] = dfield(default_factory=list)
    atr_source_snapshot_ids: list[str] = dfield(default_factory=list)
    source_snapshot_ids: list[str] = dfield(default_factory=list)
    context_asof_status: str = "LEGACY_TEMPORAL_UNVERIFIED"
    current_price_asof_status: str = "LEGACY_TEMPORAL_UNVERIFIED"
    reference_price_asof_status: str = "LEGACY_TEMPORAL_UNVERIFIED"
    atr_asof_status: str = "LEGACY_TEMPORAL_UNVERIFIED"
    derived_asof_status: str = "LEGACY_TEMPORAL_UNVERIFIED"
    block_reason_codes: list[str] = dfield(default_factory=list)
    blocked_input_roles: list[str] = dfield(default_factory=list)
    schema_version: str = V2_EXTENSION_EXHAUSTION_SCHEMA_VERSION
    policy_version: str = "2E.3"

    def model_dump(self) -> dict:
        return asdict(self)


# ── ExhaustionComponentEvidence ──
@dataclass
class ExhaustionComponentEvidence:
    component_id: str = ""
    family: str = ""
    present: bool = False
    instrument: str = ""
    target_family: str = ""
    instrument_role: str = "DIRECT"
    calendar_id: str = ""
    frequency: str = "DAILY"
    horizon: str = "1d"
    event_timestamp: datetime | None = None
    available_at: datetime | None = None
    source_type: str = ""
    source_schema_version: str = ""
    source_version: str = ""
    source_snapshot_ids: list[str] = dfield(default_factory=list)
    asof_status: str = "LEGACY_TEMPORAL_UNVERIFIED"
    provenance_status: str = "UNKNOWN"
    validation_status: str = "HYPOTHESIS_ONLY"

    def __post_init__(self):
        if not self.component_id or not self.component_id.strip():
            raise ValueError("component_id must be non-empty")
        if self.family not in COMPONENT_FAMILIES:
            raise ValueError(f"unknown component family: {self.family!r}")
        if type(self.present) is not bool:
            raise ValueError("present must be a bool")
        if self.provenance_status not in PROVENANCE_STATUS:
            raise ValueError(f"unknown provenance_status: {self.provenance_status!r}")
        if self.asof_status not in ASOF_STATUSES:
            raise ValueError(f"unknown asof_status: {self.asof_status!r}")
        if self.validation_status != "HYPOTHESIS_ONLY":
            raise ValueError("component validation_status must be HYPOTHESIS_ONLY")
        for name in ("event_timestamp", "available_at"):
            v = getattr(self, name)
            if v is not None:
                if v.tzinfo is None:
                    raise ValueError(f"{name} must be tz-aware")
                setattr(self, name, ensure_utc_aware(v))
        self.instrument = normalize_instrument(self.instrument)
        self.target_family = normalize_family(self.target_family)

    def model_dump(self) -> dict:
        return asdict(self)


# ── DailyExhaustionPolicy (frozen) ──
_FROZEN_EXH = dict(version="2E.3", scope="DAILY_RESEARCH_PROXY", requires_extension="EXTENDED_OR_EXTREME",
                   minimum_distinct_confirmation_families=2, validation_status="HYPOTHESIS_ONLY",
                   optimization_status="NOT_OPTIMIZED")


@dataclass
class DailyExhaustionPolicy:
    version: str = "2E.3"
    scope: str = "DAILY_RESEARCH_PROXY"
    requires_extension: str = "EXTENDED_OR_EXTREME"
    minimum_distinct_confirmation_families: int = 2
    validation_status: str = "HYPOTHESIS_ONLY"
    optimization_status: str = "NOT_OPTIMIZED"

    def __post_init__(self):
        for k, v in _FROZEN_EXH.items():
            if getattr(self, k) != v:
                raise ValueError(f"DailyExhaustionPolicy.{k} is frozen to {v!r}; got {getattr(self, k)!r}")

    def model_dump(self) -> dict:
        return asdict(self)


# ── DailyExhaustionAssessment ──
@dataclass
class DailyExhaustionAssessment:
    assessment_id: str = ""
    instrument: str = ""
    target_family: str = ""
    instrument_role: str = "DIRECT"
    calendar_id: str = ""
    frequency: str = "DAILY"
    horizon: str = "1d"
    feature_cutoff_timestamp: datetime | None = None
    state_origin: datetime | None = None
    extension_assessment_id: str = ""
    extension_state: str | None = None
    positive_confirmation_families: list[str] = dfield(default_factory=list)
    positive_component_ids: list[str] = dfield(default_factory=list)
    unverified_component_ids: list[str] = dfield(default_factory=list)
    conflict_families: list[str] = dfield(default_factory=list)
    conflicting_component_ids: list[str] = dfield(default_factory=list)
    negative_component_ids: list[str] = dfield(default_factory=list)
    component_ids: list[str] = dfield(default_factory=list)
    component_asof_by_id: dict[str, str] = dfield(default_factory=dict)
    required_confirmation_families: list[str] = dfield(default_factory=list)
    required_component_ids: list[str] = dfield(default_factory=list)
    confirmation_family_count: int = 0
    warning_established: bool = False
    warning_event_timestamp: datetime | None = None
    warning_available_at: datetime | None = None
    assessment_status: str = "UNVERIFIED"
    validation_status: str = "HYPOTHESIS_ONLY"
    optimization_status: str = "NOT_OPTIMIZED"
    context_source_snapshot_ids: list[str] = dfield(default_factory=list)
    extension_source_snapshot_ids: list[str] = dfield(default_factory=list)
    component_source_snapshot_ids: list[str] = dfield(default_factory=list)
    source_snapshot_ids: list[str] = dfield(default_factory=list)
    derived_asof_status: str = "LEGACY_TEMPORAL_UNVERIFIED"
    block_reason_codes: list[str] = dfield(default_factory=list)
    schema_version: str = V2_EXTENSION_EXHAUSTION_SCHEMA_VERSION
    policy_version: str = "2E.3"

    def model_dump(self) -> dict:
        return asdict(self)


# ── extension evaluation ──
def evaluate_extension(
    context: StateEvaluationContext,
    current_close: PointInTimeScalar,
    previous_close: PointInTimeScalar,
    atr_baseline: PointInTimeScalar,
    policy: DailyExtensionPolicy | None = None,
) -> DailyExtensionAssessment:
    policy = policy or DailyExtensionPolicy()
    scalars = {"CURRENT_PRICE": current_close, "REFERENCE_PRICE": previous_close, "ATR_BASELINE": atr_baseline}

    # build base with FULL lineage first (§28/§32) — preserved on all statuses
    a = DailyExtensionAssessment(
        instrument=context.instrument, target_family=context.target_family,
        instrument_role=context.instrument_role, calendar_id=context.calendar_id,
        frequency=context.frequency, horizon=context.horizon,
        feature_cutoff_timestamp=context.feature_cutoff_timestamp, state_origin=context.state_origin,
        context_source_snapshot_ids=_canonical(context.source_snapshot_ids),
        current_price_source_snapshot_ids=_canonical(current_close.source_snapshot_ids),
        reference_price_source_snapshot_ids=_canonical(previous_close.source_snapshot_ids),
        atr_source_snapshot_ids=_canonical(atr_baseline.source_snapshot_ids),
        context_asof_status=context.asof_status,
        current_price_asof_status=current_close.asof_status,
        reference_price_asof_status=previous_close.asof_status,
        atr_asof_status=atr_baseline.asof_status,
    )
    a.source_snapshot_ids = _canonical(a.context_source_snapshot_ids + a.current_price_source_snapshot_ids
                                       + a.reference_price_source_snapshot_ids + a.atr_source_snapshot_ids)
    a.derived_asof_status = _least_verified([context.asof_status, current_close.asof_status,
                                             previous_close.asof_status, atr_baseline.asof_status])

    def block(reason, roles=()):
        a.assessment_status = "BLOCKED"
        a.block_reason_codes = [reason]
        a.blocked_input_roles = _canonical(list(roles))
        a.assessment_id = _extension_identity(a)
        return a

    # context contract
    if context.validate_contract():
        return block(BLOCKED_CONTEXT_CONTRACT, ["CONTEXT"])

    # scalar identity
    for role, sc in scalars.items():
        for name in ("instrument", "target_family", "instrument_role", "calendar_id", "frequency", "horizon"):
            if not getattr(sc, name) or not str(getattr(sc, name)).strip():
                return block(BLOCKED_IDENTITY_MISMATCH, [role])
        if (normalize_instrument(sc.instrument) != normalize_instrument(context.instrument)
                or normalize_family(sc.target_family) != normalize_family(context.target_family)
                or sc.instrument_role != context.instrument_role
                or sc.calendar_id != context.calendar_id
                or sc.frequency != context.frequency
                or sc.horizon != context.horizon):
            return block(BLOCKED_IDENTITY_MISMATCH, [role])

    # series semantics
    series_set = {sc.series_semantics for sc in scalars.values()}
    if len(series_set) > 1:
        return block(BLOCKED_SERIES_SEMANTICS_MISMATCH)
    a.series_semantics = next(iter(series_set))

    # roll
    if _is_futures(context):
        bad = [role for role, sc in scalars.items() if sc.roll_status != "NONE"]
        if bad:
            return block(BLOCKED_ROLL_PROVENANCE, bad)
        a.roll_status = "NONE"
    else:
        rolls = {sc.roll_status for sc in scalars.values()}
        a.roll_status = next(iter(rolls)) if len(rolls) == 1 else "UNKNOWN"

    # ATR provenance
    if atr_baseline.atr_period != policy.atr_period or atr_baseline.atr_method != policy.atr_method:
        return block(BLOCKED_ATR_POLICY_MISMATCH, ["ATR_BASELINE"])

    # source identity
    for role, sc in scalars.items():
        for name in ("source_type", "source_schema_version", "source_version"):
            if not getattr(sc, name) or not str(getattr(sc, name)).strip():
                return block(BLOCKED_SOURCE_PROVENANCE, [role])

    # temporal completeness + ordering
    for role, sc in scalars.items():
        if ensure_utc_aware(sc.event_timestamp) > ensure_utc_aware(sc.available_at):
            return block(BLOCKED_TEMPORAL_EVIDENCE_PROVENANCE, [role])
    atr_ev = ensure_utc_aware(atr_baseline.event_timestamp)
    prev_ev = ensure_utc_aware(previous_close.event_timestamp)
    curr_ev = ensure_utc_aware(current_close.event_timestamp)
    if not (atr_ev <= prev_ev < curr_ev):
        return block(BLOCKED_TEMPORAL_EVIDENCE_PROVENANCE)
    cutoff = context.feature_cutoff_timestamp
    for role, sc in scalars.items():
        if cutoff is not None and ensure_utc_aware(sc.available_at) > ensure_utc_aware(cutoff):
            return block(BLOCKED_FUTURE_EVIDENCE, [role])

    # numeric quality
    for role, sc in scalars.items():
        if not _positive(sc.value):
            return block(INVALID_INPUT, [role])

    # provenance UNKNOWN → UNVERIFIED
    if any(sc.provenance_status == "UNKNOWN" for sc in scalars.values()):
        a.current_price = current_close.value
        a.reference_price = previous_close.value
        a.atr_baseline = atr_baseline.value
        a.assessment_status = "UNVERIFIED"
        a.extension_state = None
        a.assessment_id = _extension_identity(a)
        return a

    signed = (current_close.value - previous_close.value) / atr_baseline.value
    absu = abs(signed)
    side = "UP" if signed > 0 else ("DOWN" if signed < 0 else "FLAT")
    if absu < policy.extended_threshold_atr:
        state = "NORMAL"
    elif absu < policy.extreme_threshold_atr:
        state = "EXTENDED"
    else:
        state = "EXTREME"

    a.current_price = current_close.value
    a.current_price_event_timestamp = current_close.event_timestamp
    a.current_price_available_at = current_close.available_at
    a.extension_event_timestamp = current_close.event_timestamp
    a.extension_available_at = max(ensure_utc_aware(current_close.available_at),
                                   ensure_utc_aware(previous_close.available_at),
                                   ensure_utc_aware(atr_baseline.available_at))
    a.reference_price = previous_close.value
    a.atr_baseline = atr_baseline.value
    a.signed_extension_units = signed
    a.absolute_extension_units = absu
    a.extension_side = side
    a.extension_state = state
    a.assessment_status = "EVALUATED"
    a.assessment_id = _extension_identity(a)
    return a


def _extension_identity(a: DailyExtensionAssessment) -> str:
    parts = [
        normalize_instrument(a.instrument), normalize_family(a.target_family),
        a.instrument_role, a.calendar_id, a.frequency, a.horizon,
        a.feature_cutoff_timestamp.isoformat() if a.feature_cutoff_timestamp else "",
        a.state_origin.isoformat() if a.state_origin else "",
        V2_EXTENSION_EXHAUSTION_SCHEMA_VERSION, a.policy_version,
        str(a.current_price), str(a.reference_price), str(a.atr_baseline),
        str(a.signed_extension_units), str(a.absolute_extension_units),
        str(a.extension_side), str(a.extension_state), a.assessment_status,
        a.roll_status, a.series_semantics,
        a.extension_event_timestamp.isoformat() if a.extension_event_timestamp else "",
        a.extension_available_at.isoformat() if a.extension_available_at else "",
        "|".join(_canonical(a.current_price_source_snapshot_ids)),
        "|".join(_canonical(a.reference_price_source_snapshot_ids)),
        "|".join(_canonical(a.atr_source_snapshot_ids)),
        "|".join(_canonical(a.context_source_snapshot_ids)),
        a.derived_asof_status,
        "|".join(_canonical(a.block_reason_codes)),
        "|".join(_canonical(a.blocked_input_roles)),
    ]
    return _id_fp(parts)


# ── exhaustion evaluation ──
def evaluate_exhaustion(
    extension: DailyExtensionAssessment,
    components: list[ExhaustionComponentEvidence],
    context: StateEvaluationContext,
    policy: DailyExhaustionPolicy | None = None,
) -> DailyExhaustionAssessment:
    policy = policy or DailyExhaustionPolicy()
    base = DailyExhaustionAssessment(
        instrument=context.instrument, target_family=context.target_family,
        instrument_role=context.instrument_role, calendar_id=context.calendar_id,
        frequency=context.frequency, horizon=context.horizon,
        feature_cutoff_timestamp=context.feature_cutoff_timestamp, state_origin=context.state_origin,
        extension_assessment_id=extension.assessment_id, extension_state=extension.extension_state,
        context_source_snapshot_ids=_canonical(context.source_snapshot_ids),
        extension_source_snapshot_ids=_canonical(extension.source_snapshot_ids),
    )

    def block(reason):
        base.assessment_status = "BLOCKED"
        base.block_reason_codes = [reason]
        base.assessment_id = _exhaustion_identity(base)
        return base

    # context contract
    if context.validate_contract():
        return block(BLOCKED_CONTEXT_CONTRACT)

    # same state stream (§7/§8): identity + cutoff/origin
    if (normalize_instrument(extension.instrument) != normalize_instrument(context.instrument)
            or normalize_family(extension.target_family) != normalize_family(context.target_family)
            or extension.instrument_role != context.instrument_role
            or extension.calendar_id != context.calendar_id
            or extension.frequency != context.frequency
            or extension.horizon != context.horizon):
        return block(BLOCKED_IDENTITY_MISMATCH)
    if (extension.feature_cutoff_timestamp is None or context.feature_cutoff_timestamp is None
            or ensure_utc_aware(extension.feature_cutoff_timestamp) != ensure_utc_aware(context.feature_cutoff_timestamp)
            or extension.state_origin is None or context.state_origin is None
            or ensure_utc_aware(extension.state_origin) != ensure_utc_aware(context.state_origin)):
        return block(BLOCKED_STATE_STREAM_MISMATCH)

    # extension must be EVALUATED + EXTENDED/EXTREME
    if extension.assessment_status != "EVALUATED":
        return block("BLOCKED_EXTENSION_NOT_EVALUATED")
    if extension.extension_state not in ("EXTENDED", "EXTREME"):
        base.source_snapshot_ids = _canonical(base.context_source_snapshot_ids
                                              + base.extension_source_snapshot_ids)
        base.derived_asof_status = _least_verified([context.asof_status, extension.derived_asof_status])
        base.assessment_status = "INSUFFICIENT_CONFIRMATION"
        base.warning_established = False
        base.assessment_id = _exhaustion_identity(base)
        return base

    # component dedupe + collision (§19)
    seen: dict[str, ExhaustionComponentEvidence] = {}
    for comp in components:
        if comp.component_id in seen:
            if asdict(seen[comp.component_id]) != asdict(comp):
                return block(BLOCKED_COMPONENT_ID_COLLISION)
            continue
        seen[comp.component_id] = comp
    components = list(seen.values())

    # component lineage collected first (§21/§22/§23/§25)
    base.component_ids = _canonical([c.component_id for c in components])
    base.component_asof_by_id = {c.component_id: c.asof_status for c in sorted(components, key=lambda c: c.component_id)}
    base.component_source_snapshot_ids = _canonical([sid for c in components for sid in c.source_snapshot_ids])
    base.source_snapshot_ids = _canonical(base.context_source_snapshot_ids
                                          + base.extension_source_snapshot_ids
                                          + base.component_source_snapshot_ids)

    trusted_by_family: dict[str, list[ExhaustionComponentEvidence]] = {}
    unverified_ids: list[str] = []
    for comp in components:
        if comp.source_type == "V2C_OUTCOME":
            base.derived_asof_status = _least_verified([context.asof_status, extension.derived_asof_status]
                                                       + [c.asof_status for c in components])
            return block(BLOCKED_DIRECT_FUTURE_OUTCOME_SOURCE)
        if comp.event_timestamp is None or comp.available_at is None:
            return block(BLOCKED_TEMPORAL_EVIDENCE_PROVENANCE)
        if ensure_utc_aware(comp.event_timestamp) > ensure_utc_aware(comp.available_at):
            return block(BLOCKED_TEMPORAL_EVIDENCE_PROVENANCE)
        if context.feature_cutoff_timestamp is not None and \
                ensure_utc_aware(comp.available_at) > ensure_utc_aware(context.feature_cutoff_timestamp):
            return block(BLOCKED_FUTURE_EVIDENCE)
        for name in ("source_type", "source_schema_version", "source_version"):
            if not getattr(comp, name) or not str(getattr(comp, name)).strip():
                return block(BLOCKED_SOURCE_PROVENANCE)
        if (normalize_instrument(comp.instrument) != normalize_instrument(context.instrument)
                or normalize_family(comp.target_family) != normalize_family(context.target_family)
                or comp.instrument_role != context.instrument_role
                or comp.calendar_id != context.calendar_id
                or comp.frequency != context.frequency
                or comp.horizon != context.horizon):
            return block(BLOCKED_IDENTITY_MISMATCH)
        if comp.provenance_status == "UNKNOWN":
            unverified_ids.append(comp.component_id)
            continue
        trusted_by_family.setdefault(comp.family, []).append(comp)

    base.unverified_component_ids = _canonical(unverified_ids)
    base.derived_asof_status = _least_verified([context.asof_status, extension.derived_asof_status]
                                               + [c.asof_status for c in components])

    # conflict + positive + negative classification (§23/§25)
    conflict_families: list[str] = []
    conflicting_ids: list[str] = []
    positive_by_family: dict[str, ExhaustionComponentEvidence] = {}
    negative_ids: list[str] = []
    for family, comps in trusted_by_family.items():
        values = {comp.present for comp in comps}
        if len(values) > 1:
            conflict_families.append(family)
            conflicting_ids.extend(comp.component_id for comp in comps)
            continue
        if values == {True}:
            # earliest-establishing evidence for this family (§14)
            earliest = min(comps, key=lambda c: (ensure_utc_aware(c.available_at), c.family, c.component_id))
            positive_by_family[family] = earliest
        else:  # {False}
            negative_ids.extend(comp.component_id for comp in comps)

    base.conflict_families = _canonical(conflict_families)
    base.conflicting_component_ids = _canonical(conflicting_ids)
    base.negative_component_ids = _canonical(negative_ids)
    base.positive_confirmation_families = _canonical(list(positive_by_family.keys()))
    base.positive_component_ids = _canonical([c.component_id for c in positive_by_family.values()])
    base.confirmation_family_count = len(positive_by_family)

    if conflict_families:
        base.assessment_status = "CONFLICT"
        base.warning_established = False
        base.assessment_id = _exhaustion_identity(base)
        return base

    # earliest K distinct families (§15/§16)
    k = policy.minimum_distinct_confirmation_families
    ordered = sorted(positive_by_family.values(),
                     key=lambda c: (ensure_utc_aware(c.available_at), c.family, c.component_id))
    if len(ordered) >= k:
        required = ordered[:k]
        base.required_confirmation_families = _canonical([c.family for c in required])
        base.required_component_ids = _canonical([c.component_id for c in required])
        base.warning_established = True
        base.assessment_status = "WARNING_ESTABLISHED"
        base.warning_event_timestamp = max([extension.extension_event_timestamp]
                                           + [c.event_timestamp for c in required])
        base.warning_available_at = max([extension.extension_available_at]
                                        + [c.available_at for c in required])
    else:
        base.warning_established = False
        base.assessment_status = "INSUFFICIENT_CONFIRMATION"

    base.assessment_id = _exhaustion_identity(base)
    return base


def _exhaustion_identity(a: DailyExhaustionAssessment) -> str:
    parts = [
        normalize_instrument(a.instrument), normalize_family(a.target_family),
        a.instrument_role, a.calendar_id, a.frequency, a.horizon,
        a.feature_cutoff_timestamp.isoformat() if a.feature_cutoff_timestamp else "",
        a.state_origin.isoformat() if a.state_origin else "",
        a.extension_assessment_id, str(a.extension_state),
        V2_EXTENSION_EXHAUSTION_SCHEMA_VERSION, a.policy_version,
        "|".join(_canonical(a.positive_confirmation_families)),
        "|".join(_canonical(a.positive_component_ids)),
        "|".join(_canonical(a.unverified_component_ids)),
        "|".join(_canonical(a.conflict_families)),
        "|".join(_canonical(a.conflicting_component_ids)),
        "|".join(_canonical(a.negative_component_ids)),
        "|".join(_canonical(a.component_ids)),
        "|".join(_canonical(a.required_confirmation_families)),
        "|".join(_canonical(a.required_component_ids)),
        str(a.confirmation_family_count), str(a.warning_established),
        a.warning_event_timestamp.isoformat() if a.warning_event_timestamp else "",
        a.warning_available_at.isoformat() if a.warning_available_at else "",
        "|".join(_canonical(a.context_source_snapshot_ids)),
        "|".join(_canonical(a.extension_source_snapshot_ids)),
        "|".join(_canonical(a.component_source_snapshot_ids)),
        a.derived_asof_status, a.assessment_status,
        "|".join(_canonical(a.block_reason_codes)),
    ]
    return _id_fp(parts)


# ── adapters ──
def _evidence_id(ctx: StateEvaluationContext, layer: str, value: str, source_type: str) -> str:
    parts = [
        normalize_instrument(ctx.instrument), normalize_family(ctx.target_family),
        ctx.instrument_role, ctx.calendar_id, ctx.frequency, ctx.horizon,
        ctx.feature_cutoff_timestamp.isoformat() if ctx.feature_cutoff_timestamp else "",
        ctx.state_origin.isoformat() if ctx.state_origin else "",
        V2_EXTENSION_EXHAUSTION_SCHEMA_VERSION, layer, value, source_type,
    ]
    return "v2e_" + _id_fp(parts)


def _same_stream(ctx: StateEvaluationContext, instrument: str, target_family: str, instrument_role: str,
                 calendar_id: str, frequency: str, horizon: str,
                 cutoff: datetime | None, origin: datetime | None) -> bool:
    if not (normalize_instrument(instrument) == normalize_instrument(ctx.instrument)
            and normalize_family(target_family) == normalize_family(ctx.target_family)
            and instrument_role == ctx.instrument_role
            and calendar_id == ctx.calendar_id
            and frequency == ctx.frequency
            and horizon == ctx.horizon):
        return False
    if (cutoff is None or ctx.feature_cutoff_timestamp is None
            or ensure_utc_aware(cutoff) != ensure_utc_aware(ctx.feature_cutoff_timestamp)
            or origin is None or ctx.state_origin is None
            or ensure_utc_aware(origin) != ensure_utc_aware(ctx.state_origin)):
        return False
    return True


def extension_to_state_evidence(assessment: DailyExtensionAssessment,
                                context: StateEvaluationContext) -> StateEvidence | None:
    if assessment.assessment_status != "EVALUATED" or assessment.extension_state is None:
        return None
    if not _same_stream(context, assessment.instrument, assessment.target_family,
                        assessment.instrument_role, assessment.calendar_id,
                        assessment.frequency, assessment.horizon,
                        assessment.feature_cutoff_timestamp, assessment.state_origin):
        raise ValueError("extension assessment does not match context state stream (no retarget)")
    return StateEvidence(
        evidence_id=_evidence_id(context, "EXTENSION", assessment.extension_state, "V2E_EXTENSION"),
        layer="EXTENSION", value=assessment.extension_state,
        instrument=context.instrument, target_family=context.target_family,
        instrument_role=context.instrument_role, calendar_id=context.calendar_id,
        frequency=context.frequency, horizon=context.horizon,
        event_timestamp=assessment.extension_event_timestamp,
        available_at=assessment.extension_available_at,
        source_type="V2E_EXTENSION", source_schema_version=V2_EXTENSION_EXHAUSTION_SCHEMA_VERSION,
        source_version=assessment.policy_version,
        source_snapshot_ids=list(assessment.source_snapshot_ids),
        asof_status=assessment.derived_asof_status,
        provenance_status="VERIFIED_INPUT", validation_status="HYPOTHESIS_ONLY",
    )


def exhaustion_to_state_evidence(assessment: DailyExhaustionAssessment,
                                 context: StateEvaluationContext) -> StateEvidence | None:
    if assessment.assessment_status != "WARNING_ESTABLISHED":
        return None
    if not _same_stream(context, assessment.instrument, assessment.target_family,
                        assessment.instrument_role, assessment.calendar_id,
                        assessment.frequency, assessment.horizon,
                        assessment.feature_cutoff_timestamp, assessment.state_origin):
        raise ValueError("exhaustion assessment does not match context state stream (no retarget)")
    return StateEvidence(
        evidence_id=_evidence_id(context, "RISK", "EXHAUSTION_WARNING", "V2E_EXHAUSTION"),
        layer="RISK", value="EXHAUSTION_WARNING",
        instrument=context.instrument, target_family=context.target_family,
        instrument_role=context.instrument_role, calendar_id=context.calendar_id,
        frequency=context.frequency, horizon=context.horizon,
        event_timestamp=assessment.warning_event_timestamp,
        available_at=assessment.warning_available_at,
        source_type="V2E_EXHAUSTION", source_schema_version=V2_EXTENSION_EXHAUSTION_SCHEMA_VERSION,
        source_version=assessment.policy_version,
        source_snapshot_ids=list(assessment.source_snapshot_ids),
        asof_status=assessment.derived_asof_status,
        provenance_status="VERIFIED_INPUT", validation_status="HYPOTHESIS_ONLY",
    )
