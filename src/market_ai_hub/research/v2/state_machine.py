"""V2-D — Dynamic State Machine Scaffold (typed multi-layer state contract).

RESEARCH ONLY. Deterministic evidence-composition engine for five state domains. This is a
SCAFFOLD, not a trading decision system.

Five domains (layer value vs evaluation status are SEPARATE):
- DIRECTIONAL: STRONG_BULL / BULLISH / NEUTRAL / BEARISH / STRONG_BEAR
- EXTENSION:   NORMAL / EXTENDED / EXTREME   (V2-E evaluator NOT built here)
- STRUCTURAL:  BREAKOUT_ATTEMPT / ACCEPTANCE_CONFIRMED / ACCEPTANCE_FAILED / REJECTION /
               BREAKDOWN_ATTEMPT / RECLAIM
- RISK:        NORMAL / EXHAUSTION_WARNING / REVERSAL_RISK / MODEL_FAILURE
- CHASE_RISK:  ALLOW / CAUTION / STOP   (independent of Direction; STOP != SHORT)

No evidence → value=None + status=NOT_EVALUATED (never default NEUTRAL/NORMAL/ALLOW).
V2-C Touch/Break/Acceptance are FORECAST-OUTCOME labels and MUST NOT leak into a forecast-time state.
No extension/exhaustion evaluator, no probability, no trading semantics, no persistence DB.

Schema: V2_STATE_MACHINE_SCHEMA_VERSION = "2D.1"  (independent from 2A.1 / 2B.1 / 2C.2 / 3A.2.3)
"""
from __future__ import annotations

from dataclasses import dataclass, field as dfield, asdict
from datetime import datetime
from hashlib import sha256
from typing import Any

from market_ai_hub.research.v2.asof import normalize_instrument, normalize_family, ensure_utc_aware

V2_STATE_MACHINE_SCHEMA_VERSION = "2D.1"

# ── enums ──
LAYERS = ("DIRECTIONAL", "EXTENSION", "STRUCTURAL", "RISK", "CHASE_RISK")

DIRECTIONAL_VALUES = ("STRONG_BULL", "BULLISH", "NEUTRAL", "BEARISH", "STRONG_BEAR")
EXTENSION_VALUES = ("NORMAL", "EXTENDED", "EXTREME")
STRUCTURAL_VALUES = ("BREAKOUT_ATTEMPT", "ACCEPTANCE_CONFIRMED", "ACCEPTANCE_FAILED",
                     "REJECTION", "BREAKDOWN_ATTEMPT", "RECLAIM")
RISK_VALUES = ("NORMAL", "EXHAUSTION_WARNING", "REVERSAL_RISK", "MODEL_FAILURE")
CHASE_RISK_VALUES = ("ALLOW", "CAUTION", "STOP")

_LAYER_VALUES = {
    "DIRECTIONAL": DIRECTIONAL_VALUES,
    "EXTENSION": EXTENSION_VALUES,
    "STRUCTURAL": STRUCTURAL_VALUES,
    "RISK": RISK_VALUES,
    "CHASE_RISK": CHASE_RISK_VALUES,
}

EVALUATION_STATUSES = ("NOT_EVALUATED", "EVALUATED", "UNVERIFIED", "CONFLICT", "BLOCKED")
SNAPSHOT_STATUSES = ("NO_EVIDENCE", "COMPOSED_PARTIAL", "COMPOSED_COMPLETE", "BLOCKED")
PROVENANCE_STATUS = ("AUTHORITATIVE", "VERIFIED_INPUT", "UNKNOWN")
_TRUSTED = ("AUTHORITATIVE", "VERIFIED_INPUT")
SUPPORTED_FREQUENCIES = ("DAILY",)

# evidence source types
SOURCE_V2C_OUTCOME = "V2C_OUTCOME"

# blockers
BLOCKED_IDENTITY_MISMATCH = "BLOCKED_IDENTITY_MISMATCH"
BLOCKED_TEMPORAL_CONTRACT = "BLOCKED_TEMPORAL_CONTRACT"
BLOCKED_FUTURE_EVIDENCE = "BLOCKED_FUTURE_EVIDENCE"
BLOCKED_FUTURE_OUTCOME_EVIDENCE = "BLOCKED_FUTURE_OUTCOME_EVIDENCE"
BLOCKED_EVIDENCE_ID_COLLISION = "BLOCKED_EVIDENCE_ID_COLLISION"
BLOCKED_UNSUPPORTED_FREQUENCY = "BLOCKED_UNSUPPORTED_FREQUENCY"
BLOCKED_TEMPORAL_TRANSITION = "BLOCKED_TEMPORAL_TRANSITION"

# ASOF conservativeness rank
_ASOF_RANK = {"ASOF_VERIFIED": 2, "TEMPORAL_UNVERIFIED": 1, "LEGACY_TEMPORAL_UNVERIFIED": 0}


def _least_verified_asof(statuses: list[str]) -> str:
    if not statuses:
        return "LEGACY_TEMPORAL_UNVERIFIED"
    return min(statuses, key=lambda s: _ASOF_RANK.get(s, 0))


# ── LayerState ──
@dataclass
class LayerState:
    value: str | None = None
    status: str = "NOT_EVALUATED"
    evidence_ids: list[str] = dfield(default_factory=list)
    source_snapshot_ids: list[str] = dfield(default_factory=list)
    reason_codes: list[str] = dfield(default_factory=list)

    def __post_init__(self):
        if self.status not in EVALUATION_STATUSES:
            raise ValueError(f"unknown evaluation status: {self.status!r}")

    def model_dump(self) -> dict:
        return asdict(self)


# ── StateEvaluationContext (§8) ──
@dataclass
class StateEvaluationContext:
    instrument: str = ""
    target_family: str = ""
    instrument_role: str = "DIRECT"
    calendar_id: str = ""
    frequency: str = "DAILY"
    horizon: str = "1d"
    feature_cutoff_timestamp: datetime | None = None
    state_origin: datetime | None = None
    source_snapshot_ids: list[str] = dfield(default_factory=list)
    asof_status: str = "LEGACY_TEMPORAL_UNVERIFIED"
    evaluation_mode: str = "RESEARCH"

    def __post_init__(self):
        if self.frequency not in SUPPORTED_FREQUENCIES:
            raise ValueError(f"unsupported frequency: {self.frequency!r} (V2-D supports DAILY only)")
        for name in ("feature_cutoff_timestamp", "state_origin"):
            v = getattr(self, name)
            if v is not None and v.tzinfo is None:
                raise ValueError(f"{name} must be tz-aware")

    def validate_ordering(self) -> list[str]:
        reasons = []
        if self.feature_cutoff_timestamp and self.state_origin \
                and self.feature_cutoff_timestamp > self.state_origin:
            reasons.append("CUTOFF_AFTER_ORIGIN")
        return reasons

    def model_dump(self) -> dict:
        return asdict(self)


# ── StateEvidence (§9/§12) ──
@dataclass
class StateEvidence:
    evidence_id: str = ""
    layer: str = ""
    value: str | None = None
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
    validation_status: str = "HYPOTHESIS_ONLY"
    provenance_status: str = "UNKNOWN"
    # V2C_OUTCOME-only provenance (§12)
    source_forecast_origin: datetime | None = None
    outcome_window_start: str = ""
    outcome_window_end: str = ""
    outcome_first_event_session: str = ""
    settled_at: datetime | None = None
    label_schema_version: str = ""
    notes: str = ""

    def __post_init__(self):
        if self.layer not in LAYERS:
            raise ValueError(f"unknown layer: {self.layer!r}")
        if self.value is not None and self.value not in _LAYER_VALUES[self.layer]:
            raise ValueError(f"value {self.value!r} invalid for layer {self.layer!r}")
        if self.frequency not in SUPPORTED_FREQUENCIES:
            raise ValueError(f"unsupported frequency: {self.frequency!r}")
        if self.provenance_status not in PROVENANCE_STATUS:
            raise ValueError(f"unknown provenance_status: {self.provenance_status!r}")
        for name in ("event_timestamp", "available_at", "source_forecast_origin", "settled_at"):
            v = getattr(self, name)
            if v is not None and v.tzinfo is None:
                raise ValueError(f"{name} must be tz-aware")

    def model_dump(self) -> dict:
        return asdict(self)


# ── StateSnapshot (§22) ──
@dataclass
class StateSnapshot:
    snapshot_id: str = ""
    instrument: str = ""
    target_family: str = ""
    instrument_role: str = "DIRECT"
    calendar_id: str = ""
    frequency: str = "DAILY"
    horizon: str = "1d"
    feature_cutoff_timestamp: datetime | None = None
    state_origin: datetime | None = None
    directional_state: LayerState = dfield(default_factory=LayerState)
    extension_state: LayerState = dfield(default_factory=LayerState)
    structural_state: LayerState = dfield(default_factory=LayerState)
    risk_state: LayerState = dfield(default_factory=LayerState)
    chase_risk_state: LayerState = dfield(default_factory=LayerState)
    snapshot_status: str = "NO_EVIDENCE"
    evidence_ids: list[str] = dfield(default_factory=list)
    source_snapshot_ids: list[str] = dfield(default_factory=list)
    context_asof_status: str = "LEGACY_TEMPORAL_UNVERIFIED"
    evidence_asof_statuses: list[str] = dfield(default_factory=list)
    derived_asof_status: str = "LEGACY_TEMPORAL_UNVERIFIED"
    state_schema_version: str = V2_STATE_MACHINE_SCHEMA_VERSION
    created_at: str = ""

    def __post_init__(self):
        if self.snapshot_status not in SNAPSHOT_STATUSES:
            raise ValueError(f"unknown snapshot_status: {self.snapshot_status!r}")

    def layers(self) -> dict[str, LayerState]:
        return {
            "DIRECTIONAL": self.directional_state,
            "EXTENSION": self.extension_state,
            "STRUCTURAL": self.structural_state,
            "RISK": self.risk_state,
            "CHASE_RISK": self.chase_risk_state,
        }

    def model_dump(self) -> dict:
        return asdict(self)


# ── StateTransitionRecord (§24) ──
@dataclass
class StateTransitionRecord:
    transition_id: str = ""
    instrument: str = ""
    target_family: str = ""
    instrument_role: str = "DIRECT"
    calendar_id: str = ""
    frequency: str = "DAILY"
    horizon: str = "1d"
    previous_snapshot_id: str = ""
    new_snapshot_id: str = ""
    transition_timestamp: datetime | None = None
    changed_layers: list[str] = dfield(default_factory=list)
    previous_directional_state: LayerState = dfield(default_factory=LayerState)
    new_directional_state: LayerState = dfield(default_factory=LayerState)
    previous_extension_state: LayerState = dfield(default_factory=LayerState)
    new_extension_state: LayerState = dfield(default_factory=LayerState)
    previous_structural_state: LayerState = dfield(default_factory=LayerState)
    new_structural_state: LayerState = dfield(default_factory=LayerState)
    previous_risk_state: LayerState = dfield(default_factory=LayerState)
    new_risk_state: LayerState = dfield(default_factory=LayerState)
    previous_chase_risk_state: LayerState = dfield(default_factory=LayerState)
    new_chase_risk_state: LayerState = dfield(default_factory=LayerState)
    trigger_evidence_ids: list[str] = dfield(default_factory=list)
    source_snapshot_ids: list[str] = dfield(default_factory=list)
    probability_before: float | None = None
    probability_after: float | None = None
    probability_status: str = "NOT_AVAILABLE"
    invalidation_status: str = "NONE"
    schema_version: str = V2_STATE_MACHINE_SCHEMA_VERSION

    def model_dump(self) -> dict:
        return asdict(self)


# ── StatePersistencePolicy (§30) — no hidden defaults ──
@dataclass
class StatePersistencePolicy:
    version: str = "2D.1"
    status: str = "NOT_CONFIGURED"
    validation_status: str = "HYPOTHESIS_ONLY"
    minimum_dwell_time_seconds: float | None = None
    entry_threshold: float | None = None
    exit_threshold: float | None = None
    confirmation_count: int | None = None
    hysteresis: bool | None = None

    def model_dump(self) -> dict:
        return asdict(self)


# ── helpers ──
def _identity_match(ev: StateEvidence, ctx: StateEvaluationContext) -> list[str]:
    reasons = []
    if normalize_instrument(ev.instrument) != normalize_instrument(ctx.instrument):
        reasons.append("INSTRUMENT_MISMATCH")
    if normalize_family(ev.target_family) != normalize_family(ctx.target_family):
        reasons.append("TARGET_FAMILY_MISMATCH")
    if ev.instrument_role != ctx.instrument_role:
        reasons.append("INSTRUMENT_ROLE_MISMATCH")
    if ev.calendar_id != ctx.calendar_id:
        reasons.append("CALENDAR_MISMATCH")
    if ev.frequency != ctx.frequency:
        reasons.append("FREQUENCY_MISMATCH")
    if ev.horizon != ctx.horizon:
        reasons.append("HORIZON_MISMATCH")
    return reasons


def validate_state_evidence(ev: StateEvidence, ctx: StateEvaluationContext) -> list[str]:
    """Return blocker reason codes (empty = valid+eligible to compose)."""
    reasons = list(_identity_match(ev, ctx))
    if reasons:
        return [BLOCKED_IDENTITY_MISMATCH]
    cutoff = ctx.feature_cutoff_timestamp
    if cutoff is not None:
        if ev.available_at is not None and ensure_utc_aware(ev.available_at) > ensure_utc_aware(cutoff):
            return [BLOCKED_FUTURE_EVIDENCE]
        if ev.event_timestamp is not None and ensure_utc_aware(ev.event_timestamp) > ensure_utc_aware(cutoff):
            return [BLOCKED_FUTURE_EVIDENCE]
    if ev.source_type == SOURCE_V2C_OUTCOME:
        if ev.settled_at is None or (cutoff is not None and ensure_utc_aware(ev.settled_at) > ensure_utc_aware(cutoff)):
            return [BLOCKED_FUTURE_OUTCOME_EVIDENCE]
        if not (ev.source_forecast_origin and ev.label_schema_version):
            return [BLOCKED_FUTURE_OUTCOME_EVIDENCE]
    return []


def snapshot_identity(ctx: StateEvaluationContext, layers: dict[str, LayerState],
                      evidence_ids: list[str]) -> str:
    parts = [
        normalize_instrument(ctx.instrument), normalize_family(ctx.target_family),
        ctx.instrument_role, ctx.calendar_id, ctx.frequency, ctx.horizon,
        ensure_utc_aware(ctx.feature_cutoff_timestamp).isoformat() if ctx.feature_cutoff_timestamp else "",
        ensure_utc_aware(ctx.state_origin).isoformat() if ctx.state_origin else "",
        V2_STATE_MACHINE_SCHEMA_VERSION,
        "|".join(sorted(evidence_ids)),
    ]
    for layer in LAYERS:
        s = layers[layer]
        parts.append(f"{layer}:{s.value}:{s.status}")
    return sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


def transition_identity(prev_id: str, new_id: str) -> str:
    return sha256(f"{prev_id}|{new_id}".encode("utf-8")).hexdigest()[:16]


# ── composition (§18/§19) ──
def compose_state_snapshot(ctx: StateEvaluationContext,
                           evidence: list[StateEvidence]) -> StateSnapshot:
    """Deterministic evidence composition. No model / ATR / probability / LLM / future query."""
    # context time contract
    if ctx.validate_ordering() or ctx.feature_cutoff_timestamp is None or ctx.state_origin is None:
        return _blocked_snapshot(ctx, BLOCKED_TEMPORAL_CONTRACT)

    layers: dict[str, LayerState] = {l: LayerState(status="NOT_EVALUATED") for l in LAYERS}

    # validate + dedupe evidence
    seen: dict[str, StateEvidence] = {}
    for ev in evidence:
        if ev.evidence_id in seen:
            if asdict(seen[ev.evidence_id]) != asdict(ev):
                return _blocked_snapshot(ctx, BLOCKED_EVIDENCE_ID_COLLISION)
            continue  # exact duplicate → deterministic de-duplicate
        seen[ev.evidence_id] = ev
        reasons = validate_state_evidence(ev, ctx)
        if reasons:
            return _blocked_snapshot(ctx, reasons[0])
    eligible = list(seen.values())

    # group by layer
    by_layer: dict[str, list[StateEvidence]] = {l: [] for l in LAYERS}
    for ev in eligible:
        by_layer[ev.layer].append(ev)

    # per-layer composition
    for layer in LAYERS:
        evs = by_layer[layer]
        layers[layer] = _compose_layer(layer, evs)

    # snapshot status
    statuses = [layers[l].status for l in LAYERS]
    if all(s == "NOT_EVALUATED" for s in statuses):
        snap_status = "NO_EVIDENCE"
    elif all(s == "EVALUATED" for s in statuses):
        snap_status = "COMPOSED_COMPLETE"
    else:
        snap_status = "COMPOSED_PARTIAL"

    evidence_ids = sorted([ev.evidence_id for ev in eligible])
    source_snapshot_ids = sorted({sid for ev in eligible for sid in ev.source_snapshot_ids})
    derived_asof = _least_verified_asof([ctx.asof_status] + [ev.asof_status for ev in eligible])

    snap = StateSnapshot(
        snapshot_id=snapshot_identity(ctx, layers, evidence_ids),
        instrument=ctx.instrument, target_family=ctx.target_family,
        instrument_role=ctx.instrument_role, calendar_id=ctx.calendar_id,
        frequency=ctx.frequency, horizon=ctx.horizon,
        feature_cutoff_timestamp=ctx.feature_cutoff_timestamp, state_origin=ctx.state_origin,
        directional_state=layers["DIRECTIONAL"], extension_state=layers["EXTENSION"],
        structural_state=layers["STRUCTURAL"], risk_state=layers["RISK"],
        chase_risk_state=layers["CHASE_RISK"], snapshot_status=snap_status,
        evidence_ids=evidence_ids, source_snapshot_ids=source_snapshot_ids,
        context_asof_status=ctx.asof_status,
        evidence_asof_statuses=[ev.asof_status for ev in eligible],
        derived_asof_status=derived_asof,
        created_at=datetime.now().astimezone().isoformat(),
    )
    return snap


def _compose_layer(layer: str, evs: list[StateEvidence]) -> LayerState:
    if not evs:
        return LayerState(status="NOT_EVALUATED")
    trusted = [ev for ev in evs if ev.provenance_status in _TRUSTED]
    if not trusted:
        # only UNKNOWN provenance → UNVERIFIED, no published value
        return LayerState(value=None, status="UNVERIFIED",
                          evidence_ids=[ev.evidence_id for ev in evs],
                          source_snapshot_ids=sorted({sid for ev in evs for sid in ev.source_snapshot_ids}),
                          reason_codes=["UNVERIFIED_PROVENANCE"])
    values = {ev.value for ev in trusted}
    ids = [ev.evidence_id for ev in trusted]
    snaps = sorted({sid for ev in trusted for sid in ev.source_snapshot_ids})
    if len(values) == 1:
        return LayerState(value=next(iter(values)), status="EVALUATED", evidence_ids=ids,
                          source_snapshot_ids=snaps)
    return LayerState(value=None, status="CONFLICT", evidence_ids=ids,
                      source_snapshot_ids=snaps, reason_codes=sorted(values))


def _blocked_snapshot(ctx: StateEvaluationContext, reason: str) -> StateSnapshot:
    blocked = LayerState(value=None, status="BLOCKED", reason_codes=[reason])
    return StateSnapshot(
        instrument=ctx.instrument, target_family=ctx.target_family,
        instrument_role=ctx.instrument_role, calendar_id=ctx.calendar_id,
        frequency=ctx.frequency, horizon=ctx.horizon,
        feature_cutoff_timestamp=ctx.feature_cutoff_timestamp, state_origin=ctx.state_origin,
        directional_state=blocked, extension_state=blocked, structural_state=blocked,
        risk_state=blocked, chase_risk_state=blocked, snapshot_status="BLOCKED",
        context_asof_status=ctx.asof_status,
        derived_asof_status=_least_verified_asof([ctx.asof_status]),
    )


# ── transition (§24/§26/§27) ──
def transition(previous: StateSnapshot | None,
               current: StateSnapshot,
               trigger_evidence_ids: list[str] | None = None) -> StateTransitionRecord:
    """Deterministic transition. No probability. Monotonic time. Cross-identity/time rejected."""
    if previous is not None:
        # identity must match
        if (normalize_instrument(previous.instrument) != normalize_instrument(current.instrument)
                or normalize_family(previous.target_family) != normalize_family(current.target_family)
                or previous.instrument_role != current.instrument_role
                or previous.calendar_id != current.calendar_id
                or previous.frequency != current.frequency
                or previous.horizon != current.horizon):
            raise ValueError("cross-identity transition rejected")
        # monotonic time
        if current.state_origin is None or previous.state_origin is None or \
                ensure_utc_aware(current.state_origin) <= ensure_utc_aware(previous.state_origin):
            raise ValueError("backward/equal-time transition rejected")

    prev_layers = previous.layers() if previous is not None else {l: LayerState() for l in LAYERS}
    curr_layers = current.layers()

    changed = []
    for layer in LAYERS:
        pv, ps = prev_layers[layer].value, prev_layers[layer].status
        cv, cs = curr_layers[layer].value, curr_layers[layer].status
        if (pv, ps) != (cv, cs):
            changed.append(layer)

    return StateTransitionRecord(
        transition_id=transition_identity(previous.snapshot_id if previous else "", current.snapshot_id),
        instrument=current.instrument, target_family=current.target_family,
        instrument_role=current.instrument_role, calendar_id=current.calendar_id,
        frequency=current.frequency, horizon=current.horizon,
        previous_snapshot_id=previous.snapshot_id if previous else "",
        new_snapshot_id=current.snapshot_id,
        transition_timestamp=current.state_origin,
        changed_layers=changed,
        previous_directional_state=prev_layers["DIRECTIONAL"],
        new_directional_state=curr_layers["DIRECTIONAL"],
        previous_extension_state=prev_layers["EXTENSION"],
        new_extension_state=curr_layers["EXTENSION"],
        previous_structural_state=prev_layers["STRUCTURAL"],
        new_structural_state=curr_layers["STRUCTURAL"],
        previous_risk_state=prev_layers["RISK"],
        new_risk_state=curr_layers["RISK"],
        previous_chase_risk_state=prev_layers["CHASE_RISK"],
        new_chase_risk_state=curr_layers["CHASE_RISK"],
        trigger_evidence_ids=list(trigger_evidence_ids or []),
        source_snapshot_ids=current.source_snapshot_ids,
        probability_before=None, probability_after=None, probability_status="NOT_AVAILABLE",
        invalidation_status="NONE",
    )
