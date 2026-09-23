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

Evidence truth contract (2D.2):
- StateEvidence must carry non-empty evidence_id, legal non-null value, non-empty target identity,
  non-empty source identity, mandatory event_timestamp + available_at, and a known asof_status.
- Point-in-time: event_timestamp <= available_at <= feature_cutoff_timestamp <= state_origin.
- V2-C Touch/Break/Acceptance are forecast-outcome labels and MUST NOT leak into forecast state.
- Canonical stored timestamps are tz-aware UTC; set-like outputs are canonical sorted.
No extension/exhaustion evaluator, no probability, no trading semantics, no persistence DB.

Schema: V2_STATE_MACHINE_SCHEMA_VERSION = "2D.4"  (independent from 2A.1 / 2B.1 / 2C.2 / 3A.2.3)

2D.4 artifact-identity/transition-isolation hardening (V2-G prerequisite):
- StateSnapshot identity is content-addressed: same snapshot_id => same canonical semantic payload,
  including context_asof_status, evidence_asof_by_id/statuses, full LayerState attribution
  (evidence_ids / source_snapshot_ids / reason_codes), block/blocked lineage, and source lineage.
- Excluded from identity: snapshot_id itself and created_at (wall-clock runtime metadata).
- Blocked snapshots use the same content-consistent identity principle (no weaker ad-hoc hash).
- StateTransitionRecord deep-copies every previous/new LayerState so a later mutation of the source
  snapshot cannot silently rewrite an already-produced transition artifact.
"""
from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field as dfield, asdict
from datetime import datetime, timezone, date as date_cls
from hashlib import sha256
from typing import Any

from market_ai_hub.research.v2.asof import normalize_instrument, normalize_family, ensure_utc_aware
from market_ai_hub.research.v2.labels import V2_DAILY_LABEL_SCHEMA_VERSION

V2_STATE_MACHINE_SCHEMA_VERSION = "2D.4"

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
SUPPORTED_EVALUATION_MODES = ("RESEARCH",)
ASOF_STATUSES = ("ASOF_VERIFIED", "TEMPORAL_UNVERIFIED", "LEGACY_TEMPORAL_UNVERIFIED")

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
BLOCKED_TEMPORAL_EVIDENCE_PROVENANCE = "BLOCKED_TEMPORAL_EVIDENCE_PROVENANCE"
BLOCKED_CONTEXT_CONTRACT = "BLOCKED_CONTEXT_CONTRACT"
BLOCKED_SOURCE_PROVENANCE = "BLOCKED_SOURCE_PROVENANCE"
BLOCKED_INVALID_SNAPSHOT_TRANSITION = "BLOCKED_INVALID_SNAPSHOT_TRANSITION"

# ASOF conservativeness rank (higher = more verified); summary takes least-verified
_ASOF_RANK = {"ASOF_VERIFIED": 2, "TEMPORAL_UNVERIFIED": 1, "LEGACY_TEMPORAL_UNVERIFIED": 0}


def _least_verified_asof(statuses: list[str]) -> str:
    if not statuses:
        return "LEGACY_TEMPORAL_UNVERIFIED"
    return min(statuses, key=lambda s: _ASOF_RANK[s])


def _require_nonempty(name: str, value: Any) -> None:
    if value is None or (isinstance(value, str) and not value.strip()):
        raise ValueError(f"{name} must be non-empty")


def _canonical(xs: list[str]) -> list[str]:
    return sorted({x for x in xs if x})


_ISO_DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _valid_iso_date(s: str) -> bool:
    if not isinstance(s, str) or not _ISO_DATE_RE.fullmatch(s):
        return False
    try:
        date_cls.fromisoformat(s)
        return True
    except ValueError:
        return False


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


# ── StateEvaluationContext (§8/§20) ──
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
        if self.evaluation_mode not in SUPPORTED_EVALUATION_MODES:
            raise ValueError(f"unsupported evaluation_mode: {self.evaluation_mode!r}")
        if self.asof_status not in ASOF_STATUSES:
            raise ValueError(f"unknown asof_status: {self.asof_status!r}")
        for name in ("feature_cutoff_timestamp", "state_origin"):
            v = getattr(self, name)
            if v is None or v.tzinfo is None:
                raise ValueError(f"{name} must be tz-aware and non-null")
        # canonical identity (§18/§19)
        self.instrument = normalize_instrument(self.instrument)
        self.target_family = normalize_family(self.target_family)
        # canonical UTC
        self.feature_cutoff_timestamp = ensure_utc_aware(self.feature_cutoff_timestamp)
        self.state_origin = ensure_utc_aware(self.state_origin)

    def validate_contract(self) -> list[str]:
        reasons = []
        for name in ("instrument", "target_family", "instrument_role", "calendar_id", "horizon"):
            if not getattr(self, name) or not str(getattr(self, name)).strip():
                reasons.append(f"EMPTY_{name.upper()}")
        if self.feature_cutoff_timestamp and self.state_origin \
                and self.feature_cutoff_timestamp > self.state_origin:
            reasons.append("CUTOFF_AFTER_ORIGIN")
        return reasons

    def model_dump(self) -> dict:
        return asdict(self)


# ── StateEvidence (§9/§12/§21/§28) ──
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
    source_forecast_origin: datetime | None = None
    outcome_window_start: str = ""
    outcome_window_end: str = ""
    outcome_first_event_session: str = ""
    settled_at: datetime | None = None
    label_schema_version: str = ""
    notes: str = ""

    def __post_init__(self):
        _require_nonempty("evidence_id", self.evidence_id)
        if self.layer not in LAYERS:
            raise ValueError(f"unknown layer: {self.layer!r}")
        if self.value is None:
            raise ValueError(f"StateEvidence.value must be a legal non-null domain value (got None)")
        if self.value not in _LAYER_VALUES[self.layer]:
            raise ValueError(f"value {self.value!r} invalid for layer {self.layer!r}")
        if self.frequency not in SUPPORTED_FREQUENCIES:
            raise ValueError(f"unsupported frequency: {self.frequency!r}")
        if self.provenance_status not in PROVENANCE_STATUS:
            raise ValueError(f"unknown provenance_status: {self.provenance_status!r}")
        if self.asof_status not in ASOF_STATUSES:
            raise ValueError(f"unknown asof_status: {self.asof_status!r}")
        # canonical identity (§18/§19)
        self.instrument = normalize_instrument(self.instrument)
        self.target_family = normalize_family(self.target_family)
        # canonical UTC for any provided timestamp
        for name in ("event_timestamp", "available_at", "source_forecast_origin", "settled_at"):
            v = getattr(self, name)
            if v is not None:
                if v.tzinfo is None:
                    raise ValueError(f"{name} must be tz-aware")
                setattr(self, name, ensure_utc_aware(v))

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
    context_source_snapshot_ids: list[str] = dfield(default_factory=list)
    evidence_source_snapshot_ids: list[str] = dfield(default_factory=list)
    source_snapshot_ids: list[str] = dfield(default_factory=list)
    block_reason_codes: list[str] = dfield(default_factory=list)
    blocked_evidence_ids: list[str] = dfield(default_factory=list)
    offending_evidence_fingerprint: str = ""
    context_asof_status: str = "LEGACY_TEMPORAL_UNVERIFIED"
    evidence_asof_statuses: list[str] = dfield(default_factory=list)
    evidence_asof_by_id: dict[str, str] = dfield(default_factory=dict)
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

    def semantic_dump(self) -> dict:
        """Deterministic dump excluding runtime metadata (created_at)."""
        d = asdict(self)
        d.pop("created_at", None)
        return d

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

    def semantic_dump(self) -> dict:
        return asdict(self)

    def model_dump(self) -> dict:
        return asdict(self)


# ── StatePersistencePolicy (§30) — no hidden defaults ──
@dataclass
class StatePersistencePolicy:
    version: str = "2D.4"
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
    # identity must be non-empty AND match
    for name in ("instrument", "target_family", "instrument_role", "calendar_id", "horizon"):
        if not getattr(ev, name) or not str(getattr(ev, name)).strip():
            return [BLOCKED_IDENTITY_MISMATCH]
    if _identity_match(ev, ctx):
        return [BLOCKED_IDENTITY_MISMATCH]
    # source identity mandatory
    for name in ("source_type", "source_schema_version", "source_version"):
        if not getattr(ev, name) or not str(getattr(ev, name)).strip():
            return [BLOCKED_SOURCE_PROVENANCE]
    # temporal completeness mandatory
    if ev.event_timestamp is None or ev.available_at is None:
        return [BLOCKED_TEMPORAL_EVIDENCE_PROVENANCE]
    # temporal ordering: event <= available (impossible provenance ordering otherwise)
    if ensure_utc_aware(ev.event_timestamp) > ensure_utc_aware(ev.available_at):
        return [BLOCKED_TEMPORAL_EVIDENCE_PROVENANCE]
    cutoff = ctx.feature_cutoff_timestamp
    if cutoff is not None:
        if ensure_utc_aware(ev.available_at) > ensure_utc_aware(cutoff):
            return [BLOCKED_FUTURE_EVIDENCE]
        if ensure_utc_aware(ev.event_timestamp) > ensure_utc_aware(cutoff):
            return [BLOCKED_FUTURE_EVIDENCE]
    # V2-C outcome provenance
    if ev.source_type == SOURCE_V2C_OUTCOME:
        if ev.settled_at is None or (cutoff is not None and ensure_utc_aware(ev.settled_at) > ensure_utc_aware(cutoff)):
            return [BLOCKED_FUTURE_OUTCOME_EVIDENCE]
        if not (ev.source_forecast_origin and ev.outcome_window_start and ev.outcome_window_end
                and ev.outcome_first_event_session and ev.label_schema_version):
            return [BLOCKED_FUTURE_OUTCOME_EVIDENCE]
        if ev.label_schema_version != V2_DAILY_LABEL_SCHEMA_VERSION:
            return [BLOCKED_FUTURE_OUTCOME_EVIDENCE]
        # strict ISO dates
        for name in ("outcome_window_start", "outcome_first_event_session", "outcome_window_end"):
            if not _valid_iso_date(getattr(ev, name)):
                return [BLOCKED_FUTURE_OUTCOME_EVIDENCE]
        ws = date_cls.fromisoformat(ev.outcome_window_start)
        fe = date_cls.fromisoformat(ev.outcome_first_event_session)
        we = date_cls.fromisoformat(ev.outcome_window_end)
        if not (ws <= fe <= we):
            return [BLOCKED_FUTURE_OUTCOME_EVIDENCE]
        if ensure_utc_aware(ev.source_forecast_origin) > ensure_utc_aware(ev.event_timestamp):
            return [BLOCKED_FUTURE_OUTCOME_EVIDENCE]
        if ensure_utc_aware(ev.event_timestamp) > ensure_utc_aware(ev.settled_at):
            return [BLOCKED_FUTURE_OUTCOME_EVIDENCE]
    return []


def _hash_payload(payload: dict) -> str:
    return sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()[:16]


def _layer_semantic(l: LayerState) -> dict:
    return {
        "value": l.value,
        "status": l.status,
        "evidence_ids": _canonical(l.evidence_ids),
        "source_snapshot_ids": _canonical(l.source_snapshot_ids),
        "reason_codes": _canonical(l.reason_codes),
    }


def _snapshot_semantic_payload(s: StateSnapshot) -> dict:
    """Canonical identity payload: every semantic field except snapshot_id and created_at."""
    return {
        "instrument": normalize_instrument(s.instrument),
        "target_family": normalize_family(s.target_family),
        "instrument_role": s.instrument_role,
        "calendar_id": s.calendar_id,
        "frequency": s.frequency,
        "horizon": s.horizon,
        "feature_cutoff_timestamp": ensure_utc_aware(s.feature_cutoff_timestamp).isoformat()
        if s.feature_cutoff_timestamp else "",
        "state_origin": ensure_utc_aware(s.state_origin).isoformat() if s.state_origin else "",
        "directional_state": _layer_semantic(s.directional_state),
        "extension_state": _layer_semantic(s.extension_state),
        "structural_state": _layer_semantic(s.structural_state),
        "risk_state": _layer_semantic(s.risk_state),
        "chase_risk_state": _layer_semantic(s.chase_risk_state),
        "snapshot_status": s.snapshot_status,
        "evidence_ids": _canonical(s.evidence_ids),
        "context_source_snapshot_ids": _canonical(s.context_source_snapshot_ids),
        "evidence_source_snapshot_ids": _canonical(s.evidence_source_snapshot_ids),
        "source_snapshot_ids": _canonical(s.source_snapshot_ids),
        "block_reason_codes": _canonical(s.block_reason_codes),
        "blocked_evidence_ids": _canonical(s.blocked_evidence_ids),
        "offending_evidence_fingerprint": s.offending_evidence_fingerprint,
        "context_asof_status": s.context_asof_status,
        "evidence_asof_statuses": _canonical(s.evidence_asof_statuses),
        "evidence_asof_by_id": {k: s.evidence_asof_by_id[k] for k in sorted(s.evidence_asof_by_id)},
        "derived_asof_status": s.derived_asof_status,
        "state_schema_version": s.state_schema_version,
    }


def snapshot_identity(snap: StateSnapshot) -> str:
    """Content-addressed snapshot id: same id => same canonical semantic artifact."""
    return _hash_payload(_snapshot_semantic_payload(snap))


def transition_identity(prev_id: str, new_id: str, trigger_ids: list[str]) -> str:
    parts = [prev_id, new_id, "|".join(_canonical(trigger_ids)), V2_STATE_MACHINE_SCHEMA_VERSION]
    return sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


# ── composition (§18/§19) ──
def compose_state_snapshot(ctx: StateEvaluationContext,
                           evidence: list[StateEvidence]) -> StateSnapshot:
    """Deterministic evidence composition. No model / ATR / probability / LLM / future query."""
    # context contract
    if ctx.validate_contract():
        return _blocked_snapshot(ctx, BLOCKED_CONTEXT_CONTRACT)

    layers: dict[str, LayerState] = {l: LayerState(status="NOT_EVALUATED") for l in LAYERS}

    seen: dict[str, StateEvidence] = {}
    for ev in evidence:
        if ev.evidence_id in seen:
            if asdict(seen[ev.evidence_id]) != asdict(ev):
                return _blocked_snapshot(ctx, BLOCKED_EVIDENCE_ID_COLLISION, ev)
            continue
        seen[ev.evidence_id] = ev
        reasons = validate_state_evidence(ev, ctx)
        if reasons:
            return _blocked_snapshot(ctx, reasons[0], ev)
    eligible = list(seen.values())

    by_layer: dict[str, list[StateEvidence]] = {l: [] for l in LAYERS}
    for ev in eligible:
        by_layer[ev.layer].append(ev)

    for layer in LAYERS:
        layers[layer] = _compose_layer(layer, by_layer[layer])

    statuses = [layers[l].status for l in LAYERS]
    if all(s == "NOT_EVALUATED" for s in statuses):
        snap_status = "NO_EVIDENCE"
    elif all(s == "EVALUATED" for s in statuses):
        snap_status = "COMPOSED_COMPLETE"
    else:
        snap_status = "COMPOSED_PARTIAL"

    evidence_ids = _canonical([ev.evidence_id for ev in eligible])
    context_snaps = _canonical(ctx.source_snapshot_ids)
    evidence_snaps = _canonical([sid for ev in eligible for sid in ev.source_snapshot_ids])
    union_snaps = _canonical(context_snaps + evidence_snaps)
    derived_asof = _least_verified_asof([ctx.asof_status] + [ev.asof_status for ev in eligible])
    evidence_asof_by_id = {ev.evidence_id: ev.asof_status for ev in sorted(eligible, key=lambda e: e.evidence_id)}

    snap = StateSnapshot(
        snapshot_id="",
        instrument=ctx.instrument, target_family=ctx.target_family,
        instrument_role=ctx.instrument_role, calendar_id=ctx.calendar_id,
        frequency=ctx.frequency, horizon=ctx.horizon,
        feature_cutoff_timestamp=ctx.feature_cutoff_timestamp, state_origin=ctx.state_origin,
        directional_state=layers["DIRECTIONAL"], extension_state=layers["EXTENSION"],
        structural_state=layers["STRUCTURAL"], risk_state=layers["RISK"],
        chase_risk_state=layers["CHASE_RISK"], snapshot_status=snap_status,
        evidence_ids=evidence_ids, context_source_snapshot_ids=context_snaps,
        evidence_source_snapshot_ids=evidence_snaps, source_snapshot_ids=union_snaps,
        context_asof_status=ctx.asof_status,
        evidence_asof_statuses=[evidence_asof_by_id[k] for k in sorted(evidence_asof_by_id)],
        evidence_asof_by_id=evidence_asof_by_id,
        derived_asof_status=derived_asof,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    snap.snapshot_id = snapshot_identity(snap)
    return snap


def _compose_layer(layer: str, evs: list[StateEvidence]) -> LayerState:
    if not evs:
        return LayerState(status="NOT_EVALUATED")
    trusted = [ev for ev in evs if ev.provenance_status in _TRUSTED]
    if not trusted:
        ids = _canonical([ev.evidence_id for ev in evs])
        snaps = _canonical([sid for ev in evs for sid in ev.source_snapshot_ids])
        return LayerState(value=None, status="UNVERIFIED", evidence_ids=ids,
                          source_snapshot_ids=snaps, reason_codes=["UNVERIFIED_PROVENANCE"])
    values = {ev.value for ev in trusted}
    ids = _canonical([ev.evidence_id for ev in trusted])
    snaps = _canonical([sid for ev in trusted for sid in ev.source_snapshot_ids])
    if len(values) == 1:
        return LayerState(value=next(iter(values)), status="EVALUATED", evidence_ids=ids,
                          source_snapshot_ids=snaps)
    return LayerState(value=None, status="CONFLICT", evidence_ids=ids,
                      source_snapshot_ids=snaps, reason_codes=sorted(values))


def _blocked_snapshot(ctx: StateEvaluationContext, reason: str,
                      offending: StateEvidence | None = None) -> StateSnapshot:
    def blocked_layer() -> LayerState:
        return LayerState(value=None, status="BLOCKED", reason_codes=[reason])
    offending_ids = _canonical([offending.evidence_id]) if offending else []
    offending_snaps = _canonical([sid for sid in offending.source_snapshot_ids]) if offending else []
    offending_fp = ""
    if offending is not None:
        d = asdict(offending)
        d.pop("notes", None)
        d["source_snapshot_ids"] = _canonical(offending.source_snapshot_ids)
        offending_fp = sha256(
            "|".join(f"{k}={v}" for k, v in sorted(d.items(), key=lambda x: x[0])).encode("utf-8")
        ).hexdigest()[:16]
    context_snaps = _canonical(ctx.source_snapshot_ids)
    union_snaps = _canonical(context_snaps + offending_snaps)
    derived = _least_verified_asof(
        [ctx.asof_status] + ([offending.asof_status] if offending else []))
    snap = StateSnapshot(
        snapshot_id="",
        instrument=ctx.instrument, target_family=ctx.target_family,
        instrument_role=ctx.instrument_role, calendar_id=ctx.calendar_id,
        frequency=ctx.frequency, horizon=ctx.horizon,
        feature_cutoff_timestamp=ctx.feature_cutoff_timestamp, state_origin=ctx.state_origin,
        directional_state=blocked_layer(), extension_state=blocked_layer(),
        structural_state=blocked_layer(), risk_state=blocked_layer(),
        chase_risk_state=blocked_layer(), snapshot_status="BLOCKED",
        context_source_snapshot_ids=context_snaps,
        evidence_source_snapshot_ids=offending_snaps,
        source_snapshot_ids=union_snaps,
        block_reason_codes=[reason],
        blocked_evidence_ids=offending_ids,
        offending_evidence_fingerprint=offending_fp,
        context_asof_status=ctx.asof_status,
        derived_asof_status=derived,
    )
    snap.snapshot_id = snapshot_identity(snap)
    return snap


# ── transition (§24/§26/§27/§17/§18/§19) ──
def transition(previous: StateSnapshot | None,
               current: StateSnapshot,
               trigger_evidence_ids: list[str] | None = None) -> StateTransitionRecord:
    """Deterministic transition. No probability. Monotonic time. Blocked snapshots rejected."""
    if current.snapshot_status == "BLOCKED" or (previous is not None and previous.snapshot_status == "BLOCKED"):
        raise ValueError(BLOCKED_INVALID_SNAPSHOT_TRANSITION)

    if previous is not None:
        if (normalize_instrument(previous.instrument) != normalize_instrument(current.instrument)
                or normalize_family(previous.target_family) != normalize_family(current.target_family)
                or previous.instrument_role != current.instrument_role
                or previous.calendar_id != current.calendar_id
                or previous.frequency != current.frequency
                or previous.horizon != current.horizon):
            raise ValueError("cross-identity transition rejected")
        if current.state_origin is None or previous.state_origin is None or \
                ensure_utc_aware(current.state_origin) <= ensure_utc_aware(previous.state_origin):
            raise ValueError("backward/equal-time transition rejected")

    # trigger lineage validation (§18): provided triggers ⊆ current evidence
    triggers = _canonical(list(trigger_evidence_ids or []))
    if triggers:
        current_ids = set(current.evidence_ids)
        if not set(triggers).issubset(current_ids):
            raise ValueError("trigger_evidence_ids must be a subset of current.evidence_ids")

    prev_layers = previous.layers() if previous is not None else {l: LayerState() for l in LAYERS}
    curr_layers = current.layers()

    changed = []
    for layer in LAYERS:
        pv, ps = prev_layers[layer].value, prev_layers[layer].status
        cv, cs = curr_layers[layer].value, curr_layers[layer].status
        if (pv, ps) != (cv, cs):
            changed.append(layer)

    src_union = _canonical(
        (previous.source_snapshot_ids if previous else []) + current.source_snapshot_ids)

    return StateTransitionRecord(
        transition_id=transition_identity(previous.snapshot_id if previous else "", current.snapshot_id, triggers),
        instrument=current.instrument, target_family=current.target_family,
        instrument_role=current.instrument_role, calendar_id=current.calendar_id,
        frequency=current.frequency, horizon=current.horizon,
        previous_snapshot_id=previous.snapshot_id if previous else "",
        new_snapshot_id=current.snapshot_id,
        transition_timestamp=current.state_origin,
        changed_layers=changed,
        previous_directional_state=copy.deepcopy(prev_layers["DIRECTIONAL"]),
        new_directional_state=copy.deepcopy(curr_layers["DIRECTIONAL"]),
        previous_extension_state=copy.deepcopy(prev_layers["EXTENSION"]),
        new_extension_state=copy.deepcopy(curr_layers["EXTENSION"]),
        previous_structural_state=copy.deepcopy(prev_layers["STRUCTURAL"]),
        new_structural_state=copy.deepcopy(curr_layers["STRUCTURAL"]),
        previous_risk_state=copy.deepcopy(prev_layers["RISK"]),
        new_risk_state=copy.deepcopy(curr_layers["RISK"]),
        previous_chase_risk_state=copy.deepcopy(prev_layers["CHASE_RISK"]),
        new_chase_risk_state=copy.deepcopy(curr_layers["CHASE_RISK"]),
        trigger_evidence_ids=triggers,
        source_snapshot_ids=src_union,
        probability_before=None, probability_after=None, probability_status="NOT_AVAILABLE",
        invalidation_status="NONE",
    )
