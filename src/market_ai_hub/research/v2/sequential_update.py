"""V2-G — Sequential State Updating Scaffold (descriptive, non-probabilistic).

RESEARCH ONLY. Consumes V2-D (2D.4) StateSnapshot / StateTransitionRecord artifacts and produces a
deterministic descriptive state sequence: revision descriptors (state vs attribution), dwell/run
descriptors, evidence/source deltas, and a strict continuity/integrity contract.

This is the CORE_V2 "Sequential Updating" scaffold only. Change-point algorithms (CUSUM /
Page-Hinkley / BOCPD) and state-transition probability are RESEARCH_CHALLENGER and are NOT
implemented here. There is no calibrated probability yet (V2-I), so probability level/velocity/
acceleration remain unavailable typed placeholders.

Machine-enforced principles:
- SEQUENTIAL OBSERVATION != PREDICTION
- STATE CHANGE != CHANGE POINT
- CATEGORICAL STATE CHANGE != NUMERIC VELOCITY
- DWELL DURATION != PERSISTENCE VALIDATION
- RUN LENGTH != CONFIRMATION POLICY
- PROBABILITY VELOCITY != STATE ORDINAL CHANGE
- CHASE STOP != SHORT

No persistence DB (V2-H), no calibration (V2-I), no trading. All state categories are categorical:
no ordinal arithmetic (STRONG_BEAR=-2 … STRONG_BULL=+2) is performed.

Schema: V2_SEQUENTIAL_UPDATE_SCHEMA_VERSION = "2G.2"  (independent of 2A.1/2B.1/2C.2/2D.4/2E.3/2F.3/3A.2.3)

2G.2 blocked-artifact audit-lineage closure:
- BLOCKED artifacts retain the full candidate/input audit lineage (declared vs recomputed identity,
  state stream, ASOF, source lineage) instead of only a hash + reason.
- sequence_identity(artifact) == artifact.sequence_id holds for BOTH SEQUENCE_AVAILABLE and BLOCKED
  (self-verifiable identity); only the empty NOT_AVAILABLE sequence keeps sequence_id == "".
- append failure preserves the existing sequence declared/recomputed identity and new-input lineage.
"""
from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field as dfield, asdict
from datetime import datetime
from hashlib import sha256
from typing import Any

from market_ai_hub.research.v2.asof import normalize_instrument, normalize_family, ensure_utc_aware
from market_ai_hub.research.v2.state_machine import (
    StateSnapshot,
    StateTransitionRecord,
    LayerState,
    snapshot_identity,
    transition,
    V2_STATE_MACHINE_SCHEMA_VERSION,
    LAYERS,
    _least_verified_asof,
)

V2_SEQUENTIAL_UPDATE_SCHEMA_VERSION = "2G.2"

# ── capability registry (machine-readable) ──
V2G_CAPABILITIES = {
    "DETERMINISTIC_STATE_REVISION": "ENGINE_AVAILABLE",
    "RUN_LENGTH_DWELL_DESCRIPTOR": "ENGINE_AVAILABLE",
    "PROBABILITY_VELOCITY": "NOT_AVAILABLE_PENDING_CALIBRATED_PROBABILITY",
    "PROBABILITY_ACCELERATION": "NOT_AVAILABLE_PENDING_CALIBRATED_PROBABILITY",
    "CUSUM": "RESEARCH_CHALLENGER_NOT_IMPLEMENTED",
    "PAGE_HINKLEY": "RESEARCH_CHALLENGER_NOT_IMPLEMENTED",
    "BOCPD": "RESEARCH_CHALLENGER_NOT_IMPLEMENTED",
    "STATE_TRANSITION_PROBABILITY": "RESEARCH_CHALLENGER_NOT_IMPLEMENTED",
}

SEQUENCE_STATUSES = ("NOT_AVAILABLE", "SEQUENCE_AVAILABLE", "BLOCKED")
UPDATE_KINDS = ("STATE_CHANGE", "ATTRIBUTION_ONLY", "NO_LAYER_CHANGE")
TRANSITION_STATUSES = ("VERIFIED", "NOT_PROVIDED")

# ── blockers ──
BLOCKED_SNAPSHOT_INTEGRITY_MISMATCH = "BLOCKED_SNAPSHOT_INTEGRITY_MISMATCH"
BLOCKED_UNSUPPORTED_UPSTREAM_SCHEMA = "BLOCKED_UNSUPPORTED_UPSTREAM_SCHEMA"
BLOCKED_UPSTREAM_SNAPSHOT = "BLOCKED_UPSTREAM_SNAPSHOT"
BLOCKED_IDENTITY_MISMATCH = "BLOCKED_IDENTITY_MISMATCH"
BLOCKED_SNAPSHOT_ID_COLLISION = "BLOCKED_SNAPSHOT_ID_COLLISION"
BLOCKED_AMBIGUOUS_STATE_ORIGIN = "BLOCKED_AMBIGUOUS_STATE_ORIGIN"
BLOCKED_CUTOFF_REGRESSION = "BLOCKED_CUTOFF_REGRESSION"
BLOCKED_TRANSITION_INTEGRITY_MISMATCH = "BLOCKED_TRANSITION_INTEGRITY_MISMATCH"
BLOCKED_TRANSITION_ID_COLLISION = "BLOCKED_TRANSITION_ID_COLLISION"
BLOCKED_ORPHAN_TRANSITION = "BLOCKED_ORPHAN_TRANSITION"
BLOCKED_SEQUENCE_INTEGRITY_MISMATCH = "BLOCKED_SEQUENCE_INTEGRITY_MISMATCH"
BLOCKED_EXISTING_SEQUENCE_NOT_APPENDABLE = "BLOCKED_EXISTING_SEQUENCE_NOT_APPENDABLE"


def _canonical(xs: list[str]) -> list[str]:
    return sorted({x for x in xs if x})


def _dt_iso(x: datetime | None) -> str:
    return ensure_utc_aware(x).isoformat() if x else ""


def _id_fp(parts: list[str]) -> str:
    return sha256("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:16]


def _json_safe(obj: Any) -> Any:
    if isinstance(obj, datetime):
        return ensure_utc_aware(obj).isoformat()
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, set):
        return sorted(_json_safe(v) for v in obj)
    return obj


def _hash_payload(payload: dict) -> str:
    return sha256(
        json.dumps(_json_safe(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()[:16]


def _transition_key(t: StateTransitionRecord) -> str:
    return _hash_payload(asdict(t))


def _target_identity(s: StateSnapshot) -> tuple:
    return (normalize_instrument(s.instrument), normalize_family(s.target_family),
            s.instrument_role, s.calendar_id, s.frequency, s.horizon)


def _strip_created(s: StateSnapshot) -> StateSnapshot:
    c = copy.deepcopy(s)
    c.created_at = ""
    return c


# ── policy (frozen: canonical statuses are not caller-settable) ──
@dataclass(frozen=True)
class SequentialUpdatePolicy:
    version: str = "2G.2"
    mode: str = "DESCRIPTIVE_STATE_SEQUENCE"
    persistence_policy: str = "NOT_CONFIGURED"
    probability_status: str = "NOT_AVAILABLE_UPSTREAM_UNCALIBRATED"
    change_point_status: str = "RESEARCH_CHALLENGER_NOT_IMPLEMENTED"
    validation_status: str = "HYPOTHESIS_ONLY"

    def __post_init__(self):
        if self.version != "2G.2":
            raise ValueError("SequentialUpdatePolicy.version is frozen to 2G.2")
        if self.mode != "DESCRIPTIVE_STATE_SEQUENCE":
            raise ValueError("SequentialUpdatePolicy.mode is frozen to DESCRIPTIVE_STATE_SEQUENCE")
        if self.persistence_policy != "NOT_CONFIGURED":
            raise ValueError("SequentialUpdatePolicy.persistence_policy is frozen to NOT_CONFIGURED")
        if self.probability_status != "NOT_AVAILABLE_UPSTREAM_UNCALIBRATED":
            raise ValueError("probability_status is frozen to NOT_AVAILABLE_UPSTREAM_UNCALIBRATED")
        if self.change_point_status != "RESEARCH_CHALLENGER_NOT_IMPLEMENTED":
            raise ValueError("change_point_status is frozen to RESEARCH_CHALLENGER_NOT_IMPLEMENTED")
        if self.validation_status != "HYPOTHESIS_ONLY":
            raise ValueError("validation_status is frozen to HYPOTHESIS_ONLY")

    def model_dump(self) -> dict:
        return asdict(self)


# ── descriptor dataclasses ──
@dataclass
class LayerRevisionDescriptor:
    layer: str = ""
    state_changed: bool = False
    attribution_changed: bool = False

    def model_dump(self) -> dict:
        return asdict(self)


@dataclass
class LayerRunDescriptor:
    layer: str = ""
    value: str | None = None
    status: str = "NOT_EVALUATED"
    run_start_origin: datetime | None = None
    current_origin: datetime | None = None
    run_length_observations: int = 0
    run_elapsed_seconds: float | None = None

    def model_dump(self) -> dict:
        return asdict(self)


@dataclass
class StateSequenceStep:
    step_id: str = ""
    previous_snapshot_id: str = ""
    current_snapshot_id: str = ""
    previous_state_origin: datetime | None = None
    current_state_origin: datetime | None = None
    previous_feature_cutoff: datetime | None = None
    current_feature_cutoff: datetime | None = None
    elapsed_seconds: float | None = None
    cutoff_delta_seconds: float | None = None
    information_advanced: bool = False
    state_changed_layers: list[str] = dfield(default_factory=list)
    attribution_changed_layers: list[str] = dfield(default_factory=list)
    layer_revision_descriptors: list[LayerRevisionDescriptor] = dfield(default_factory=list)
    evidence_added_ids: list[str] = dfield(default_factory=list)
    evidence_removed_ids: list[str] = dfield(default_factory=list)
    source_snapshot_added_ids: list[str] = dfield(default_factory=list)
    source_snapshot_removed_ids: list[str] = dfield(default_factory=list)
    transition_id: str = ""
    transition_status: str = "NOT_PROVIDED"
    derived_asof_status: str = "LEGACY_TEMPORAL_UNVERIFIED"
    update_kind: str = "NO_LAYER_CHANGE"

    def model_dump(self) -> dict:
        return asdict(self)


# ── candidate audit entries (blocked-artifact lineage) ──
@dataclass
class SequenceCandidateSnapshotAudit:
    declared_snapshot_id: str = ""
    recomputed_snapshot_id: str = ""
    instrument: str = ""
    target_family: str = ""
    instrument_role: str = "DIRECT"
    calendar_id: str = ""
    frequency: str = "DAILY"
    horizon: str = "1d"
    feature_cutoff_timestamp: datetime | None = None
    state_origin: datetime | None = None
    state_schema_version: str = ""
    snapshot_status: str = ""
    source_snapshot_ids: list[str] = dfield(default_factory=list)
    derived_asof_status: str = ""

    def model_dump(self) -> dict:
        return asdict(self)


@dataclass
class SequenceCandidateTransitionAudit:
    declared_transition_id: str = ""
    recomputed_transition_fingerprint: str = ""
    previous_snapshot_id: str = ""
    new_snapshot_id: str = ""
    transition_timestamp: datetime | None = None
    schema_version: str = ""
    trigger_evidence_ids: list[str] = dfield(default_factory=list)
    source_snapshot_ids: list[str] = dfield(default_factory=list)

    def model_dump(self) -> dict:
        return asdict(self)


def _render_target_identity(instrument: str, target_family: str, instrument_role: str,
                            calendar_id: str, frequency: str, horizon: str) -> str:
    return "|".join([instrument, target_family, instrument_role, calendar_id, frequency, horizon])


def _render_state_stream(audit: "SequenceCandidateSnapshotAudit") -> str:
    return "|".join([audit.instrument, audit.target_family, audit.instrument_role, audit.calendar_id,
                     audit.frequency, audit.horizon, _dt_iso(audit.feature_cutoff_timestamp),
                     _dt_iso(audit.state_origin)])


def _snapshot_audit(s: StateSnapshot) -> SequenceCandidateSnapshotAudit:
    try:
        recomputed = snapshot_identity(s)
    except Exception:
        recomputed = ""
    return SequenceCandidateSnapshotAudit(
        declared_snapshot_id=s.snapshot_id, recomputed_snapshot_id=recomputed,
        instrument=normalize_instrument(s.instrument), target_family=normalize_family(s.target_family),
        instrument_role=s.instrument_role, calendar_id=s.calendar_id,
        frequency=s.frequency, horizon=s.horizon,
        feature_cutoff_timestamp=s.feature_cutoff_timestamp, state_origin=s.state_origin,
        state_schema_version=s.state_schema_version, snapshot_status=s.snapshot_status,
        source_snapshot_ids=_canonical(s.source_snapshot_ids), derived_asof_status=s.derived_asof_status,
    )


def _transition_audit(t: StateTransitionRecord) -> SequenceCandidateTransitionAudit:
    return SequenceCandidateTransitionAudit(
        declared_transition_id=t.transition_id, recomputed_transition_fingerprint=_transition_key(t),
        previous_snapshot_id=t.previous_snapshot_id, new_snapshot_id=t.new_snapshot_id,
        transition_timestamp=t.transition_timestamp, schema_version=t.schema_version,
        trigger_evidence_ids=_canonical(t.trigger_evidence_ids),
        source_snapshot_ids=_canonical(t.source_snapshot_ids),
    )


def _snapshot_audit_sort_key(x: SequenceCandidateSnapshotAudit):
    return (_dt_iso(x.state_origin), x.declared_snapshot_id, x.recomputed_snapshot_id)


def _transition_audit_sort_key(x: SequenceCandidateTransitionAudit):
    return (x.previous_snapshot_id, x.new_snapshot_id, x.declared_transition_id)


@dataclass
class StateSequenceArtifact:
    sequence_id: str = ""
    instrument: str = ""
    target_family: str = ""
    instrument_role: str = "DIRECT"
    calendar_id: str = ""
    frequency: str = "DAILY"
    horizon: str = "1d"
    first_state_origin: datetime | None = None
    last_state_origin: datetime | None = None
    first_feature_cutoff: datetime | None = None
    last_feature_cutoff: datetime | None = None
    snapshot_ids: list[str] = dfield(default_factory=list)
    transition_ids: list[str] = dfield(default_factory=list)
    steps: list[StateSequenceStep] = dfield(default_factory=list)
    layer_run_descriptors: list[LayerRunDescriptor] = dfield(default_factory=list)
    snapshots: list[StateSnapshot] = dfield(default_factory=list)
    transitions: list[StateTransitionRecord] = dfield(default_factory=list)
    snapshot_source_snapshot_ids: list[str] = dfield(default_factory=list)
    transition_source_snapshot_ids: list[str] = dfield(default_factory=list)
    source_snapshot_ids: list[str] = dfield(default_factory=list)
    derived_asof_status: str = "LEGACY_TEMPORAL_UNVERIFIED"
    probability_level: float | None = None
    probability_velocity: float | None = None
    probability_acceleration: float | None = None
    probability_status: str = "NOT_AVAILABLE_UPSTREAM_UNCALIBRATED"
    change_point_status: str = "RESEARCH_CHALLENGER_NOT_IMPLEMENTED"
    change_point_method: str | None = None
    change_point_score: float | None = None
    sequence_status: str = "NOT_AVAILABLE"
    block_reason_codes: list[str] = dfield(default_factory=list)
    candidate_snapshot_audits: list[SequenceCandidateSnapshotAudit] = dfield(default_factory=list)
    candidate_transition_audits: list[SequenceCandidateTransitionAudit] = dfield(default_factory=list)
    candidate_snapshot_ids: list[str] = dfield(default_factory=list)
    candidate_snapshot_fingerprints: list[str] = dfield(default_factory=list)
    candidate_transition_ids: list[str] = dfield(default_factory=list)
    candidate_transition_fingerprints: list[str] = dfield(default_factory=list)
    candidate_target_identities: list[str] = dfield(default_factory=list)
    candidate_state_stream_ids: list[str] = dfield(default_factory=list)
    candidate_snapshot_schema_versions: list[str] = dfield(default_factory=list)
    candidate_snapshot_source_snapshot_ids: list[str] = dfield(default_factory=list)
    candidate_transition_source_snapshot_ids: list[str] = dfield(default_factory=list)
    candidate_source_snapshot_ids: list[str] = dfield(default_factory=list)
    candidate_snapshot_asof_by_id: dict[str, str] = dfield(default_factory=dict)
    blocked_input_count: int = 0
    parent_sequence_id: str = ""
    existing_sequence_declared_id: str = ""
    existing_sequence_recomputed_id: str = ""
    schema_version: str = V2_SEQUENTIAL_UPDATE_SCHEMA_VERSION
    policy_version: str = "2G.2"

    def semantic_dump(self) -> dict:
        return asdict(self)

    def model_dump(self) -> dict:
        return asdict(self)


# ── identity ──
def sequence_identity(a: StateSequenceArtifact) -> str:
    """Content-addressed sequence id (valid artifacts): every semantic field, order preserved for
    chronology, snapshot/transition content captured via recomputed fingerprints (mutation-detectable),
    created_at excluded."""
    payload = {
        "instrument": normalize_instrument(a.instrument),
        "target_family": normalize_family(a.target_family),
        "instrument_role": a.instrument_role,
        "calendar_id": a.calendar_id,
        "frequency": a.frequency,
        "horizon": a.horizon,
        "first_state_origin": _dt_iso(a.first_state_origin),
        "last_state_origin": _dt_iso(a.last_state_origin),
        "first_feature_cutoff": _dt_iso(a.first_feature_cutoff),
        "last_feature_cutoff": _dt_iso(a.last_feature_cutoff),
        "snapshot_ids": list(a.snapshot_ids),
        "snapshot_fingerprints": [snapshot_identity(s) for s in a.snapshots],
        "transition_ids": list(a.transition_ids),
        "transition_fingerprints": [_transition_key(t) for t in a.transitions],
        "steps": [asdict(s) for s in a.steps],
        "layer_run_descriptors": [asdict(r) for r in a.layer_run_descriptors],
        "snapshot_source_snapshot_ids": _canonical(a.snapshot_source_snapshot_ids),
        "transition_source_snapshot_ids": _canonical(a.transition_source_snapshot_ids),
        "source_snapshot_ids": _canonical(a.source_snapshot_ids),
        "derived_asof_status": a.derived_asof_status,
        "probability_level": a.probability_level,
        "probability_velocity": a.probability_velocity,
        "probability_acceleration": a.probability_acceleration,
        "probability_status": a.probability_status,
        "change_point_status": a.change_point_status,
        "change_point_method": a.change_point_method,
        "change_point_score": a.change_point_score,
        "sequence_status": a.sequence_status,
        "block_reason_codes": _canonical(a.block_reason_codes),
        "candidate_snapshot_audits": [asdict(x) for x in a.candidate_snapshot_audits],
        "candidate_transition_audits": [asdict(x) for x in a.candidate_transition_audits],
        "candidate_snapshot_ids": list(a.candidate_snapshot_ids),
        "candidate_snapshot_fingerprints": list(a.candidate_snapshot_fingerprints),
        "candidate_transition_ids": list(a.candidate_transition_ids),
        "candidate_transition_fingerprints": list(a.candidate_transition_fingerprints),
        "candidate_target_identities": list(a.candidate_target_identities),
        "candidate_state_stream_ids": list(a.candidate_state_stream_ids),
        "candidate_snapshot_schema_versions": list(a.candidate_snapshot_schema_versions),
        "candidate_snapshot_source_snapshot_ids": list(a.candidate_snapshot_source_snapshot_ids),
        "candidate_transition_source_snapshot_ids": list(a.candidate_transition_source_snapshot_ids),
        "candidate_source_snapshot_ids": list(a.candidate_source_snapshot_ids),
        "candidate_snapshot_asof_by_id": dict(sorted(a.candidate_snapshot_asof_by_id.items())),
        "blocked_input_count": a.blocked_input_count,
        "parent_sequence_id": a.parent_sequence_id,
        "existing_sequence_declared_id": a.existing_sequence_declared_id,
        "existing_sequence_recomputed_id": a.existing_sequence_recomputed_id,
        "schema_version": a.schema_version,
        "policy_version": a.policy_version,
    }
    return _hash_payload(payload)


def _blocked_artifact_from_audits(
        snapshot_audits: list[SequenceCandidateSnapshotAudit],
        transition_audits: list[SequenceCandidateTransitionAudit],
        reason: str, *, parent_sequence_id: str = "",
        existing_sequence_declared_id: str = "", existing_sequence_recomputed_id: str = "",
) -> StateSequenceArtifact:
    """Build a BLOCKED artifact that preserves full candidate/input audit lineage and whose
    sequence_id is recomputable from the returned artifact itself."""
    snap_audits = sorted(snapshot_audits, key=_snapshot_audit_sort_key)
    trans_audits = sorted(transition_audits, key=_transition_audit_sort_key)

    snapshot_source = _canonical([sid for x in snap_audits for sid in x.source_snapshot_ids])
    transition_source = _canonical([sid for x in trans_audits for sid in x.source_snapshot_ids])
    identities = sorted({_render_target_identity(x.instrument, x.target_family, x.instrument_role,
                                                 x.calendar_id, x.frequency, x.horizon)
                         for x in snap_audits})
    streams = sorted({_render_state_stream(x) for x in snap_audits})
    origins = [x.state_origin for x in snap_audits if x.state_origin is not None]
    cutoffs = [x.feature_cutoff_timestamp for x in snap_audits if x.feature_cutoff_timestamp is not None]

    artifact = StateSequenceArtifact(
        sequence_id="",
        sequence_status="BLOCKED",
        block_reason_codes=[reason],
        candidate_snapshot_audits=snap_audits,
        candidate_transition_audits=trans_audits,
        candidate_snapshot_ids=[x.declared_snapshot_id for x in snap_audits],
        candidate_snapshot_fingerprints=[x.recomputed_snapshot_id for x in snap_audits],
        candidate_transition_ids=[x.declared_transition_id for x in trans_audits],
        candidate_transition_fingerprints=[x.recomputed_transition_fingerprint for x in trans_audits],
        candidate_target_identities=identities,
        candidate_state_stream_ids=streams,
        candidate_snapshot_schema_versions=sorted({x.state_schema_version for x in snap_audits if x.state_schema_version}),
        candidate_snapshot_source_snapshot_ids=snapshot_source,
        candidate_transition_source_snapshot_ids=transition_source,
        candidate_source_snapshot_ids=_canonical(snapshot_source + transition_source),
        candidate_snapshot_asof_by_id={x.declared_snapshot_id: x.derived_asof_status for x in snap_audits},
        blocked_input_count=len(snap_audits) + len(trans_audits),
        first_state_origin=min(origins) if origins else None,
        last_state_origin=max(origins) if origins else None,
        first_feature_cutoff=min(cutoffs) if cutoffs else None,
        last_feature_cutoff=max(cutoffs) if cutoffs else None,
        derived_asof_status=_least_verified_asof([x.derived_asof_status for x in snap_audits]),
        parent_sequence_id=parent_sequence_id,
        existing_sequence_declared_id=existing_sequence_declared_id,
        existing_sequence_recomputed_id=existing_sequence_recomputed_id,
    )
    # common identity only when every candidate agrees; never first-item authority (§12)
    if len(identities) == 1 and snap_audits:
        x = snap_audits[0]
        artifact.instrument = x.instrument
        artifact.target_family = x.target_family
        artifact.instrument_role = x.instrument_role
        artifact.calendar_id = x.calendar_id
        artifact.frequency = x.frequency
        artifact.horizon = x.horizon
    artifact.sequence_id = sequence_identity(artifact)
    return artifact


def _blocked_artifact(snapshots: list[StateSnapshot], transitions: list[StateTransitionRecord],
                      reason: str) -> StateSequenceArtifact:
    return _blocked_artifact_from_audits(
        [_snapshot_audit(s) for s in snapshots],
        [_transition_audit(t) for t in transitions],
        reason,
    )


# ── validation ──
def _validate_snapshot(snap: StateSnapshot) -> str | None:
    if snap.state_schema_version != V2_STATE_MACHINE_SCHEMA_VERSION:
        return BLOCKED_UNSUPPORTED_UPSTREAM_SCHEMA
    if snap.snapshot_status == "BLOCKED":
        return BLOCKED_UPSTREAM_SNAPSHOT
    if snapshot_identity(snap) != snap.snapshot_id:
        return BLOCKED_SNAPSHOT_INTEGRITY_MISMATCH
    if snap.state_origin is None or snap.feature_cutoff_timestamp is None:
        return BLOCKED_SNAPSHOT_INTEGRITY_MISMATCH
    return None


def _validate_transitions(sorted_snaps: list[StateSnapshot],
                          transitions: list[StateTransitionRecord]) -> tuple[dict | None, str | None]:
    if not transitions:
        return {}, None
    adjacent = {(sorted_snaps[i].snapshot_id, sorted_snaps[i + 1].snapshot_id)
                for i in range(len(sorted_snaps) - 1)}
    snap_by_id = {s.snapshot_id: s for s in sorted_snaps}
    by_key: dict[tuple[str, str], StateTransitionRecord] = {}
    for t in transitions:
        key = (t.previous_snapshot_id, t.new_snapshot_id)
        if key not in adjacent:
            return None, BLOCKED_ORPHAN_TRANSITION
        if key in by_key:
            if by_key[key].semantic_dump() != t.semantic_dump():
                return None, BLOCKED_TRANSITION_ID_COLLISION
            continue  # exact duplicate dedupe
        by_key[key] = t
    # strong integrity: rebuild canonical transition and compare semantic dumps
    for key, t in by_key.items():
        prev = snap_by_id[key[0]]
        curr = snap_by_id[key[1]]
        try:
            expected = transition(prev, curr, trigger_evidence_ids=t.trigger_evidence_ids)
        except Exception:
            return None, BLOCKED_TRANSITION_INTEGRITY_MISMATCH
        if expected.semantic_dump() != t.semantic_dump():
            return None, BLOCKED_TRANSITION_INTEGRITY_MISMATCH
        if ensure_utc_aware(t.transition_timestamp) != ensure_utc_aware(curr.state_origin):
            return None, BLOCKED_TRANSITION_INTEGRITY_MISMATCH
    return by_key, None


# ── revision / run ──
def _build_step(prev: StateSnapshot, curr: StateSnapshot,
                trans: StateTransitionRecord | None) -> StateSequenceStep:
    changed_state: list[str] = []
    changed_attr: list[str] = []
    revs: list[LayerRevisionDescriptor] = []
    for layer in LAYERS:
        pl = prev.layers()[layer]
        cl = curr.layers()[layer]
        sc = (pl.value != cl.value) or (pl.status != cl.status)
        ac = (_canonical(pl.evidence_ids) != _canonical(cl.evidence_ids)
              or _canonical(pl.source_snapshot_ids) != _canonical(cl.source_snapshot_ids)
              or _canonical(pl.reason_codes) != _canonical(cl.reason_codes))
        if sc:
            changed_state.append(layer)
        if ac:
            changed_attr.append(layer)
        revs.append(LayerRevisionDescriptor(layer=layer, state_changed=sc, attribution_changed=ac))

    prev_ids = set(prev.evidence_ids)
    curr_ids = set(curr.evidence_ids)
    prev_snaps = set(prev.source_snapshot_ids)
    curr_snaps = set(curr.source_snapshot_ids)

    if changed_state:
        update_kind = "STATE_CHANGE"
    elif changed_attr:
        update_kind = "ATTRIBUTION_ONLY"
    else:
        update_kind = "NO_LAYER_CHANGE"

    elapsed = (ensure_utc_aware(curr.state_origin) - ensure_utc_aware(prev.state_origin)).total_seconds()
    cutoff_delta = (ensure_utc_aware(curr.feature_cutoff_timestamp)
                    - ensure_utc_aware(prev.feature_cutoff_timestamp)).total_seconds()
    info_advanced = ensure_utc_aware(curr.feature_cutoff_timestamp) > ensure_utc_aware(prev.feature_cutoff_timestamp)

    transition_id = trans.transition_id if trans is not None else ""
    transition_status = "VERIFIED" if trans is not None else "NOT_PROVIDED"

    return StateSequenceStep(
        step_id=_id_fp(["step", prev.snapshot_id, curr.snapshot_id]),
        previous_snapshot_id=prev.snapshot_id, current_snapshot_id=curr.snapshot_id,
        previous_state_origin=prev.state_origin, current_state_origin=curr.state_origin,
        previous_feature_cutoff=prev.feature_cutoff_timestamp, current_feature_cutoff=curr.feature_cutoff_timestamp,
        elapsed_seconds=elapsed, cutoff_delta_seconds=cutoff_delta,
        information_advanced=info_advanced,
        state_changed_layers=changed_state, attribution_changed_layers=changed_attr,
        layer_revision_descriptors=revs,
        evidence_added_ids=_canonical(curr_ids - prev_ids),
        evidence_removed_ids=_canonical(prev_ids - curr_ids),
        source_snapshot_added_ids=_canonical(curr_snaps - prev_snaps),
        source_snapshot_removed_ids=_canonical(prev_snaps - curr_snaps),
        transition_id=transition_id, transition_status=transition_status,
        derived_asof_status=_least_verified_asof([prev.derived_asof_status, curr.derived_asof_status]),
        update_kind=update_kind,
    )


def _compute_run_descriptors(sorted_snaps: list[StateSnapshot]) -> list[LayerRunDescriptor]:
    runs = {layer: {"value": None, "status": None, "start": None, "count": 0} for layer in LAYERS}
    for s in sorted_snaps:
        for layer in LAYERS:
            ls = s.layers()[layer]
            if runs[layer]["value"] != ls.value or runs[layer]["status"] != ls.status:
                runs[layer] = {"value": ls.value, "status": ls.status, "start": s.state_origin, "count": 1}
            else:
                runs[layer]["count"] += 1
    end = sorted_snaps[-1].state_origin
    descs: list[LayerRunDescriptor] = []
    for layer in LAYERS:
        r = runs[layer]
        elapsed = None
        if r["start"] is not None:
            elapsed = (ensure_utc_aware(end) - ensure_utc_aware(r["start"])).total_seconds()
        descs.append(LayerRunDescriptor(
            layer=layer, value=r["value"], status=r["status"],
            run_start_origin=r["start"], current_origin=end,
            run_length_observations=r["count"], run_elapsed_seconds=elapsed))
    return descs


# ── build / append ──
def build_state_sequence(snapshots: list[StateSnapshot],
                         transitions: list[StateTransitionRecord] | None = None) -> StateSequenceArtifact:
    transitions = list(transitions or [])
    if not snapshots:
        return StateSequenceArtifact(sequence_status="NOT_AVAILABLE")

    # snapshot integrity + upstream schema + status gate
    for snap in snapshots:
        reason = _validate_snapshot(snap)
        if reason:
            return _blocked_artifact(snapshots, transitions, reason)

    # deep-copy on ingest (strip wall-clock created_at for determinism)
    snaps = [_strip_created(s) for s in snapshots]

    # target identity isolation
    if len({_target_identity(s) for s in snaps}) != 1:
        return _blocked_artifact(snapshots, transitions, BLOCKED_IDENTITY_MISMATCH)

    # exact-duplicate dedupe + same-id-different-payload collision (defensive)
    by_id: dict[str, StateSnapshot] = {}
    for s in snaps:
        if s.snapshot_id in by_id:
            if by_id[s.snapshot_id].semantic_dump() != s.semantic_dump():
                return _blocked_artifact(snapshots, transitions, BLOCKED_SNAPSHOT_ID_COLLISION)
            continue
        by_id[s.snapshot_id] = s
    deduped = list(by_id.values())

    # canonical chronology by state_origin
    sorted_snaps = sorted(deduped, key=lambda s: ensure_utc_aware(s.state_origin))

    # same origin / different snapshot -> ambiguous branch
    origins: dict[datetime, StateSnapshot] = {}
    for s in sorted_snaps:
        o = ensure_utc_aware(s.state_origin)
        if o in origins and origins[o].snapshot_id != s.snapshot_id:
            return _blocked_artifact(snapshots, transitions, BLOCKED_AMBIGUOUS_STATE_ORIGIN)
        origins[o] = s

    # monotonic origin (strict) + non-decreasing cutoff
    for i in range(len(sorted_snaps) - 1):
        if ensure_utc_aware(sorted_snaps[i + 1].state_origin) <= ensure_utc_aware(sorted_snaps[i].state_origin):
            return _blocked_artifact(snapshots, transitions, BLOCKED_AMBIGUOUS_STATE_ORIGIN)
        if ensure_utc_aware(sorted_snaps[i + 1].feature_cutoff_timestamp) \
                < ensure_utc_aware(sorted_snaps[i].feature_cutoff_timestamp):
            return _blocked_artifact(snapshots, transitions, BLOCKED_CUTOFF_REGRESSION)

    # transition validation
    trans_by_key, trans_reason = _validate_transitions(sorted_snaps, transitions)
    if trans_reason:
        return _blocked_artifact(snapshots, transitions, trans_reason)

    # build steps
    steps: list[StateSequenceStep] = []
    for i in range(len(sorted_snaps) - 1):
        prev, curr = sorted_snaps[i], sorted_snaps[i + 1]
        t = trans_by_key.get((prev.snapshot_id, curr.snapshot_id))
        steps.append(_build_step(prev, curr, t))

    run_descs = _compute_run_descriptors(sorted_snaps)

    snapshot_union = _canonical([sid for s in sorted_snaps for sid in s.source_snapshot_ids])
    transition_union = _canonical([sid for t in transitions for sid in t.source_snapshot_ids])
    union = _canonical(snapshot_union + transition_union)
    derived_asof = _least_verified_asof([s.derived_asof_status for s in sorted_snaps])

    artifact = StateSequenceArtifact(
        sequence_id="",
        instrument=sorted_snaps[0].instrument, target_family=sorted_snaps[0].target_family,
        instrument_role=sorted_snaps[0].instrument_role, calendar_id=sorted_snaps[0].calendar_id,
        frequency=sorted_snaps[0].frequency, horizon=sorted_snaps[0].horizon,
        first_state_origin=sorted_snaps[0].state_origin, last_state_origin=sorted_snaps[-1].state_origin,
        first_feature_cutoff=sorted_snaps[0].feature_cutoff_timestamp,
        last_feature_cutoff=sorted_snaps[-1].feature_cutoff_timestamp,
        snapshot_ids=[s.snapshot_id for s in sorted_snaps],
        transition_ids=[s.transition_id for s in steps if s.transition_id],
        steps=steps,
        layer_run_descriptors=run_descs,
        snapshots=sorted_snaps,
        transitions=[copy.deepcopy(t) for t in sorted(
            trans_by_key.values(), key=lambda t: (t.previous_snapshot_id, t.new_snapshot_id))],
        snapshot_source_snapshot_ids=snapshot_union,
        transition_source_snapshot_ids=transition_union,
        source_snapshot_ids=union,
        derived_asof_status=derived_asof,
        sequence_status="SEQUENCE_AVAILABLE",
    )
    artifact.sequence_id = sequence_identity(artifact)
    return artifact


def append_state_update(existing: StateSequenceArtifact,
                        new_snapshot: StateSnapshot,
                        transition: StateTransitionRecord | None = None) -> StateSequenceArtifact:
    if existing.sequence_status == "NOT_AVAILABLE":
        return build_state_sequence([new_snapshot], [transition] if transition is not None else None)

    declared_existing = existing.sequence_id
    recomputed_existing = sequence_identity(existing)

    if existing.sequence_status == "SEQUENCE_AVAILABLE" and recomputed_existing == existing.sequence_id:
        snapshots = list(existing.snapshots) + [new_snapshot]
        transitions = list(existing.transitions) + ([transition] if transition is not None else [])
        return build_state_sequence(snapshots, transitions)

    new_transitions = [transition] if transition is not None else []
    if existing.sequence_status == "BLOCKED":
        reason = BLOCKED_EXISTING_SEQUENCE_NOT_APPENDABLE
        snap_audits = list(existing.candidate_snapshot_audits) + [_snapshot_audit(new_snapshot)]
        trans_audits = list(existing.candidate_transition_audits) + [_transition_audit(t) for t in new_transitions]
    else:  # SEQUENCE_AVAILABLE but corrupted (declared != recomputed)
        reason = BLOCKED_SEQUENCE_INTEGRITY_MISMATCH
        snap_audits = [_snapshot_audit(s) for s in existing.snapshots] + [_snapshot_audit(new_snapshot)]
        trans_audits = [_transition_audit(t) for t in existing.transitions] + [_transition_audit(t) for t in new_transitions]

    return _blocked_artifact_from_audits(
        snap_audits, trans_audits, reason,
        parent_sequence_id=declared_existing,
        existing_sequence_declared_id=declared_existing,
        existing_sequence_recomputed_id=recomputed_existing,
    )
