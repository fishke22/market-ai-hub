"""V2-E — Daily Extension / Exhaustion Research Engine.

RESEARCH ONLY. Point-in-time DAILY extension evaluator (ATR-normalized move from previous close),
typed Exhaustion component evidence, and a multi-component Exhaustion Warning research evaluator.

Formal invariants:
- EXTENSION != EXHAUSTION; EXHAUSTION_WARNING != REVERSAL / BEARISH / CHASE_STOP / SHORT / SELL.
- Extension direction (UP/DOWN) is NOT Directional/Bullish/Bearish.
- Extension is a DAILY_RESEARCH_PROXY; no intraday/VWAP/session-high-low/order-flow.
- ATR baseline is pre-move (atr_event <= previous_close_event < current_close_event).
- Exhaustion requires EXTENDED_OR_EXTREME + >=2 distinct trusted confirmation families.
- No probability, no trading semantics, no future-outcome leakage.

Schema: V2_EXTENSION_EXHAUSTION_SCHEMA_VERSION = "2E.1"  (independent from 2A.1/2B.1/2C.2/2D.3/3A.2.3)
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field as dfield, asdict
from datetime import datetime
from hashlib import sha256
from typing import Any

from market_ai_hub.research.v2.asof import normalize_instrument, normalize_family, ensure_utc_aware
from market_ai_hub.research.v2.state_machine import StateEvaluationContext, StateEvidence

V2_EXTENSION_EXHAUSTION_SCHEMA_VERSION = "2E.1"

# ── enums ──
EXTENSION_STATES = ("NORMAL", "EXTENDED", "EXTREME")
EXTENSION_SIDES = ("UP", "DOWN", "FLAT")
REFERENCE_KINDS = ("PREVIOUS_CLOSE", "SESSION_OPEN", "SMA20", "EMA20", "VWAP", "CUSTOM")
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
_ASOF_RANK = {"ASOF_VERIFIED": 2, "TEMPORAL_UNVERIFIED": 1, "LEGACY_TEMPORAL_UNVERIFIED": 0}


def _least_verified(asofs: list[str]) -> str:
    if not asofs:
        return "LEGACY_TEMPORAL_UNVERIFIED"
    return min(asofs, key=lambda s: _ASOF_RANK[s])


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


# ── PointInTimeScalar (§12) ──
@dataclass
class PointInTimeScalar:
    name: str = ""
    value: float | None = None
    event_timestamp: datetime | None = None
    available_at: datetime | None = None
    source_type: str = ""
    source_schema_version: str = ""
    source_version: str = ""
    source_snapshot_ids: list[str] = dfield(default_factory=list)
    asof_status: str = "LEGACY_TEMPORAL_UNVERIFIED"
    provenance_status: str = "UNKNOWN"

    def __post_init__(self):
        if not self.name or not self.name.strip():
            raise ValueError("PointInTimeScalar.name must be non-empty")
        if self.value is None or not _finite(self.value):
            raise ValueError(f"PointInTimeScalar.value must be finite (got {self.value!r})")
        if self.provenance_status not in PROVENANCE_STATUS:
            raise ValueError(f"unknown provenance_status: {self.provenance_status!r}")
        if self.asof_status not in ASOF_STATUSES:
            raise ValueError(f"unknown asof_status: {self.asof_status!r}")
        for name in ("event_timestamp", "available_at"):
            v = getattr(self, name)
            if v is None:
                raise ValueError(f"PointInTimeScalar.{name} must be non-null")
            if v.tzinfo is None:
                raise ValueError(f"PointInTimeScalar.{name} must be tz-aware")
            setattr(self, name, ensure_utc_aware(v))

    def model_dump(self) -> dict:
        return asdict(self)


# ── DailyExtensionPolicy (§15) ──
@dataclass
class DailyExtensionPolicy:
    version: str = "2E.1"
    scope: str = "DAILY_RESEARCH_PROXY"
    reference_kind: str = CANONICAL_REFERENCE
    atr_period: int = 14
    atr_method: str = ATR_METHOD
    extended_threshold_atr: float = 1.0
    extreme_threshold_atr: float = 2.0
    validation_status: str = "HYPOTHESIS_ONLY"
    optimization_status: str = "NOT_OPTIMIZED"

    def __post_init__(self):
        if self.reference_kind != CANONICAL_REFERENCE:
            raise ValueError(f"2E.1 canonical reference is {CANONICAL_REFERENCE}; got {self.reference_kind!r}")
        if self.atr_method != ATR_METHOD:
            raise ValueError(f"2E.1 canonical atr_method is {ATR_METHOD}; got {self.atr_method!r}")
        if not (_positive(self.extended_threshold_atr) and _positive(self.extreme_threshold_atr)):
            raise ValueError("thresholds must be positive")
        if self.extended_threshold_atr >= self.extreme_threshold_atr:
            raise ValueError("extended_threshold must be < extreme_threshold")

    def model_dump(self) -> dict:
        return asdict(self)


# ── DailyExtensionAssessment (§17) ──
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
    reference_price: float | None = None
    reference_kind: str = CANONICAL_REFERENCE
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
    source_snapshot_ids: list[str] = dfield(default_factory=list)
    derived_asof_status: str = "LEGACY_TEMPORAL_UNVERIFIED"
    block_reason_codes: list[str] = dfield(default_factory=list)
    schema_version: str = V2_EXTENSION_EXHAUSTION_SCHEMA_VERSION
    policy_version: str = "2E.1"

    def model_dump(self) -> dict:
        return asdict(self)


# ── ExhaustionComponentEvidence (§22/§23) ──
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
        if self.provenance_status not in PROVENANCE_STATUS:
            raise ValueError(f"unknown provenance_status: {self.provenance_status!r}")
        if self.asof_status not in ASOF_STATUSES:
            raise ValueError(f"unknown asof_status: {self.asof_status!r}")
        for name in ("event_timestamp", "available_at"):
            v = getattr(self, name)
            if v is not None and v.tzinfo is None:
                raise ValueError(f"{name} must be tz-aware")
        self.instrument = normalize_instrument(self.instrument)
        self.target_family = normalize_family(self.target_family)

    def model_dump(self) -> dict:
        return asdict(self)


# ── DailyExhaustionPolicy (§24) ──
@dataclass
class DailyExhaustionPolicy:
    version: str = "2E.1"
    scope: str = "DAILY_RESEARCH_PROXY"
    requires_extension: str = "EXTENDED_OR_EXTREME"
    minimum_distinct_confirmation_families: int = 2
    validation_status: str = "HYPOTHESIS_ONLY"
    optimization_status: str = "NOT_OPTIMIZED"

    def __post_init__(self):
        if self.minimum_distinct_confirmation_families < 2:
            raise ValueError("minimum_distinct_confirmation_families must be >= 2")

    def model_dump(self) -> dict:
        return asdict(self)


# ── DailyExhaustionAssessment (§30) ──
@dataclass
class DailyExhaustionAssessment:
    assessment_id: str = ""
    extension_assessment_id: str = ""
    extension_state: str | None = None
    positive_confirmation_families: list[str] = dfield(default_factory=list)
    positive_component_ids: list[str] = dfield(default_factory=list)
    unverified_component_ids: list[str] = dfield(default_factory=list)
    conflict_families: list[str] = dfield(default_factory=list)
    confirmation_family_count: int = 0
    warning_established: bool = False
    assessment_status: str = "UNVERIFIED"
    validation_status: str = "HYPOTHESIS_ONLY"
    optimization_status: str = "NOT_OPTIMIZED"
    source_snapshot_ids: list[str] = dfield(default_factory=list)
    derived_asof_status: str = "LEGACY_TEMPORAL_UNVERIFIED"
    block_reason_codes: list[str] = dfield(default_factory=list)
    schema_version: str = V2_EXTENSION_EXHAUSTION_SCHEMA_VERSION
    policy_version: str = "2E.1"

    def model_dump(self) -> dict:
        return asdict(self)


# ── extension evaluation (§8-§18) ──
def evaluate_extension(
    context: StateEvaluationContext,
    current_close: PointInTimeScalar,
    previous_close: PointInTimeScalar,
    atr_baseline: PointInTimeScalar,
    *,
    roll_status: str = "UNKNOWN",
    series_semantics: str = "UNKNOWN",
    policy: DailyExtensionPolicy | None = None,
) -> DailyExtensionAssessment:
    policy = policy or DailyExtensionPolicy()
    base = DailyExtensionAssessment(
        instrument=context.instrument, target_family=context.target_family,
        instrument_role=context.instrument_role, calendar_id=context.calendar_id,
        frequency=context.frequency, horizon=context.horizon,
        feature_cutoff_timestamp=context.feature_cutoff_timestamp, state_origin=context.state_origin,
        roll_status=roll_status, series_semantics=series_semantics, policy_version=policy.version,
    )

    # roll protection (§14)
    if _is_futures(context):
        if roll_status in ("ROLL_BOUNDARY", "UNKNOWN"):
            base.assessment_status = "BLOCKED"
            base.block_reason_codes = ["BLOCKED_ROLL_PROVENANCE"]
            base.assessment_id = _extension_identity(base)
            return base

    # scalar provenance completeness
    for sc in (current_close, previous_close, atr_baseline):
        for name in ("source_type", "source_schema_version", "source_version"):
            if not getattr(sc, name) or not str(getattr(sc, name)).strip():
                base.assessment_status = "BLOCKED"
                base.block_reason_codes = ["BLOCKED_SOURCE_PROVENANCE"]
                base.assessment_id = _extension_identity(base)
                return base
        if ensure_utc_aware(sc.event_timestamp) > ensure_utc_aware(sc.available_at):
            base.assessment_status = "BLOCKED"
            base.block_reason_codes = ["BLOCKED_TEMPORAL_EVIDENCE_PROVENANCE"]
            base.assessment_id = _extension_identity(base)
            return base

    cutoff = context.feature_cutoff_timestamp
    # temporal order (§10): atr <= previous_close < current_close
    atr_ev = ensure_utc_aware(atr_baseline.event_timestamp)
    prev_ev = ensure_utc_aware(previous_close.event_timestamp)
    curr_ev = ensure_utc_aware(current_close.event_timestamp)
    if not (atr_ev <= prev_ev < curr_ev):
        base.assessment_status = "BLOCKED"
        base.block_reason_codes = ["BLOCKED_TEMPORAL_EVIDENCE_PROVENANCE"]
        base.assessment_id = _extension_identity(base)
        return base
    # each available <= cutoff
    for sc in (current_close, previous_close, atr_baseline):
        if cutoff is not None and ensure_utc_aware(sc.available_at) > ensure_utc_aware(cutoff):
            base.assessment_status = "BLOCKED"
            base.block_reason_codes = ["BLOCKED_FUTURE_EVIDENCE"]
            base.assessment_id = _extension_identity(base)
            return base

    # numeric quality
    if not (_positive(previous_close.value) and _positive(current_close.value)
            and _positive(atr_baseline.value)):
        base.assessment_status = "BLOCKED"
        base.block_reason_codes = ["INVALID_INPUT"]
        base.assessment_id = _extension_identity(base)
        return base

    # provenance: UNKNOWN → UNVERIFIED
    if any(sc.provenance_status == "UNKNOWN" for sc in (current_close, previous_close, atr_baseline)):
        base.assessment_status = "UNVERIFIED"
        base.assessment_id = _extension_identity(base)
        return base

    # compute
    signed = (current_close.value - previous_close.value) / atr_baseline.value
    absu = abs(signed)
    side = "UP" if signed > 0 else ("DOWN" if signed < 0 else "FLAT")
    if absu < policy.extended_threshold_atr:
        state = "NORMAL"
    elif absu < policy.extreme_threshold_atr:
        state = "EXTENDED"
    else:
        state = "EXTREME"

    base.current_price = current_close.value
    base.current_price_event_timestamp = current_close.event_timestamp
    base.current_price_available_at = current_close.available_at
    base.reference_price = previous_close.value
    base.atr_baseline = atr_baseline.value
    base.signed_extension_units = signed
    base.absolute_extension_units = absu
    base.extension_side = side
    base.extension_state = state
    base.assessment_status = "EVALUATED"
    base.source_snapshot_ids = _canonical(current_close.source_snapshot_ids
                                          + previous_close.source_snapshot_ids
                                          + atr_baseline.source_snapshot_ids)
    base.derived_asof_status = _least_verified([current_close.asof_status, previous_close.asof_status,
                                                atr_baseline.asof_status])
    base.assessment_id = _extension_identity(base)
    return base


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
        "|".join(_canonical(a.block_reason_codes)),
    ]
    return _id_fp(parts)


# ── exhaustion evaluation (§22-§32) ──
def evaluate_exhaustion(
    extension: DailyExtensionAssessment,
    components: list[ExhaustionComponentEvidence],
    context: StateEvaluationContext,
    policy: DailyExhaustionPolicy | None = None,
) -> DailyExhaustionAssessment:
    policy = policy or DailyExhaustionPolicy()
    base = DailyExhaustionAssessment(
        extension_assessment_id=extension.assessment_id,
        extension_state=extension.extension_state,
        policy_version=policy.version,
    )

    # extension must be EVALUATED + EXTENDED/EXTREME
    if extension.assessment_status != "EVALUATED":
        base.assessment_status = "BLOCKED"
        base.block_reason_codes = ["BLOCKED_EXTENSION_NOT_EVALUATED"]
        base.assessment_id = _exhaustion_identity(base)
        return base
    if extension.extension_state not in ("EXTENDED", "EXTREME"):
        base.assessment_status = "INSUFFICIENT_CONFIRMATION"
        base.warning_established = False
        base.assessment_id = _exhaustion_identity(base)
        return base

    # validate components
    trusted_by_family: dict[str, list[ExhaustionComponentEvidence]] = {}
    unverified_ids: list[str] = []
    for comp in components:
        if comp.event_timestamp is None or comp.available_at is None:
            base.assessment_status = "BLOCKED"
            base.block_reason_codes = ["BLOCKED_TEMPORAL_EVIDENCE_PROVENANCE"]
            base.assessment_id = _exhaustion_identity(base)
            return base
        if ensure_utc_aware(comp.event_timestamp) > ensure_utc_aware(comp.available_at):
            base.assessment_status = "BLOCKED"
            base.block_reason_codes = ["BLOCKED_TEMPORAL_EVIDENCE_PROVENANCE"]
            base.assessment_id = _exhaustion_identity(base)
            return base
        if context.feature_cutoff_timestamp is not None and \
                ensure_utc_aware(comp.available_at) > ensure_utc_aware(context.feature_cutoff_timestamp):
            base.assessment_status = "BLOCKED"
            base.block_reason_codes = ["BLOCKED_FUTURE_EVIDENCE"]
            base.assessment_id = _exhaustion_identity(base)
            return base
        # identity match
        if (normalize_instrument(comp.instrument) != normalize_instrument(context.instrument)
                or normalize_family(comp.target_family) != normalize_family(context.target_family)
                or comp.instrument_role != context.instrument_role
                or comp.calendar_id != context.calendar_id
                or comp.frequency != context.frequency
                or comp.horizon != context.horizon):
            base.assessment_status = "BLOCKED"
            base.block_reason_codes = ["BLOCKED_IDENTITY_MISMATCH"]
            base.assessment_id = _exhaustion_identity(base)
            return base
        if comp.provenance_status == "UNKNOWN":
            unverified_ids.append(comp.component_id)
            continue
        trusted_by_family.setdefault(comp.family, []).append(comp)

    # conflict detection within family (§28)
    conflict_families: list[str] = []
    positive_families: list[str] = []
    positive_ids: list[str] = []
    for family, comps in trusted_by_family.items():
        values = {comp.present for comp in comps}
        if len(values) > 1:
            conflict_families.append(family)
            continue
        if values == {True}:
            positive_families.append(family)
            positive_ids.extend(comp.component_id for comp in comps)

    if conflict_families:
        base.conflict_families = _canonical(conflict_families)
        base.assessment_status = "CONFLICT"
        base.warning_established = False
        base.assessment_id = _exhaustion_identity(base)
        return base

    # distinct family count (§24/§25)
    distinct_count = len(positive_families)
    base.positive_confirmation_families = _canonical(positive_families)
    base.positive_component_ids = _canonical(positive_ids)
    base.unverified_component_ids = _canonical(unverified_ids)
    base.confirmation_family_count = distinct_count

    if distinct_count >= policy.minimum_distinct_confirmation_families:
        base.warning_established = True
        base.assessment_status = "WARNING_ESTABLISHED"
    else:
        base.warning_established = False
        base.assessment_status = "INSUFFICIENT_CONFIRMATION"

    base.source_snapshot_ids = _canonical([sid for c in components for sid in c.source_snapshot_ids])
    base.derived_asof_status = _least_verified([c.asof_status for c in components] or [extension.derived_asof_status])
    base.assessment_id = _exhaustion_identity(base)
    return base


def _exhaustion_identity(a: DailyExhaustionAssessment) -> str:
    parts = [
        a.extension_assessment_id, str(a.extension_state),
        V2_EXTENSION_EXHAUSTION_SCHEMA_VERSION, a.policy_version,
        "|".join(_canonical(a.positive_confirmation_families)),
        "|".join(_canonical(a.positive_component_ids)),
        "|".join(_canonical(a.conflict_families)),
        str(a.warning_established), a.assessment_status,
    ]
    return _id_fp(parts)


# ── adapters (§19/§32) ──
def _evidence_id(target: StateEvaluationContext, layer: str, value: str, source_type: str) -> str:
    parts = [
        normalize_instrument(target.instrument), normalize_family(target.target_family),
        target.instrument_role, target.calendar_id, target.frequency, target.horizon,
        target.feature_cutoff_timestamp.isoformat() if target.feature_cutoff_timestamp else "",
        target.state_origin.isoformat() if target.state_origin else "",
        V2_EXTENSION_EXHAUSTION_SCHEMA_VERSION, layer, value, source_type,
    ]
    return "v2e_" + _id_fp(parts)


def extension_to_state_evidence(assessment: DailyExtensionAssessment,
                                context: StateEvaluationContext) -> StateEvidence | None:
    if assessment.assessment_status != "EVALUATED" or assessment.extension_state is None:
        return None
    return StateEvidence(
        evidence_id=_evidence_id(context, "EXTENSION", assessment.extension_state, "V2E_EXTENSION"),
        layer="EXTENSION", value=assessment.extension_state,
        instrument=context.instrument, target_family=context.target_family,
        instrument_role=context.instrument_role, calendar_id=context.calendar_id,
        frequency=context.frequency, horizon=context.horizon,
        event_timestamp=assessment.current_price_event_timestamp,
        available_at=assessment.current_price_available_at,
        source_type="V2E_EXTENSION", source_schema_version=V2_EXTENSION_EXHAUSTION_SCHEMA_VERSION,
        source_version=assessment.policy_version,
        source_snapshot_ids=list(assessment.source_snapshot_ids),
        asof_status=assessment.derived_asof_status,
        provenance_status="VERIFIED_INPUT", validation_status="HYPOTHESIS_ONLY",
    )


def exhaustion_to_state_evidence(assessment: DailyExhaustionAssessment,
                                 context: StateEvaluationContext,
                                 current_event_timestamp: datetime | None = None,
                                 current_available_at: datetime | None = None) -> StateEvidence | None:
    if assessment.assessment_status != "WARNING_ESTABLISHED":
        return None
    return StateEvidence(
        evidence_id=_evidence_id(context, "RISK", "EXHAUSTION_WARNING", "V2E_EXHAUSTION"),
        layer="RISK", value="EXHAUSTION_WARNING",
        instrument=context.instrument, target_family=context.target_family,
        instrument_role=context.instrument_role, calendar_id=context.calendar_id,
        frequency=context.frequency, horizon=context.horizon,
        event_timestamp=current_event_timestamp,
        available_at=current_available_at,
        source_type="V2E_EXHAUSTION", source_schema_version=V2_EXTENSION_EXHAUSTION_SCHEMA_VERSION,
        source_version=assessment.policy_version,
        source_snapshot_ids=list(assessment.source_snapshot_ids),
        asof_status=assessment.derived_asof_status,
        provenance_status="VERIFIED_INPUT", validation_status="HYPOTHESIS_ONLY",
    )
