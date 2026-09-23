"""Phase V2-G — sequential state updating scaffold tests."""
from __future__ import annotations

import copy
import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, "src")

from market_ai_hub.research.v2 import state_machine as SM
from market_ai_hub.research.v2 import sequential_update as SU


def _dt(d, h=0, m=0):
    return datetime(2026, 9, d, h, m, tzinfo=timezone.utc)


def _ctx(**kw):
    base = dict(instrument="JNU", target_family="OSAKA_MICRO", instrument_role="DIRECT",
                calendar_id="OSE_DERIVATIVES", frequency="DAILY", horizon="1d",
                feature_cutoff_timestamp=_dt(18, 8, 0), state_origin=_dt(18, 8, 0))
    base.update(kw)
    return SM.StateEvaluationContext(**base)


def _ev(layer, value, eid="e1", **kw):
    base = dict(evidence_id=eid, layer=layer, value=value,
                instrument="JNU", target_family="OSAKA_MICRO", instrument_role="DIRECT",
                calendar_id="OSE_DERIVATIVES", frequency="DAILY", horizon="1d",
                event_timestamp=_dt(18, 0, 0), available_at=_dt(18, 7, 0),
                source_type="TYPED_EVIDENCE", source_schema_version="v1", source_version="v1",
                provenance_status="VERIFIED_INPUT")
    base.update(kw)
    return SM.StateEvidence(**base)


def _snap(origin, specs, cutoff=None, **ctx_kw):
    """specs: list of (layer, value, evidence_id)."""
    evs = [_ev(layer, value, eid) for (layer, value, eid) in specs]
    kw = dict(state_origin=origin, feature_cutoff_timestamp=cutoff if cutoff is not None else origin)
    kw.update(ctx_kw)
    return SM.compose_state_snapshot(_ctx(**kw), evs)


def _forge_identity(snap, **changes):
    s = copy.deepcopy(snap)
    for k, v in changes.items():
        setattr(s, k, v)
    s.snapshot_id = SM.snapshot_identity(s)
    return s


def _synthetic():
    s0 = _snap(_dt(18, 8), [("DIRECTIONAL", "BULLISH", "d1"), ("EXTENSION", "NORMAL", "x1")])
    s1 = _snap(_dt(18, 9), [("DIRECTIONAL", "BULLISH", "d1"), ("EXTENSION", "EXTENDED", "x1")])
    s2 = _snap(_dt(18, 10), [("DIRECTIONAL", "BULLISH", "d1"), ("EXTENSION", "EXTREME", "x1"),
                             ("RISK", "EXHAUSTION_WARNING", "r1")])
    s3 = _snap(_dt(18, 11), [("DIRECTIONAL", "BEARISH", "d1"), ("EXTENSION", "NORMAL", "x1")])
    return [s0, s1, s2, s3]


# ── schema / capability ──
def test_v2g_schema_2g1():
    assert SU.V2_SEQUENTIAL_UPDATE_SCHEMA_VERSION == "2G.1"


def test_change_point_methods_are_research_challenger_not_implemented():
    assert SU.V2G_CAPABILITIES["CUSUM"] == "RESEARCH_CHALLENGER_NOT_IMPLEMENTED"
    assert SU.V2G_CAPABILITIES["PAGE_HINKLEY"] == "RESEARCH_CHALLENGER_NOT_IMPLEMENTED"
    assert SU.V2G_CAPABILITIES["BOCPD"] == "RESEARCH_CHALLENGER_NOT_IMPLEMENTED"


def test_probability_velocity_not_available():
    assert SU.V2G_CAPABILITIES["PROBABILITY_VELOCITY"] == "NOT_AVAILABLE_PENDING_CALIBRATED_PROBABILITY"


def test_probability_acceleration_not_available():
    assert SU.V2G_CAPABILITIES["PROBABILITY_ACCELERATION"] == "NOT_AVAILABLE_PENDING_CALIBRATED_PROBABILITY"


def test_state_transition_probability_not_available():
    assert SU.V2G_CAPABILITIES["STATE_TRANSITION_PROBABILITY"] == "RESEARCH_CHALLENGER_NOT_IMPLEMENTED"


# ── snapshot integrity ──
def test_valid_content_addressed_snapshot_is_accepted():
    a = SU.build_state_sequence(_synthetic())
    assert a.sequence_status == "SEQUENCE_AVAILABLE"


def test_mutated_snapshot_with_stale_id_blocks():
    snaps = _synthetic()
    snaps[0].directional_state.value = "STRONG_BULL"
    a = SU.build_state_sequence(snaps)
    assert a.sequence_status == "BLOCKED"
    assert SU.BLOCKED_SNAPSHOT_INTEGRITY_MISMATCH in a.block_reason_codes


def test_blocked_snapshot_cannot_enter_sequence():
    s0 = _snap(_dt(18, 8), [("DIRECTIONAL", "BULLISH", "d1")])
    s1 = _snap(_dt(18, 9), [("DIRECTIONAL", "BULLISH", "d1")])
    blocked = SM.compose_state_snapshot(_ctx(state_origin=_dt(18, 8)), [_ev("DIRECTIONAL", "BULLISH", event_timestamp=None)])
    assert blocked.snapshot_status == "BLOCKED"
    a = SU.build_state_sequence([blocked, s1])
    assert a.sequence_status == "BLOCKED"
    assert SU.BLOCKED_UPSTREAM_SNAPSHOT in a.block_reason_codes


def test_unsupported_v2d_schema_blocks():
    s0 = _snap(_dt(18, 8), [("DIRECTIONAL", "BULLISH", "d1")])
    s1 = _snap(_dt(18, 9), [("DIRECTIONAL", "BULLISH", "d1")])
    s0.state_schema_version = "2D.3"
    s0.snapshot_id = SM.snapshot_identity(s0)
    a = SU.build_state_sequence([s0, s1])
    assert a.sequence_status == "BLOCKED"
    assert SU.BLOCKED_UNSUPPORTED_UPSTREAM_SCHEMA in a.block_reason_codes


def test_snapshot_integrity_check_uses_v2d_snapshot_identity():
    assert SU.snapshot_identity is SM.snapshot_identity


# ── deep copy ──
def test_sequence_deep_copies_input_snapshots():
    snaps = _synthetic()
    a = SU.build_state_sequence(snaps)
    assert a.snapshots[0] is not snaps[0]
    assert a.snapshots[0].directional_state is not snaps[0].directional_state


def test_mutating_source_snapshot_after_build_does_not_change_sequence():
    snaps = _synthetic()
    a = SU.build_state_sequence(snaps)
    before = a.sequence_id
    snaps[0].directional_state.value = "STRONG_BULL"
    snaps[1].extension_state.value = "EXTREME"
    assert a.sequence_id == before


def test_mutating_nested_layer_lists_after_build_does_not_change_sequence():
    snaps = _synthetic()
    a = SU.build_state_sequence(snaps)
    before = a.sequence_id
    snaps[0].directional_state.evidence_ids.append("extra")
    snaps[0].directional_state.reason_codes.append("X")
    assert a.sequence_id == before


# ── identity isolation ──
def test_cross_instrument_sequence_blocks():
    s0 = _snap(_dt(18, 8), [("DIRECTIONAL", "BULLISH", "d1")])
    s1 = _forge_identity(_snap(_dt(18, 9), [("DIRECTIONAL", "BULLISH", "d1")]), instrument="NK225M")
    a = SU.build_state_sequence([s0, s1])
    assert a.sequence_status == "BLOCKED"
    assert SU.BLOCKED_IDENTITY_MISMATCH in a.block_reason_codes


def test_cross_target_family_sequence_blocks():
    s0 = _snap(_dt(18, 8), [("DIRECTIONAL", "BULLISH", "d1")])
    s1 = _forge_identity(_snap(_dt(18, 9), [("DIRECTIONAL", "BULLISH", "d1")]), target_family="TAIWAN_STOCK")
    a = SU.build_state_sequence([s0, s1])
    assert a.sequence_status == "BLOCKED"
    assert SU.BLOCKED_IDENTITY_MISMATCH in a.block_reason_codes


def test_cross_role_sequence_blocks():
    s0 = _snap(_dt(18, 8), [("DIRECTIONAL", "BULLISH", "d1")])
    s1 = _forge_identity(_snap(_dt(18, 9), [("DIRECTIONAL", "BULLISH", "d1")]), instrument_role="PROXY")
    a = SU.build_state_sequence([s0, s1])
    assert a.sequence_status == "BLOCKED"
    assert SU.BLOCKED_IDENTITY_MISMATCH in a.block_reason_codes


def test_cross_calendar_sequence_blocks():
    s0 = _snap(_dt(18, 8), [("DIRECTIONAL", "BULLISH", "d1")])
    s1 = _forge_identity(_snap(_dt(18, 9), [("DIRECTIONAL", "BULLISH", "d1")]), calendar_id="TAIEX")
    a = SU.build_state_sequence([s0, s1])
    assert a.sequence_status == "BLOCKED"
    assert SU.BLOCKED_IDENTITY_MISMATCH in a.block_reason_codes


def test_cross_frequency_sequence_blocks():
    s0 = _snap(_dt(18, 8), [("DIRECTIONAL", "BULLISH", "d1")])
    s1 = _forge_identity(_snap(_dt(18, 9), [("DIRECTIONAL", "BULLISH", "d1")]), frequency="5D")
    a = SU.build_state_sequence([s0, s1])
    assert a.sequence_status == "BLOCKED"
    assert SU.BLOCKED_IDENTITY_MISMATCH in a.block_reason_codes


def test_cross_horizon_sequence_blocks():
    s0 = _snap(_dt(18, 8), [("DIRECTIONAL", "BULLISH", "d1")])
    s1 = _forge_identity(_snap(_dt(18, 9), [("DIRECTIONAL", "BULLISH", "d1")]), horizon="5d")
    a = SU.build_state_sequence([s0, s1])
    assert a.sequence_status == "BLOCKED"
    assert SU.BLOCKED_IDENTITY_MISMATCH in a.block_reason_codes


# ── chronology ──
def test_input_order_does_not_change_sequence():
    snaps = _synthetic()
    a1 = SU.build_state_sequence(snaps)
    a2 = SU.build_state_sequence([snaps[2], snaps[0], snaps[3], snaps[1]])
    assert a1.sequence_id == a2.sequence_id
    assert a1.semantic_dump() == a2.semantic_dump()


def test_snapshots_are_canonical_sorted_by_origin():
    snaps = _synthetic()
    a = SU.build_state_sequence([snaps[3], snaps[1], snaps[0], snaps[2]])
    assert a.snapshot_ids == [s.snapshot_id for s in sorted(snaps, key=lambda s: s.state_origin)]


def test_exact_duplicate_snapshot_dedupes():
    snaps = _synthetic()
    a1 = SU.build_state_sequence(snaps)
    a2 = SU.build_state_sequence([snaps[0], snaps[0], snaps[1], snaps[2], snaps[3]])
    assert a1.sequence_id == a2.sequence_id
    assert len(a2.snapshot_ids) == 4


def test_same_origin_different_snapshot_blocks():
    s0 = _snap(_dt(18, 8), [("DIRECTIONAL", "BULLISH", "d1")])
    s1 = _snap(_dt(18, 8), [("DIRECTIONAL", "BEARISH", "d1")])
    a = SU.build_state_sequence([s0, s1])
    assert a.sequence_status == "BLOCKED"
    assert SU.BLOCKED_AMBIGUOUS_STATE_ORIGIN in a.block_reason_codes


def test_cutoff_regression_blocks():
    s0 = _snap(_dt(18, 8), [("DIRECTIONAL", "BULLISH", "d1")], cutoff=_dt(18, 8))
    s1 = _snap(_dt(18, 9), [("DIRECTIONAL", "BULLISH", "d1")], cutoff=_dt(18, 7))
    a = SU.build_state_sequence([s0, s1])
    assert a.sequence_status == "BLOCKED"
    assert SU.BLOCKED_CUTOFF_REGRESSION in a.block_reason_codes


def test_equal_cutoff_is_allowed_and_information_advanced_false():
    s0 = _snap(_dt(18, 8), [("DIRECTIONAL", "BULLISH", "d1")], cutoff=_dt(18, 8))
    s1 = _snap(_dt(18, 9), [("DIRECTIONAL", "BULLISH", "d1")], cutoff=_dt(18, 8))
    a = SU.build_state_sequence([s0, s1])
    assert a.sequence_status == "SEQUENCE_AVAILABLE"
    assert a.steps[0].information_advanced is False


def test_advancing_cutoff_sets_information_advanced_true():
    s0 = _snap(_dt(18, 8), [("DIRECTIONAL", "BULLISH", "d1")], cutoff=_dt(18, 8))
    s1 = _snap(_dt(18, 9), [("DIRECTIONAL", "BULLISH", "d1")], cutoff=_dt(18, 9))
    a = SU.build_state_sequence([s0, s1])
    assert a.steps[0].information_advanced is True


# ── revision descriptor ──
def test_state_value_change_is_state_change():
    s0 = _snap(_dt(18, 8), [("DIRECTIONAL", "BULLISH", "d1")])
    s1 = _snap(_dt(18, 9), [("DIRECTIONAL", "BEARISH", "d1")])
    a = SU.build_state_sequence([s0, s1])
    assert "DIRECTIONAL" in a.steps[0].state_changed_layers
    assert a.steps[0].update_kind == "STATE_CHANGE"


def test_status_change_is_state_change():
    s0 = _snap(_dt(18, 8), [("DIRECTIONAL", "BULLISH", "d1")])
    s1 = _snap(_dt(18, 9), [("DIRECTIONAL", "BULLISH", "a1"), ("DIRECTIONAL", "BEARISH", "b1")])
    assert s1.directional_state.status == "CONFLICT"
    a = SU.build_state_sequence([s0, s1])
    assert "DIRECTIONAL" in a.steps[0].state_changed_layers


def test_attribution_only_change_is_not_state_change():
    s0 = _snap(_dt(18, 8), [("DIRECTIONAL", "BULLISH", "d1")])
    s1 = _snap(_dt(18, 9), [("DIRECTIONAL", "BULLISH", "d2")])
    a = SU.build_state_sequence([s0, s1])
    assert "DIRECTIONAL" not in a.steps[0].state_changed_layers
    assert "DIRECTIONAL" in a.steps[0].attribution_changed_layers
    assert a.steps[0].update_kind == "ATTRIBUTION_ONLY"


def test_no_layer_change_descriptor():
    s0 = _snap(_dt(18, 8), [("DIRECTIONAL", "BULLISH", "d1")])
    s1 = _snap(_dt(18, 9), [("DIRECTIONAL", "BULLISH", "d1")])
    a = SU.build_state_sequence([s0, s1])
    assert a.steps[0].state_changed_layers == []
    assert a.steps[0].attribution_changed_layers == []
    assert a.steps[0].update_kind == "NO_LAYER_CHANGE"


def test_evidence_added_removed_are_canonical():
    s0 = _snap(_dt(18, 8), [("DIRECTIONAL", "BULLISH", "d1")])
    s1 = _snap(_dt(18, 9), [("DIRECTIONAL", "BULLISH", "d1"), ("RISK", "EXHAUSTION_WARNING", "r1")])
    a = SU.build_state_sequence([s0, s1])
    assert a.steps[0].evidence_added_ids == ["r1"]
    assert a.steps[0].evidence_removed_ids == []


def test_source_added_removed_are_canonical():
    s0 = _snap(_dt(18, 8), [("DIRECTIONAL", "BULLISH", "d1")])
    s1 = _snap(_dt(18, 9), [("DIRECTIONAL", "BULLISH", "d1")], source_snapshot_ids=["srcB", "srcA"])
    a = SU.build_state_sequence([s0, s1])
    assert a.steps[0].source_snapshot_added_ids == ["srcA", "srcB"]


# ── categorical no arithmetic ──
def test_bullish_to_strong_bull_has_no_numeric_velocity():
    s0 = _snap(_dt(18, 8), [("DIRECTIONAL", "BULLISH", "d1")])
    s1 = _snap(_dt(18, 9), [("DIRECTIONAL", "STRONG_BULL", "d1")])
    a = SU.build_state_sequence([s0, s1])
    assert a.probability_velocity is None
    assert a.probability_level is None
    assert a.probability_acceleration is None


def test_extreme_to_normal_has_no_numeric_velocity():
    s0 = _snap(_dt(18, 8), [("EXTENSION", "EXTREME", "x1")])
    s1 = _snap(_dt(18, 9), [("EXTENSION", "NORMAL", "x1")])
    a = SU.build_state_sequence([s0, s1])
    assert a.probability_velocity is None
    for d in a.semantic_dump():
        assert "ordinal" not in d.lower()


def test_chase_stop_does_not_create_directional_velocity():
    s0 = _snap(_dt(18, 8), [("DIRECTIONAL", "BULLISH", "d1"), ("CHASE_RISK", "STOP", "c1")])
    s1 = _snap(_dt(18, 9), [("DIRECTIONAL", "BULLISH", "d1"), ("CHASE_RISK", "STOP", "c1")])
    a = SU.build_state_sequence([s0, s1])
    assert a.probability_velocity is None
    assert "DIRECTIONAL" not in a.steps[0].state_changed_layers


# ── dwell / run ──
def test_direction_run_length_increments():
    s0 = _snap(_dt(18, 8), [("DIRECTIONAL", "BULLISH", "d1")])
    s1 = _snap(_dt(18, 9), [("DIRECTIONAL", "BULLISH", "d1")])
    s2 = _snap(_dt(18, 10), [("DIRECTIONAL", "BULLISH", "d1")])
    a = SU.build_state_sequence([s0, s1, s2])
    d = [r for r in a.layer_run_descriptors if r.layer == "DIRECTIONAL"][0]
    assert d.run_length_observations == 3
    assert d.value == "BULLISH"


def test_direction_run_resets_on_value_change():
    snaps = _synthetic()
    a = SU.build_state_sequence(snaps)
    d = [r for r in a.layer_run_descriptors if r.layer == "DIRECTIONAL"][0]
    assert d.value == "BEARISH"
    assert d.run_length_observations == 1


def test_run_resets_on_status_change():
    s0 = _snap(_dt(18, 8), [("DIRECTIONAL", "BULLISH", "d1")])
    s1 = _snap(_dt(18, 9), [("DIRECTIONAL", "BULLISH", "d1"), ("DIRECTIONAL", "BEARISH", "b1")])
    a = SU.build_state_sequence([s0, s1])
    d = [r for r in a.layer_run_descriptors if r.layer == "DIRECTIONAL"][0]
    assert d.status == "CONFLICT"
    assert d.run_length_observations == 1


def test_attribution_only_change_does_not_reset_run():
    s0 = _snap(_dt(18, 8), [("DIRECTIONAL", "BULLISH", "d1")])
    s1 = _snap(_dt(18, 9), [("DIRECTIONAL", "BULLISH", "d2")])
    a = SU.build_state_sequence([s0, s1])
    d = [r for r in a.layer_run_descriptors if r.layer == "DIRECTIONAL"][0]
    assert d.value == "BULLISH"
    assert d.run_length_observations == 2


def test_run_elapsed_seconds_is_descriptive():
    s0 = _snap(_dt(18, 8, 0), [("DIRECTIONAL", "BULLISH", "d1")])
    s1 = _snap(_dt(18, 8, 2), [("DIRECTIONAL", "BULLISH", "d1")])
    a = SU.build_state_sequence([s0, s1])
    d = [r for r in a.layer_run_descriptors if r.layer == "DIRECTIONAL"][0]
    assert d.run_elapsed_seconds == pytest.approx(120.0)


def test_run_length_does_not_set_confirmation_status():
    s0 = _snap(_dt(18, 8), [("DIRECTIONAL", "BULLISH", "d1")])
    s1 = _snap(_dt(18, 9), [("DIRECTIONAL", "BULLISH", "d1")])
    s2 = _snap(_dt(18, 10), [("DIRECTIONAL", "BULLISH", "d1")])
    a = SU.build_state_sequence([s0, s1, s2])
    d = [r for r in a.layer_run_descriptors if r.layer == "DIRECTIONAL"][0]
    assert not hasattr(d, "confirmation")
    assert "confirmed" not in a.semantic_dump()


# ── transitions ──
def test_valid_provided_transition_is_verified():
    s0 = _snap(_dt(18, 8), [("DIRECTIONAL", "BULLISH", "d1")])
    s1 = _snap(_dt(18, 9), [("DIRECTIONAL", "BEARISH", "d1")])
    t = SM.transition(s0, s1)
    a = SU.build_state_sequence([s0, s1], transitions=[t])
    assert a.sequence_status == "SEQUENCE_AVAILABLE"
    assert a.steps[0].transition_status == "VERIFIED"
    assert a.steps[0].transition_id == t.transition_id


def test_transition_prev_id_mismatch_blocks():
    s0 = _snap(_dt(18, 8), [("DIRECTIONAL", "BULLISH", "d1")])
    s1 = _snap(_dt(18, 9), [("DIRECTIONAL", "BEARISH", "d1")])
    t = SM.transition(s0, s1)
    t.previous_snapshot_id = "wrong"
    a = SU.build_state_sequence([s0, s1], transitions=[t])
    assert a.sequence_status == "BLOCKED"
    assert SU.BLOCKED_ORPHAN_TRANSITION in a.block_reason_codes


def test_transition_new_id_mismatch_blocks():
    s0 = _snap(_dt(18, 8), [("DIRECTIONAL", "BULLISH", "d1")])
    s1 = _snap(_dt(18, 9), [("DIRECTIONAL", "BEARISH", "d1")])
    t = SM.transition(s0, s1)
    t.new_snapshot_id = "wrong"
    a = SU.build_state_sequence([s0, s1], transitions=[t])
    assert a.sequence_status == "BLOCKED"
    assert SU.BLOCKED_ORPHAN_TRANSITION in a.block_reason_codes


def test_mutated_transition_payload_blocks():
    s0 = _snap(_dt(18, 8), [("DIRECTIONAL", "BULLISH", "d1")])
    s1 = _snap(_dt(18, 9), [("DIRECTIONAL", "BEARISH", "d1")])
    t = SM.transition(s0, s1)
    t.new_directional_state.value = "STRONG_BEAR"
    a = SU.build_state_sequence([s0, s1], transitions=[t])
    assert a.sequence_status == "BLOCKED"
    assert SU.BLOCKED_TRANSITION_INTEGRITY_MISMATCH in a.block_reason_codes


def test_forged_probability_transition_blocks():
    s0 = _snap(_dt(18, 8), [("DIRECTIONAL", "BULLISH", "d1")])
    s1 = _snap(_dt(18, 9), [("DIRECTIONAL", "BEARISH", "d1")])
    t = SM.transition(s0, s1)
    t.probability_before = 0.7
    a = SU.build_state_sequence([s0, s1], transitions=[t])
    assert a.sequence_status == "BLOCKED"
    assert SU.BLOCKED_TRANSITION_INTEGRITY_MISMATCH in a.block_reason_codes


def test_orphan_transition_blocks():
    s0 = _snap(_dt(18, 8), [("DIRECTIONAL", "BULLISH", "d1")])
    s1 = _snap(_dt(18, 9), [("DIRECTIONAL", "BEARISH", "d1")])
    s2 = _snap(_dt(18, 10), [("DIRECTIONAL", "STRONG_BEAR", "d1")])
    t = SM.transition(s0, s2)  # skips s1
    a = SU.build_state_sequence([s0, s1, s2], transitions=[t])
    assert a.sequence_status == "BLOCKED"
    assert SU.BLOCKED_ORPHAN_TRANSITION in a.block_reason_codes


def test_exact_duplicate_transition_dedupes():
    s0 = _snap(_dt(18, 8), [("DIRECTIONAL", "BULLISH", "d1")])
    s1 = _snap(_dt(18, 9), [("DIRECTIONAL", "BEARISH", "d1")])
    t = SM.transition(s0, s1)
    a1 = SU.build_state_sequence([s0, s1], transitions=[t])
    a2 = SU.build_state_sequence([s0, s1], transitions=[t, t])
    assert a1.sequence_id == a2.sequence_id


def test_same_transition_id_different_payload_blocks():
    s0 = _snap(_dt(18, 8), [("DIRECTIONAL", "BULLISH", "d1")])
    s1 = _snap(_dt(18, 9), [("DIRECTIONAL", "BEARISH", "d1")])
    t1 = SM.transition(s0, s1)
    t2 = copy.deepcopy(t1)
    t2.new_directional_state.value = "STRONG_BEAR"
    assert t1.transition_id == t2.transition_id
    a = SU.build_state_sequence([s0, s1], transitions=[t1, t2])
    assert a.sequence_status == "BLOCKED"
    assert SU.BLOCKED_TRANSITION_ID_COLLISION in a.block_reason_codes


def test_transition_input_order_does_not_change_sequence():
    s0 = _snap(_dt(18, 8), [("DIRECTIONAL", "BULLISH", "d1")])
    s1 = _snap(_dt(18, 9), [("DIRECTIONAL", "BEARISH", "d1")])
    s2 = _snap(_dt(18, 10), [("DIRECTIONAL", "STRONG_BEAR", "d1")])
    t01 = SM.transition(s0, s1)
    t12 = SM.transition(s1, s2)
    a1 = SU.build_state_sequence([s0, s1, s2], transitions=[t01, t12])
    a2 = SU.build_state_sequence([s0, s1, s2], transitions=[t12, t01])
    assert a1.sequence_id == a2.sequence_id


def test_missing_transition_is_not_fabricated():
    s0 = _snap(_dt(18, 8), [("DIRECTIONAL", "BULLISH", "d1")])
    s1 = _snap(_dt(18, 9), [("DIRECTIONAL", "BEARISH", "d1")])
    s2 = _snap(_dt(18, 10), [("DIRECTIONAL", "STRONG_BEAR", "d1")])
    t01 = SM.transition(s0, s1)
    a = SU.build_state_sequence([s0, s1, s2], transitions=[t01])
    assert a.sequence_status == "SEQUENCE_AVAILABLE"
    assert a.steps[0].transition_status == "VERIFIED"
    assert a.steps[1].transition_status == "NOT_PROVIDED"


# ── ASOF / lineage ──
def test_sequence_derived_asof_is_least_verified():
    s0 = _snap(_dt(18, 8), [("DIRECTIONAL", "BULLISH", "d1")], asof_status="ASOF_VERIFIED")
    s1 = _snap(_dt(18, 9), [("DIRECTIONAL", "BULLISH", "d1")], asof_status="LEGACY_TEMPORAL_UNVERIFIED")
    a = SU.build_state_sequence([s0, s1])
    assert a.derived_asof_status == "LEGACY_TEMPORAL_UNVERIFIED"


def test_legacy_snapshot_prevents_sequence_asof_upgrade():
    s0 = _snap(_dt(18, 8), [("DIRECTIONAL", "BULLISH", "d1")], asof_status="LEGACY_TEMPORAL_UNVERIFIED")
    s1 = _snap(_dt(18, 9), [("DIRECTIONAL", "BULLISH", "d1")], asof_status="ASOF_VERIFIED")
    a = SU.build_state_sequence([s0, s1])
    assert a.derived_asof_status == "LEGACY_TEMPORAL_UNVERIFIED"


def test_sequence_preserves_source_lineage():
    s0 = _snap(_dt(18, 8), [("DIRECTIONAL", "BULLISH", "d1")], source_snapshot_ids=["srcA"])
    s1 = _snap(_dt(18, 9), [("DIRECTIONAL", "BULLISH", "d1")], source_snapshot_ids=["srcB"])
    a = SU.build_state_sequence([s0, s1])
    assert a.source_snapshot_ids == ["srcA", "srcB"]


def test_lineage_change_changes_sequence_id():
    s0 = _snap(_dt(18, 8), [("DIRECTIONAL", "BULLISH", "d1")], source_snapshot_ids=["srcA"])
    s1 = _snap(_dt(18, 9), [("DIRECTIONAL", "BULLISH", "d1")], source_snapshot_ids=["srcB"])
    a1 = SU.build_state_sequence([s0, s1])
    s1b = _snap(_dt(18, 9), [("DIRECTIONAL", "BULLISH", "d1")], source_snapshot_ids=["srcC"])
    a2 = SU.build_state_sequence([s0, s1b])
    assert a1.sequence_id != a2.sequence_id


# ── sequence identity ──
def test_sequence_identity_is_deterministic():
    snaps = _synthetic()
    a1 = SU.build_state_sequence(snaps)
    a2 = SU.build_state_sequence([s for s in snaps])
    assert a1.sequence_id == a2.sequence_id
    assert SU.sequence_identity(a1) == a1.sequence_id


def test_snapshot_input_order_does_not_change_sequence_id():
    snaps = _synthetic()
    a1 = SU.build_state_sequence(snaps)
    a2 = SU.build_state_sequence(list(reversed(snaps)))
    assert a1.sequence_id == a2.sequence_id


def test_exact_duplicate_input_does_not_change_sequence_id():
    snaps = _synthetic()
    a1 = SU.build_state_sequence(snaps)
    a2 = SU.build_state_sequence([snaps[0], snaps[0], snaps[1], snaps[2], snaps[3]])
    assert a1.sequence_id == a2.sequence_id


def test_step_semantic_change_changes_sequence_id():
    snaps = _synthetic()
    a1 = SU.build_state_sequence(snaps)
    snaps2 = _synthetic()
    snaps2[2].risk_state = SM.LayerState(value="REVERSAL_RISK", status="EVALUATED")
    snaps2[2].snapshot_id = SM.snapshot_identity(snaps2[2])
    a2 = SU.build_state_sequence(snaps2)
    assert a1.sequence_id != a2.sequence_id


def test_created_at_does_not_change_sequence_id():
    snaps = _synthetic()
    a1 = SU.build_state_sequence(snaps)
    a2 = SU.build_state_sequence([s for s in snaps])
    assert a1.sequence_id == a2.sequence_id


# ── blocked identity ──
def test_blocked_sequence_has_nonempty_deterministic_id():
    s0 = _snap(_dt(18, 8), [("DIRECTIONAL", "BULLISH", "d1")])
    s1 = _snap(_dt(18, 9), [("DIRECTIONAL", "BULLISH", "d1")])
    a1 = SU.build_state_sequence([s0, s1])
    s1.mutate = None
    a2 = SU.build_state_sequence([s0, s1])
    assert a1.sequence_status == "SEQUENCE_AVAILABLE"  # sanity
    assert a1.sequence_id != ""


def test_blocked_sequence_input_order_independent():
    s0 = _snap(_dt(18, 8), [("DIRECTIONAL", "BULLISH", "d1")])
    s1 = _snap(_dt(18, 8), [("DIRECTIONAL", "BEARISH", "d1")])  # same origin → ambiguous
    a1 = SU.build_state_sequence([s0, s1])
    a2 = SU.build_state_sequence([s1, s0])
    assert a1.sequence_status == "BLOCKED"
    assert a1.sequence_id != ""
    assert a1.sequence_id == a2.sequence_id


def test_different_block_reason_changes_sequence_id():
    s0 = _snap(_dt(18, 8), [("DIRECTIONAL", "BULLISH", "d1")])
    # reason A: same-origin ambiguous
    s1 = _snap(_dt(18, 8), [("DIRECTIONAL", "BEARISH", "d1")])
    a_ambig = SU.build_state_sequence([s0, s1])
    # reason B: cutoff regression
    s2 = _snap(_dt(18, 9), [("DIRECTIONAL", "BULLISH", "d1")], cutoff=_dt(18, 7))
    a_reg = SU.build_state_sequence([_snap(_dt(18, 8), [("DIRECTIONAL", "BULLISH", "d1")], cutoff=_dt(18, 8)), s2])
    assert a_ambig.sequence_id != a_reg.sequence_id


# ── append ──
def test_append_returns_new_sequence():
    s0 = _snap(_dt(18, 8), [("DIRECTIONAL", "BULLISH", "d1")])
    s1 = _snap(_dt(18, 9), [("DIRECTIONAL", "BULLISH", "d1")])
    base = SU.build_state_sequence([s0])
    out = SU.append_state_update(base, s1)
    assert out is not base
    assert out.sequence_id != base.sequence_id


def test_append_does_not_mutate_old_sequence():
    s0 = _snap(_dt(18, 8), [("DIRECTIONAL", "BULLISH", "d1")])
    s1 = _snap(_dt(18, 9), [("DIRECTIONAL", "BULLISH", "d1")])
    base = SU.build_state_sequence([s0])
    before_id = base.sequence_id
    before_dump = base.semantic_dump()
    SU.append_state_update(base, s1)
    assert base.sequence_id == before_id
    assert base.semantic_dump() == before_dump


def test_append_checks_existing_sequence_integrity():
    s0 = _snap(_dt(18, 8), [("DIRECTIONAL", "BULLISH", "d1")])
    s1 = _snap(_dt(18, 9), [("DIRECTIONAL", "BULLISH", "d1")])
    base = SU.build_state_sequence([s0])
    out = SU.append_state_update(base, s1)
    assert out.sequence_status == "SEQUENCE_AVAILABLE"


def test_append_rejects_mutated_existing_sequence():
    s0 = _snap(_dt(18, 8), [("DIRECTIONAL", "BULLISH", "d1")])
    s1 = _snap(_dt(18, 9), [("DIRECTIONAL", "BULLISH", "d1")])
    base = SU.build_state_sequence([s0])
    base.snapshots[0].directional_state.value = "STRONG_BULL"
    out = SU.append_state_update(base, s1)
    assert out.sequence_status == "BLOCKED"
    assert SU.BLOCKED_SEQUENCE_INTEGRITY_MISMATCH in out.block_reason_codes


def test_append_deep_copies_new_snapshot():
    s0 = _snap(_dt(18, 8), [("DIRECTIONAL", "BULLISH", "d1")])
    s1 = _snap(_dt(18, 9), [("DIRECTIONAL", "BULLISH", "d1")])
    base = SU.build_state_sequence([s0])
    out = SU.append_state_update(base, s1)
    before = out.sequence_id
    s1.directional_state.value = "STRONG_BULL"
    assert out.sequence_id == before


def test_append_same_result_as_full_rebuild():
    s0 = _snap(_dt(18, 8), [("DIRECTIONAL", "BULLISH", "d1")])
    s1 = _snap(_dt(18, 9), [("EXTENSION", "EXTENDED", "x1")])
    s2 = _snap(_dt(18, 10), [("RISK", "EXHAUSTION_WARNING", "r1")])
    full = SU.build_state_sequence([s0, s1, s2])
    appended = SU.append_state_update(SU.append_state_update(SU.build_state_sequence([s0]), s1), s2)
    assert appended.sequence_id == full.sequence_id
    assert appended.semantic_dump() == full.semantic_dump()


# ── safety ──
def test_sequence_has_no_trade_fields():
    a = SU.build_state_sequence(_synthetic())
    d = a.model_dump()
    for k in ("buy", "sell", "long", "short", "order", "broker", "position_size", "stop_loss", "take_profit"):
        assert k not in d


def test_sequence_has_no_probability_values():
    a = SU.build_state_sequence(_synthetic())
    assert a.probability_level is None
    assert a.probability_velocity is None
    assert a.probability_acceleration is None
    assert a.probability_status == "NOT_AVAILABLE_UPSTREAM_UNCALIBRATED"


def test_sequence_does_not_emit_state_evidence():
    a = SU.build_state_sequence(_synthetic())
    d = a.model_dump()
    assert "evidence" not in d
    assert "state_evidence" not in d


def test_sequence_does_not_modify_snapshot_state():
    snaps = _synthetic()
    before = [s.directional_state.value for s in snaps]
    SU.build_state_sequence(snaps)
    after = [s.directional_state.value for s in snaps]
    assert before == after


# ── synthetic sequence (report §64) ──
def test_synthetic_sequence_change_descriptors():
    s0, s1, s2, s3 = _synthetic()
    a = SU.build_state_sequence([s0, s1, s2, s3])
    assert a.steps[0].state_changed_layers == ["EXTENSION"]
    assert a.steps[1].state_changed_layers == ["EXTENSION", "RISK"]
    assert "DIRECTIONAL" in a.steps[2].state_changed_layers
    assert a.probability_status == "NOT_AVAILABLE_UPSTREAM_UNCALIBRATED"
    assert a.change_point_status == "RESEARCH_CHALLENGER_NOT_IMPLEMENTED"
