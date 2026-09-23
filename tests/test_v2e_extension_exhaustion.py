"""Phase V2-E — daily extension / exhaustion research engine tests."""
from __future__ import annotations

import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, "src")

from market_ai_hub.research.v2 import extension_exhaustion as E
from market_ai_hub.research.v2.state_machine import StateEvaluationContext, StateEvidence, compose_state_snapshot


def _dt(d, h=0, m=0):
    return datetime(2026, 9, d, h, m, tzinfo=timezone.utc)


def _ctx(**kw):
    base = dict(instrument="JNU", target_family="OSAKA_MICRO", instrument_role="DIRECT",
                calendar_id="OSE_DERIVATIVES", frequency="DAILY", horizon="1d",
                feature_cutoff_timestamp=_dt(18, 8, 0), state_origin=_dt(18, 8, 0))
    base.update(kw)
    return StateEvaluationContext(**base)


def _scalar(name, value, event, available, **kw):
    base = dict(name=name, value=value, event_timestamp=event, available_at=available,
                source_type="M", source_schema_version="v1", source_version="v1",
                provenance_status="VERIFIED_INPUT")
    base.update(kw)
    return E.PointInTimeScalar(**base)


def _prev_close(v=100.0):
    return _scalar("previous_close", v, _dt(17, 7, 0), _dt(17, 8, 0))


def _curr_close(v=101.0):
    return _scalar("current_close", v, _dt(18, 7, 0), _dt(18, 7, 30))


def _atr(v=2.0):
    return _scalar("atr_baseline", v, _dt(17, 6, 0), _dt(17, 6, 30))


def _ext(curr=101.0, prev=100.0, atr=2.0, roll="NONE", series="CONTRACT", **kw):
    return E.evaluate_extension(_ctx(), _curr_close(curr), _prev_close(prev), _atr(atr),
                                roll_status=roll, series_semantics=series, **kw)


def _comp(cid, family, present=True, **kw):
    base = dict(component_id=cid, family=family, present=present,
                instrument="JNU", target_family="OSAKA_MICRO", instrument_role="DIRECT",
                calendar_id="OSE_DERIVATIVES", frequency="DAILY", horizon="1d",
                event_timestamp=_dt(18, 0, 0), available_at=_dt(18, 7, 0),
                source_type="M", source_schema_version="v1", source_version="v1",
                provenance_status="VERIFIED_INPUT")
    base.update(kw)
    return E.ExhaustionComponentEvidence(**base)


# ── schema ──
def test_schema():
    assert E.V2_EXTENSION_EXHAUSTION_SCHEMA_VERSION == "2E.1"


def test_policy_hypothesis_only_not_optimized():
    p = E.DailyExtensionPolicy()
    assert p.validation_status == "HYPOTHESIS_ONLY"
    assert p.optimization_status == "NOT_OPTIMIZED"


# ── extension math ──
def test_positive_signed_extension():
    a = _ext(curr=103.0)
    assert a.signed_extension_units == pytest.approx(1.5)
    assert a.extension_side == "UP"


def test_negative_signed_extension():
    a = _ext(curr=97.0)
    assert a.signed_extension_units == pytest.approx(-1.5)
    assert a.extension_side == "DOWN"


def test_absolute_units():
    a = _ext(curr=97.0)
    assert a.absolute_extension_units == pytest.approx(1.5)


def test_normal_below_1():
    assert _ext(curr=101.0).extension_state == "NORMAL"  # 0.5 units


def test_exact_1_extended():
    assert _ext(curr=102.0).extension_state == "EXTENDED"  # 1.0 units


def test_just_below_2_extended():
    assert _ext(curr=103.9).extension_state == "EXTENDED"  # 1.95 units


def test_exact_2_extreme():
    assert _ext(curr=104.0).extension_state == "EXTREME"  # 2.0 units


def test_above_2_extreme():
    assert _ext(curr=105.0).extension_state == "EXTREME"  # 2.5 units


# ── input quality ──
@pytest.mark.parametrize("atr", [float("nan"), float("inf")])
def test_atr_nonfinite_rejected(atr):
    with pytest.raises(ValueError):
        _atr(atr)


def test_atr_zero_blocks():
    a = _ext(atr=0.0)
    assert a.assessment_status == "BLOCKED"
    assert "INVALID_INPUT" in a.block_reason_codes


def test_atr_negative_blocks():
    a = _ext(atr=-1.0)
    assert a.assessment_status == "BLOCKED"


def test_current_price_invalid_blocks():
    a = _ext(curr=0.0)
    assert a.assessment_status == "BLOCKED"


def test_reference_price_invalid_blocks():
    a = _ext(prev=-1.0)
    assert a.assessment_status == "BLOCKED"


# ── temporal ──
def test_event_after_available_blocks():
    cc = _scalar("current_close", 101.0, _dt(18, 8, 0), _dt(18, 7, 0))  # event > available
    a = E.evaluate_extension(_ctx(), cc, _prev_close(), _atr(), roll_status="NONE")
    assert a.assessment_status == "BLOCKED"


def test_available_after_cutoff_blocks():
    cc = _scalar("current_close", 101.0, _dt(18, 8, 30), _dt(18, 8, 30))  # available > cutoff 08:00
    a = E.evaluate_extension(_ctx(), cc, _prev_close(), _atr(), roll_status="NONE")
    assert a.assessment_status == "BLOCKED"


def test_previous_close_event_not_before_current_close_blocks():
    # previous close event == current close event (not strictly <)
    pc = _scalar("previous_close", 100.0, _dt(18, 7, 0), _dt(18, 7, 30))
    cc = _scalar("current_close", 101.0, _dt(18, 7, 0), _dt(18, 7, 30))
    a = E.evaluate_extension(_ctx(), cc, pc, _atr(), roll_status="NONE")
    assert a.assessment_status == "BLOCKED"


def test_atr_baseline_event_after_previous_close_blocks():
    atr = _scalar("atr_baseline", 2.0, _dt(18, 0, 0), _dt(18, 0, 30))  # atr after previous close (17th)
    a = E.evaluate_extension(_ctx(), _curr_close(), _prev_close(), atr, roll_status="NONE")
    assert a.assessment_status == "BLOCKED"


# ── provenance ──
def test_unknown_provenance_gives_unverified():
    cc = _scalar("current_close", 101.0, _dt(18, 7, 0), _dt(18, 7, 30), provenance_status="UNKNOWN")
    a = E.evaluate_extension(_ctx(), cc, _prev_close(), _atr(), roll_status="NONE")
    assert a.assessment_status == "UNVERIFIED"
    assert a.extension_state is None


def test_malformed_source_identity_blocks():
    cc = _scalar("current_close", 101.0, _dt(18, 7, 0), _dt(18, 7, 30), source_type="")
    a = E.evaluate_extension(_ctx(), cc, _prev_close(), _atr(), roll_status="NONE")
    assert a.assessment_status == "BLOCKED"


def test_legacy_asof_not_promoted():
    a = _ext()
    assert a.derived_asof_status == "LEGACY_TEMPORAL_UNVERIFIED"
    assert a.derived_asof_status != "ASOF_VERIFIED"


# ── roll ──
def test_futures_unknown_roll_blocks_extension():
    a = _ext(roll="UNKNOWN")
    assert a.assessment_status == "BLOCKED"
    assert a.block_reason_codes == ["BLOCKED_ROLL_PROVENANCE"]


def test_futures_roll_boundary_blocks():
    a = _ext(roll="ROLL_BOUNDARY")
    assert a.assessment_status == "BLOCKED"


def test_futures_none_works():
    a = _ext(roll="NONE")
    assert a.assessment_status == "EVALUATED"


# ── exhaustion ──
def test_extreme_extension_alone_is_not_exhaustion():
    ext = _ext(curr=105.0)  # EXTREME
    a = E.evaluate_exhaustion(ext, [], _ctx())
    assert a.assessment_status == "INSUFFICIENT_CONFIRMATION"
    assert a.warning_established is False


def test_single_oscillator_cannot_establish_exhaustion():
    ext = _ext(curr=105.0)
    a = E.evaluate_exhaustion(ext, [_comp("r1", "OSCILLATOR_EXTREME")], _ctx())
    assert a.assessment_status == "INSUFFICIENT_CONFIRMATION"


def test_duplicate_oscillator_family_cannot_inflate_confirmation_count():
    ext = _ext(curr=105.0)
    comps = [_comp("r1", "OSCILLATOR_EXTREME"), _comp("r2", "OSCILLATOR_EXTREME")]
    a = E.evaluate_exhaustion(ext, comps, _ctx())
    assert a.confirmation_family_count == 1
    assert a.assessment_status == "INSUFFICIENT_CONFIRMATION"


def test_exhaustion_requires_two_distinct_confirmation_families():
    ext = _ext(curr=105.0)
    comps = [_comp("m1", "MOMENTUM_STALL"), _comp("d1", "PRICE_VOLUME_DIVERGENCE")]
    a = E.evaluate_exhaustion(ext, comps, _ctx())
    assert a.assessment_status == "WARNING_ESTABLISHED"
    assert a.warning_established is True
    assert set(a.positive_confirmation_families) == {"MOMENTUM_STALL", "PRICE_VOLUME_DIVERGENCE"}


def test_extension_normal_with_two_confirms_no_warning():
    ext = _ext(curr=101.0)  # NORMAL
    comps = [_comp("m1", "MOMENTUM_STALL"), _comp("d1", "PRICE_VOLUME_DIVERGENCE")]
    a = E.evaluate_exhaustion(ext, comps, _ctx())
    assert a.warning_established is False
    assert a.assessment_status == "INSUFFICIENT_CONFIRMATION"


def test_unverified_component_does_not_count():
    ext = _ext(curr=105.0)
    comps = [_comp("m1", "MOMENTUM_STALL"),
             _comp("r1", "OSCILLATOR_EXTREME", provenance_status="UNKNOWN")]
    a = E.evaluate_exhaustion(ext, comps, _ctx())
    assert a.confirmation_family_count == 1
    assert a.unverified_component_ids == ["r1"]
    assert a.assessment_status == "INSUFFICIENT_CONFIRMATION"


def test_conflicting_family_conflict():
    ext = _ext(curr=105.0)
    comps = [_comp("m1", "MOMENTUM_STALL", present=True),
             _comp("m2", "MOMENTUM_STALL", present=False)]
    a = E.evaluate_exhaustion(ext, comps, _ctx())
    assert a.assessment_status == "CONFLICT"
    assert a.conflict_families == ["MOMENTUM_STALL"]


def test_component_order_does_not_change_assessment():
    ext = _ext(curr=105.0)
    a1 = E.evaluate_exhaustion(ext, [_comp("m1", "MOMENTUM_STALL"), _comp("d1", "PRICE_VOLUME_DIVERGENCE")], _ctx())
    a2 = E.evaluate_exhaustion(ext, [_comp("d1", "PRICE_VOLUME_DIVERGENCE"), _comp("m1", "MOMENTUM_STALL")], _ctx())
    assert a1.assessment_id == a2.assessment_id


# ── state adapters ──
def test_extension_evident_evaluated_to_state_evidence():
    a = _ext(curr=104.0)
    ev = E.extension_to_state_evidence(a, _ctx())
    assert ev is not None
    assert ev.layer == "EXTENSION"
    assert ev.value == "EXTREME"
    assert ev.source_type == "V2E_EXTENSION"
    assert ev.source_schema_version == "2E.1"


def test_extension_unverified_no_state_evidence():
    cc = _scalar("current_close", 101.0, _dt(18, 7, 0), _dt(18, 7, 30), provenance_status="UNKNOWN")
    a = E.evaluate_extension(_ctx(), cc, _prev_close(), _atr(), roll_status="NONE")
    assert E.extension_to_state_evidence(a, _ctx()) is None


def test_warning_to_risk_evidence():
    ext = _ext(curr=105.0)
    a = E.evaluate_exhaustion(ext, [_comp("m1", "MOMENTUM_STALL"), _comp("d1", "PRICE_VOLUME_DIVERGENCE")], _ctx())
    ev = E.exhaustion_to_state_evidence(a, _ctx(), _dt(18, 7, 0), _dt(18, 7, 30))
    assert ev is not None
    assert ev.layer == "RISK"
    assert ev.value == "EXHAUSTION_WARNING"


def test_insufficient_confirmation_no_risk_normal_evidence():
    ext = _ext(curr=105.0)
    a = E.evaluate_exhaustion(ext, [_comp("r1", "OSCILLATOR_EXTREME")], _ctx())
    assert E.exhaustion_to_state_evidence(a, _ctx(), _dt(18, 7, 0), _dt(18, 7, 30)) is None


# ── V2-D integration: exhaustion warning does not alter Direction / CHASE / REVERSAL ──
def test_exhaustion_warning_does_not_change_direction():
    ext = _ext(curr=105.0)
    a = E.evaluate_exhaustion(ext, [_comp("m1", "MOMENTUM_STALL"), _comp("d1", "PRICE_VOLUME_DIVERGENCE")], _ctx())
    risk_ev = E.exhaustion_to_state_evidence(a, _ctx(), _dt(18, 7, 0), _dt(18, 7, 30))
    dir_ev = StateEvidence(evidence_id="d1", layer="DIRECTIONAL", value="BULLISH",
                           instrument="JNU", target_family="OSAKA_MICRO", calendar_id="OSE_DERIVATIVES",
                           frequency="DAILY", horizon="1d", event_timestamp=_dt(18, 0, 0), available_at=_dt(18, 7, 0),
                           source_type="M", source_schema_version="v1", source_version="v1",
                           provenance_status="VERIFIED_INPUT")
    snap = compose_state_snapshot(_ctx(), [dir_ev, risk_ev])
    assert snap.directional_state.value == "BULLISH"
    assert snap.risk_state.value == "EXHAUSTION_WARNING"
    assert snap.chase_risk_state.value is None
    assert snap.chase_risk_state.status == "NOT_EVALUATED"


def test_exhaustion_warning_is_not_reversal_risk():
    ext = _ext(curr=105.0)
    a = E.evaluate_exhaustion(ext, [_comp("m1", "MOMENTUM_STALL"), _comp("d1", "PRICE_VOLUME_DIVERGENCE")], _ctx())
    ev = E.exhaustion_to_state_evidence(a, _ctx(), _dt(18, 7, 0), _dt(18, 7, 30))
    assert ev.value == "EXHAUSTION_WARNING"
    assert ev.value != "REVERSAL_RISK"


# ── future outcome leakage ──
def test_future_outcome_cannot_be_used_as_current_exhaustion_component():
    # component available_at after cutoff → blocked
    ext = _ext(curr=105.0)
    comp = _comp("s1", "STRUCTURAL_FAILURE", available_at=_dt(18, 9, 0))
    a = E.evaluate_exhaustion(ext, [comp, _comp("m1", "MOMENTUM_STALL")], _ctx())
    assert a.assessment_status == "BLOCKED"


# ── determinism ──
def test_extension_assessment_identity_is_deterministic():
    a1 = _ext(curr=103.0)
    a2 = _ext(curr=103.0)
    assert a1.assessment_id == a2.assessment_id


def test_extension_identity_changes_with_state():
    assert _ext(curr=101.0).assessment_id != _ext(curr=105.0).assessment_id


# ── safety ──
def test_no_probability_fields():
    a = _ext(curr=105.0)
    d = a.model_dump()
    for k in ("probability", "confidence", "success_rate", "expected_return"):
        assert k not in d


def test_no_trade_fields():
    a = _ext(curr=105.0)
    d = a.model_dump()
    for k in ("trade_instruction", "position", "order", "long", "short", "sell", "buy"):
        assert k not in d


# ── capability / data boundary truth ──
def test_daily_proxy_not_intraday():
    p = E.DailyExtensionPolicy()
    assert p.scope == "DAILY_RESEARCH_PROXY"
    assert p.reference_kind == "PREVIOUS_CLOSE"
