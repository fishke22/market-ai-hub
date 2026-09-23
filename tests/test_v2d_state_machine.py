"""Phase V2-D — dynamic state machine scaffold tests."""
from __future__ import annotations

import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, "src")

from market_ai_hub.research.v2 import state_machine as SM


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
                source_type="TYPED_EVIDENCE", provenance_status="VERIFIED_INPUT")
    base.update(kw)
    return SM.StateEvidence(**base)


# ── schema / default truth ──
def test_schema_version():
    assert SM.V2_STATE_MACHINE_SCHEMA_VERSION == "2D.1"


def test_no_evidence_all_layers_none_not_evaluated():
    s = SM.compose_state_snapshot(_ctx(), [])
    assert s.directional_state.value is None and s.directional_state.status == "NOT_EVALUATED"
    assert s.extension_state.value is None and s.extension_state.status == "NOT_EVALUATED"
    assert s.risk_state.value is None and s.risk_state.status == "NOT_EVALUATED"
    assert s.chase_risk_state.value is None and s.chase_risk_state.status == "NOT_EVALUATED"


def test_no_evidence_does_not_default_to_neutral_normal_allow():
    s = SM.compose_state_snapshot(_ctx(), [])
    assert s.directional_state.value != "NEUTRAL"
    assert s.extension_state.value != "NORMAL"
    assert s.risk_state.value != "NORMAL"
    assert s.chase_risk_state.value != "ALLOW"


# ── layer value validation ──
def test_valid_direction_accepted():
    ev = _ev("DIRECTIONAL", "BULLISH")
    assert SM.validate_state_evidence(ev, _ctx()) == []


def test_invalid_direction_rejected():
    with pytest.raises(ValueError):
        _ev("DIRECTIONAL", "NOT_A_DIRECTION")


def test_legacy_buy_zone_cannot_enter_direction():
    with pytest.raises(ValueError):
        _ev("DIRECTIONAL", "BUY_ZONE")


def test_legacy_research_state_not_silently_mapped():
    # BULLISH_EVIDENCE is a ResearchState value, NOT a V2-D Direction value
    with pytest.raises(ValueError):
        _ev("DIRECTIONAL", "BULLISH_EVIDENCE")


def test_structural_bullish_rejected():
    with pytest.raises(ValueError):
        _ev("STRUCTURAL", "BULLISH")


def test_chase_stop_valid():
    assert _ev("CHASE_RISK", "STOP").value == "STOP"


# ── layer independence / STOP != SHORT ──
def test_direction_bullish_chase_stop_is_legal():
    evs = [_ev("DIRECTIONAL", "BULLISH", "d1"), _ev("CHASE_RISK", "STOP", "c1")]
    s = SM.compose_state_snapshot(_ctx(), evs)
    assert s.directional_state.value == "BULLISH"
    assert s.chase_risk_state.value == "STOP"


def test_chase_stop_is_not_short():
    evs = [_ev("DIRECTIONAL", "BULLISH", "d1"), _ev("CHASE_RISK", "STOP", "c1")]
    s = SM.compose_state_snapshot(_ctx(), evs)
    d = s.model_dump()
    for k in ("short", "sell", "trade_instruction", "position", "order", "long_signal", "short_signal"):
        assert k not in d
    assert s.directional_state.value == "BULLISH"  # STOP did not flip Direction


def test_bearish_allow_legal():
    evs = [_ev("DIRECTIONAL", "BEARISH", "d1"), _ev("CHASE_RISK", "ALLOW", "c1")]
    s = SM.compose_state_snapshot(_ctx(), evs)
    assert s.directional_state.value == "BEARISH"
    assert s.chase_risk_state.value == "ALLOW"


# ── evidence composition ──
def test_one_trusted_evidence_evaluated():
    s = SM.compose_state_snapshot(_ctx(), [_ev("DIRECTIONAL", "BULLISH")])
    assert s.directional_state.value == "BULLISH"
    assert s.directional_state.status == "EVALUATED"


def test_two_same_trusted_evaluated():
    evs = [_ev("DIRECTIONAL", "BULLISH", "d1"), _ev("DIRECTIONAL", "BULLISH", "d2")]
    s = SM.compose_state_snapshot(_ctx(), evs)
    assert s.directional_state.value == "BULLISH"
    assert set(s.directional_state.evidence_ids) == {"d1", "d2"}


def test_conflicting_direction_evidence_fails_closed():
    evs = [_ev("DIRECTIONAL", "BULLISH", "d1"), _ev("DIRECTIONAL", "BEARISH", "d2")]
    s = SM.compose_state_snapshot(_ctx(), evs)
    assert s.directional_state.value is None
    assert s.directional_state.status == "CONFLICT"


def test_conflict_in_direction_does_not_erase_structural():
    evs = [_ev("DIRECTIONAL", "BULLISH", "d1"), _ev("DIRECTIONAL", "BEARISH", "d2"),
           _ev("STRUCTURAL", "ACCEPTANCE_CONFIRMED", "s1")]
    s = SM.compose_state_snapshot(_ctx(), evs)
    assert s.directional_state.status == "CONFLICT"
    assert s.structural_state.value == "ACCEPTANCE_CONFIRMED"
    assert s.structural_state.status == "EVALUATED"


def test_unverified_evidence_cannot_publish_evaluated_state():
    ev = _ev("DIRECTIONAL", "BULLISH", "d1", provenance_status="UNKNOWN")
    s = SM.compose_state_snapshot(_ctx(), [ev])
    assert s.directional_state.value is None
    assert s.directional_state.status == "UNVERIFIED"


# ── temporal leakage ──
def test_naive_evidence_timestamp_rejects():
    with pytest.raises(ValueError):
        _ev("DIRECTIONAL", "BULLISH", event_timestamp=datetime(2026, 9, 18, 0, 0))


def test_available_at_after_cutoff_blocks():
    ev = _ev("DIRECTIONAL", "BULLISH", available_at=_dt(18, 9, 0))
    s = SM.compose_state_snapshot(_ctx(feature_cutoff_timestamp=_dt(18, 8, 0)), [ev])
    assert s.snapshot_status == "BLOCKED"
    assert s.directional_state.reason_codes == [SM.BLOCKED_FUTURE_EVIDENCE]


def test_event_timestamp_after_cutoff_blocks():
    ev = _ev("DIRECTIONAL", "BULLISH", event_timestamp=_dt(18, 9, 0))
    s = SM.compose_state_snapshot(_ctx(), [ev])
    assert s.snapshot_status == "BLOCKED"
    assert s.directional_state.reason_codes == [SM.BLOCKED_FUTURE_EVIDENCE]


def test_cutoff_after_origin_blocks():
    s = SM.compose_state_snapshot(_ctx(feature_cutoff_timestamp=_dt(18, 9, 0), state_origin=_dt(18, 8, 0)), [])
    assert s.snapshot_status == "BLOCKED"


# ── V2-C anti-leakage ──
def test_future_v2c_outcome_cannot_leak_into_original_forecast_state():
    ev = _ev("STRUCTURAL", "ACCEPTANCE_CONFIRMED", "s1",
             source_type="V2C_OUTCOME", settled_at=_dt(20, 0, 0),
             source_forecast_origin=_dt(18, 0, 0), label_schema_version="2C.2")
    s = SM.compose_state_snapshot(_ctx(feature_cutoff_timestamp=_dt(18, 8, 0)), [ev])
    assert s.snapshot_status == "BLOCKED"
    assert s.structural_state.reason_codes == [SM.BLOCKED_FUTURE_OUTCOME_EVIDENCE]


def test_settled_v2c_outcome_within_cutoff_passes_validation():
    ev = _ev("STRUCTURAL", "ACCEPTANCE_CONFIRMED", "s1",
             source_type="V2C_OUTCOME", settled_at=_dt(18, 7, 0),
             event_timestamp=_dt(18, 6, 0),
             source_forecast_origin=_dt(18, 0, 0), label_schema_version="2C.2")
    assert SM.validate_state_evidence(ev, _ctx(feature_cutoff_timestamp=_dt(18, 8, 0))) == []


def test_no_automatic_touch_to_breakout_mapping():
    # touch/break bool labels are NOT Structural values; there is no mapping function
    with pytest.raises(ValueError):
        _ev("STRUCTURAL", "TOUCH")
    assert not hasattr(SM, "map_touch_to_structural")
    assert not hasattr(SM, "map_acceptance_to_structural")


# ── identity isolation ──
@pytest.mark.parametrize("kw,field", [
    ({"instrument": "3706.TW"}, "instrument"),
    ({"target_family": "TAIWAN_STOCK"}, "target_family"),
    ({"instrument_role": "PROXY"}, "instrument_role"),
    ({"calendar_id": "XTKS"}, "calendar_id"),
    ({"frequency": "DAILY", "horizon": "5d"}, "horizon"),
])
def test_identity_mismatch_blocks(kw, field):
    ev = _ev("DIRECTIONAL", "BULLISH", **kw)
    s = SM.compose_state_snapshot(_ctx(), [ev])
    assert s.snapshot_status == "BLOCKED"
    assert s.directional_state.reason_codes == [SM.BLOCKED_IDENTITY_MISMATCH]


def test_unsupported_frequency_rejected():
    with pytest.raises(ValueError):
        _ctx(frequency="5M")


# ── multi-horizon ──
def test_multi_horizon_snapshots_independent():
    s1 = SM.compose_state_snapshot(_ctx(horizon="1d"), [_ev("DIRECTIONAL", "BULLISH", "d1", horizon="1d")])
    s5 = SM.compose_state_snapshot(_ctx(horizon="5d"), [_ev("DIRECTIONAL", "NEUTRAL", "d2", horizon="5d")])
    assert s1.horizon == "1d" and s1.directional_state.value == "BULLISH"
    assert s5.horizon == "5d" and s5.directional_state.value == "NEUTRAL"


def test_cross_horizon_transition_rejected():
    s1 = SM.compose_state_snapshot(_ctx(horizon="1d"), [_ev("DIRECTIONAL", "BULLISH", "d1", horizon="1d")])
    s5 = SM.compose_state_snapshot(_ctx(horizon="5d", state_origin=_dt(18, 9, 0)),
                                   [_ev("DIRECTIONAL", "NEUTRAL", "d2", horizon="5d")])
    with pytest.raises(ValueError):
        SM.transition(s1, s5)


# ── ASOF ──
def test_legacy_evidence_does_not_become_asof_verified():
    ev = _ev("DIRECTIONAL", "BULLISH", "d1", asof_status="LEGACY_TEMPORAL_UNVERIFIED")
    s = SM.compose_state_snapshot(_ctx(asof_status="ASOF_VERIFIED"), [ev])
    assert s.context_asof_status == "ASOF_VERIFIED"
    assert s.derived_asof_status == "LEGACY_TEMPORAL_UNVERIFIED"


def test_mixed_verified_legacy_conservative_summary():
    ev1 = _ev("DIRECTIONAL", "BULLISH", "d1", asof_status="ASOF_VERIFIED")
    ev2 = _ev("STRUCTURAL", "ACCEPTANCE_CONFIRMED", "s1", asof_status="LEGACY_TEMPORAL_UNVERIFIED")
    s = SM.compose_state_snapshot(_ctx(asof_status="ASOF_VERIFIED"), [ev1, ev2])
    assert s.derived_asof_status == "LEGACY_TEMPORAL_UNVERIFIED"


# ── IDs ──
def test_snapshot_identity_is_deterministic():
    evs = [_ev("DIRECTIONAL", "BULLISH", "d1"), _ev("CHASE_RISK", "STOP", "c1")]
    s1 = SM.compose_state_snapshot(_ctx(), evs)
    s2 = SM.compose_state_snapshot(_ctx(), evs)
    assert s1.snapshot_id == s2.snapshot_id


def test_evidence_order_does_not_change_snapshot_id():
    evs1 = [_ev("DIRECTIONAL", "BULLISH", "d1"), _ev("CHASE_RISK", "STOP", "c1")]
    evs2 = [_ev("CHASE_RISK", "STOP", "c1"), _ev("DIRECTIONAL", "BULLISH", "d1")]
    s1 = SM.compose_state_snapshot(_ctx(), evs1)
    s2 = SM.compose_state_snapshot(_ctx(), evs2)
    assert s1.snapshot_id == s2.snapshot_id


def test_same_evidence_id_different_payload_blocks():
    ev1 = _ev("DIRECTIONAL", "BULLISH", "d1")
    ev2 = _ev("DIRECTIONAL", "BEARISH", "d1")  # same id, different value
    s = SM.compose_state_snapshot(_ctx(), [ev1, ev2])
    assert s.snapshot_status == "BLOCKED"
    assert s.directional_state.reason_codes == [SM.BLOCKED_EVIDENCE_ID_COLLISION]


# ── transition ──
def test_initial_transition_works():
    s = SM.compose_state_snapshot(_ctx(), [_ev("DIRECTIONAL", "BULLISH", "d1")])
    t = SM.transition(None, s)
    assert t.new_snapshot_id == s.snapshot_id
    assert t.probability_status == "NOT_AVAILABLE"


def test_same_states_no_changed_layers():
    evs = [_ev("DIRECTIONAL", "BULLISH", "d1")]
    s1 = SM.compose_state_snapshot(_ctx(state_origin=_dt(18, 8, 0)), evs)
    s2 = SM.compose_state_snapshot(_ctx(state_origin=_dt(18, 9, 0)), evs)
    t = SM.transition(s1, s2)
    assert t.changed_layers == []


def test_one_layer_change_only_that_layer_listed():
    s1 = SM.compose_state_snapshot(_ctx(state_origin=_dt(18, 8, 0)), [_ev("DIRECTIONAL", "BULLISH", "d1")])
    s2 = SM.compose_state_snapshot(_ctx(state_origin=_dt(18, 9, 0)),
                                   [_ev("DIRECTIONAL", "BULLISH", "d1"), _ev("CHASE_RISK", "STOP", "c1")])
    t = SM.transition(s1, s2)
    assert t.changed_layers == ["CHASE_RISK"]


def test_backward_time_transition_blocks():
    s1 = SM.compose_state_snapshot(_ctx(state_origin=_dt(18, 9, 0)), [_ev("DIRECTIONAL", "BULLISH", "d1")])
    s2 = SM.compose_state_snapshot(_ctx(state_origin=_dt(18, 8, 0)), [_ev("DIRECTIONAL", "BULLISH", "d1")])
    with pytest.raises(ValueError):
        SM.transition(s1, s2)


def test_cross_target_transition_blocks():
    s1 = SM.compose_state_snapshot(_ctx(), [_ev("DIRECTIONAL", "BULLISH", "d1")])
    s2 = SM.compose_state_snapshot(_ctx(instrument="3706.TW", target_family="TAIWAN_STOCK",
                                        calendar_id="XTAI", state_origin=_dt(18, 9, 0)),
                                   [_ev("DIRECTIONAL", "BULLISH", "d1", instrument="3706.TW",
                                        target_family="TAIWAN_STOCK", calendar_id="XTAI")])
    with pytest.raises(ValueError):
        SM.transition(s1, s2)


def test_transition_probability_not_available():
    s1 = SM.compose_state_snapshot(_ctx(state_origin=_dt(18, 8, 0)), [_ev("DIRECTIONAL", "BULLISH", "d1")])
    s2 = SM.compose_state_snapshot(_ctx(state_origin=_dt(18, 9, 0)), [_ev("DIRECTIONAL", "BEARISH", "d1")])
    t = SM.transition(s1, s2)
    assert t.probability_before is None
    assert t.probability_after is None
    assert t.probability_status == "NOT_AVAILABLE"


def test_no_trade_fields():
    s = SM.compose_state_snapshot(_ctx(), [_ev("DIRECTIONAL", "BULLISH", "d1")])
    d = s.model_dump()
    for k in ("trade_instruction", "position", "order", "entry_price", "stop_loss", "take_profit", "size"):
        assert k not in d


# ── persistence ──
def test_persistence_policy_default_not_configured():
    p = SM.StatePersistencePolicy()
    assert p.status == "NOT_CONFIGURED"
    assert p.validation_status == "HYPOTHESIS_ONLY"
    assert p.minimum_dwell_time_seconds is None
    assert p.hysteresis is None
