"""Phase V2-E — daily extension / exhaustion research engine tests (2E.2)."""
from __future__ import annotations

import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, "src")

from market_ai_hub.research.v2 import extension_exhaustion as E
from market_ai_hub.research.v2.state_machine import (
    StateEvaluationContext, StateEvidence, compose_state_snapshot, validate_state_evidence)


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
                instrument="JNU", target_family="OSAKA_MICRO", instrument_role="DIRECT",
                calendar_id="OSE_DERIVATIVES", frequency="DAILY", horizon="1d",
                series_semantics="CONTRACT", roll_status="NONE",
                source_type="M", source_schema_version="v1", source_version="v1",
                provenance_status="VERIFIED_INPUT")
    base.update(kw)
    return E.PointInTimeScalar(**base)


def _prev_close(v=100.0):
    return _scalar("previous_close", v, _dt(17, 7, 0), _dt(17, 8, 0))


def _curr_close(v=101.0):
    return _scalar("current_close", v, _dt(18, 7, 0), _dt(18, 7, 30))


def _atr(v=2.0):
    return _scalar("atr_baseline", v, _dt(17, 6, 0), _dt(17, 6, 30), atr_period=14,
                   atr_method=E.ATR_METHOD)


def _ext(curr=101.0, prev=100.0, atr=2.0, **kw):
    return E.evaluate_extension(_ctx(), _curr_close(curr), _prev_close(prev), _atr(atr), **kw)


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
    assert E.V2_EXTENSION_EXHAUSTION_SCHEMA_VERSION == "2E.2"


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
    assert _ext(curr=97.0).absolute_extension_units == pytest.approx(1.5)


def test_normal_below_1():
    assert _ext(curr=101.0).extension_state == "NORMAL"


def test_exact_1_extended():
    assert _ext(curr=102.0).extension_state == "EXTENDED"


def test_just_below_2_extended():
    assert _ext(curr=103.9).extension_state == "EXTENDED"


def test_exact_2_extreme():
    assert _ext(curr=104.0).extension_state == "EXTREME"


def test_above_2_extreme():
    assert _ext(curr=105.0).extension_state == "EXTREME"


# ── input quality ──
def test_atr_nonfinite_rejected():
    with pytest.raises(ValueError):
        _atr(float("nan"))


def test_atr_zero_blocks():
    assert _ext(atr=0.0).assessment_status == "BLOCKED"


def test_current_price_invalid_blocks():
    assert _ext(curr=0.0).assessment_status == "BLOCKED"


def test_reference_price_invalid_blocks():
    assert _ext(prev=-1.0).assessment_status == "BLOCKED"


# ── policy freeze (§8/§9) ──
def test_extension_policy_rejects_custom_atr_period():
    with pytest.raises(ValueError):
        E.DailyExtensionPolicy(atr_period=99)


def test_extension_policy_rejects_custom_thresholds():
    with pytest.raises(ValueError):
        E.DailyExtensionPolicy(extended_threshold_atr=0.1, extreme_threshold_atr=0.2)


def test_extension_policy_rejects_proven_validation_status():
    with pytest.raises(ValueError):
        E.DailyExtensionPolicy(validation_status="PROVEN")


def test_extension_policy_rejects_optimized_status():
    with pytest.raises(ValueError):
        E.DailyExtensionPolicy(optimization_status="OPTIMIZED")


def test_exhaustion_policy_requires_exact_two_families():
    with pytest.raises(ValueError):
        E.DailyExhaustionPolicy(minimum_distinct_confirmation_families=4)


def test_exhaustion_policy_rejects_proven_status():
    with pytest.raises(ValueError):
        E.DailyExhaustionPolicy(validation_status="PROVEN")


# ── roll enum / fail-closed (§3) ──
def test_unknown_roll_string_rejected():
    with pytest.raises(ValueError):
        _scalar("current_close", 101.0, _dt(18, 7, 0), _dt(18, 7, 30), roll_status="BANANA")


def test_osaka_roll_none_required():
    assert _ext().assessment_status == "EVALUATED"  # scalars default roll NONE


def test_osaka_not_applicable_roll_blocks():
    cc = _scalar("current_close", 101.0, _dt(18, 7, 0), _dt(18, 7, 30), roll_status="NOT_APPLICABLE")
    a = E.evaluate_extension(_ctx(), cc, _prev_close(), _atr())
    assert a.assessment_status == "BLOCKED"
    assert "BLOCKED_ROLL_PROVENANCE" in a.block_reason_codes


def test_osaka_roll_unknown_blocks():
    cc = _scalar("current_close", 101.0, _dt(18, 7, 0), _dt(18, 7, 30), roll_status="UNKNOWN")
    a = E.evaluate_extension(_ctx(), cc, _prev_close(), _atr())
    assert a.assessment_status == "BLOCKED"


# ── scalar identity (§5) ──
def test_cross_target_scalar_blocks():
    cc = _scalar("current_close", 101.0, _dt(18, 7, 0), _dt(18, 7, 30),
                 instrument="3706.TW", target_family="TAIWAN_STOCK", calendar_id="XTAI")
    a = E.evaluate_extension(_ctx(), cc, _prev_close(), _atr())
    assert a.assessment_status == "BLOCKED"
    assert "BLOCKED_IDENTITY_MISMATCH" in a.block_reason_codes


# ── series semantics (§6/§13) ──
def test_unknown_series_semantics_rejected():
    with pytest.raises(ValueError):
        _scalar("current_close", 101.0, _dt(18, 7, 0), _dt(18, 7, 30), series_semantics="BANANA")


def test_mixed_scalar_series_semantics_blocks():
    cc = _scalar("current_close", 101.0, _dt(18, 7, 0), _dt(18, 7, 30), series_semantics="CONTINUOUS")
    a = E.evaluate_extension(_ctx(), cc, _prev_close(), _atr())
    assert a.assessment_status == "BLOCKED"
    assert "BLOCKED_SERIES_SEMANTICS_MISMATCH" in a.block_reason_codes


# ── ATR provenance (§7) ──
def test_atr_requires_period_14():
    atr = _scalar("atr_baseline", 2.0, _dt(17, 6, 0), _dt(17, 6, 30), atr_period=10,
                  atr_method=E.ATR_METHOD)
    a = E.evaluate_extension(_ctx(), _curr_close(), _prev_close(), atr)
    assert a.assessment_status == "BLOCKED"
    assert "BLOCKED_ATR_POLICY_MISMATCH" in a.block_reason_codes


def test_atr_requires_canonical_method():
    atr = _scalar("atr_baseline", 2.0, _dt(17, 6, 0), _dt(17, 6, 30), atr_period=14,
                  atr_method="OTHER_ATR")
    a = E.evaluate_extension(_ctx(), _curr_close(), _prev_close(), atr)
    assert a.assessment_status == "BLOCKED"


# ── context / temporal ──
def test_cutoff_after_origin_blocks_extension():
    a = E.evaluate_extension(_ctx(feature_cutoff_timestamp=_dt(18, 9, 0), state_origin=_dt(18, 8, 0)),
                             _curr_close(), _prev_close(), _atr())
    assert a.assessment_status == "BLOCKED"


def test_available_after_cutoff_blocks():
    cc = _scalar("current_close", 101.0, _dt(18, 8, 30), _dt(18, 8, 30))
    a = E.evaluate_extension(_ctx(), cc, _prev_close(), _atr())
    assert a.assessment_status == "BLOCKED"


def test_previous_close_event_not_before_current_blocks():
    pc = _scalar("previous_close", 100.0, _dt(18, 7, 0), _dt(18, 7, 30))
    cc = _scalar("current_close", 101.0, _dt(18, 7, 0), _dt(18, 7, 30))
    a = E.evaluate_extension(_ctx(), cc, pc, _atr())
    assert a.assessment_status == "BLOCKED"


# ── ASOF (§12/§28) ──
def test_context_legacy_prevents_extension_asof_verified():
    ctx = _ctx(asof_status="LEGACY_TEMPORAL_UNVERIFIED")
    cc = _scalar("current_close", 101.0, _dt(18, 7, 0), _dt(18, 7, 30), asof_status="ASOF_VERIFIED")
    pc = _scalar("previous_close", 100.0, _dt(17, 7, 0), _dt(17, 8, 0), asof_status="ASOF_VERIFIED")
    atr = _scalar("atr_baseline", 2.0, _dt(17, 6, 0), _dt(17, 6, 30), asof_status="ASOF_VERIFIED",
                  atr_period=14, atr_method=E.ATR_METHOD)
    a = E.evaluate_extension(ctx, cc, pc, atr)
    assert a.derived_asof_status == "LEGACY_TEMPORAL_UNVERIFIED"


def test_unknown_provenance_gives_unverified():
    cc = _scalar("current_close", 101.0, _dt(18, 7, 0), _dt(18, 7, 30), provenance_status="UNKNOWN")
    a = E.evaluate_extension(_ctx(), cc, _prev_close(), _atr())
    assert a.assessment_status == "UNVERIFIED"
    assert a.extension_state is None


# ── exhaustion ──
def test_extreme_extension_alone_is_not_exhaustion():
    a = E.evaluate_exhaustion(_ext(curr=105.0), [], _ctx())
    assert a.assessment_status == "INSUFFICIENT_CONFIRMATION"
    assert a.warning_established is False


def test_single_oscillator_cannot_establish_exhaustion():
    a = E.evaluate_exhaustion(_ext(curr=105.0), [_comp("r1", "OSCILLATOR_EXTREME")], _ctx())
    assert a.assessment_status == "INSUFFICIENT_CONFIRMATION"


def test_duplicate_oscillator_family_cannot_inflate_confirmation_count():
    a = E.evaluate_exhaustion(_ext(curr=105.0),
                              [_comp("r1", "OSCILLATOR_EXTREME"), _comp("r2", "OSCILLATOR_EXTREME")], _ctx())
    assert a.confirmation_family_count == 1


def test_exhaustion_requires_two_distinct_confirmation_families():
    a = E.evaluate_exhaustion(_ext(curr=105.0),
                              [_comp("m1", "MOMENTUM_STALL"), _comp("d1", "PRICE_VOLUME_DIVERGENCE")], _ctx())
    assert a.assessment_status == "WARNING_ESTABLISHED"
    assert set(a.positive_confirmation_families) == {"MOMENTUM_STALL", "PRICE_VOLUME_DIVERGENCE"}


def test_unverified_component_does_not_count():
    a = E.evaluate_exhaustion(_ext(curr=105.0),
                              [_comp("m1", "MOMENTUM_STALL"),
                               _comp("r1", "OSCILLATOR_EXTREME", provenance_status="UNKNOWN")], _ctx())
    assert a.confirmation_family_count == 1
    assert a.unverified_component_ids == ["r1"]


def test_conflicting_family_conflict():
    a = E.evaluate_exhaustion(_ext(curr=105.0),
                              [_comp("m1", "MOMENTUM_STALL", True), _comp("m2", "MOMENTUM_STALL", False)], _ctx())
    assert a.assessment_status == "CONFLICT"
    assert a.conflict_families == ["MOMENTUM_STALL"]


# ── component truth (§17/§18/§19) ──
def test_component_requires_source_type():
    a = E.evaluate_exhaustion(_ext(curr=105.0),
                              [_comp("m1", "MOMENTUM_STALL", source_type=""),
                               _comp("d1", "PRICE_VOLUME_DIVERGENCE")], _ctx())
    assert a.assessment_status == "BLOCKED"


def test_component_present_must_be_bool():
    with pytest.raises(ValueError):
        _comp("m1", "MOMENTUM_STALL", present="yes")


def test_same_component_id_same_payload_dedupes():
    a = E.evaluate_exhaustion(_ext(curr=105.0),
                              [_comp("m1", "MOMENTUM_STALL"), _comp("m1", "MOMENTUM_STALL"),
                               _comp("d1", "PRICE_VOLUME_DIVERGENCE")], _ctx())
    assert a.assessment_status == "WARNING_ESTABLISHED"


def test_same_component_id_different_payload_blocks():
    a = E.evaluate_exhaustion(_ext(curr=105.0),
                              [_comp("m1", "MOMENTUM_STALL", True), _comp("m1", "MOMENTUM_STALL", False),
                               _comp("d1", "PRICE_VOLUME_DIVERGENCE")], _ctx())
    assert a.assessment_status == "BLOCKED"
    assert "BLOCKED_COMPONENT_ID_COLLISION" in a.block_reason_codes


def test_same_component_id_cannot_vote_in_two_families():
    a = E.evaluate_exhaustion(_ext(curr=105.0),
                              [_comp("x", "MOMENTUM_STALL"), _comp("x", "PRICE_VOLUME_DIVERGENCE")], _ctx())
    assert a.assessment_status == "BLOCKED"


# ── extension/exhaustion identity binding (§20/§22/§23) ──
def test_exhaustion_rejects_cross_target_extension():
    ext = _ext(curr=105.0)
    ctx_tw = _ctx(instrument="3706.TW", target_family="TAIWAN_STOCK", calendar_id="XTAI")
    comp = _comp("m1", "MOMENTUM_STALL", instrument="3706.TW", target_family="TAIWAN_STOCK", calendar_id="XTAI")
    a = E.evaluate_exhaustion(ext, [comp, _comp("d1", "PRICE_VOLUME_DIVERGENCE", instrument="3706.TW",
                                               target_family="TAIWAN_STOCK", calendar_id="XTAI")], ctx_tw)
    assert a.assessment_status == "BLOCKED"


def test_extension_adapter_rejects_cross_target_context():
    ext = _ext(curr=104.0)  # Osaka EXTREME
    with pytest.raises(ValueError):
        E.extension_to_state_evidence(ext, _ctx(instrument="3706.TW", target_family="TAIWAN_STOCK", calendar_id="XTAI"))


# ── warning time truth (§25/§26/§27) ──
def _early_extreme_extension():
    # EXTREME extension whose current close is available EARLY (05:30), so components set warning time
    cc = _scalar("current_close", 105.0, _dt(18, 5, 0), _dt(18, 5, 30))
    return E.evaluate_extension(_ctx(), cc, _prev_close(), _atr())


def test_warning_time_is_second_required_confirmation_time():
    ext = _early_extreme_extension()
    comps = [_comp("m1", "MOMENTUM_STALL", event_timestamp=_dt(18, 6, 0), available_at=_dt(18, 6, 30)),
             _comp("d1", "PRICE_VOLUME_DIVERGENCE", event_timestamp=_dt(18, 7, 0), available_at=_dt(18, 7, 15))]
    a = E.evaluate_exhaustion(ext, comps, _ctx())
    assert a.warning_available_at == _dt(18, 7, 15)  # latest required availability
    assert a.warning_event_timestamp == _dt(18, 7, 0)


def test_exhaustion_adapter_uses_assessment_timestamp_only():
    ext = _early_extreme_extension()
    comps = [_comp("m1", "MOMENTUM_STALL", available_at=_dt(18, 7, 0)),
             _comp("d1", "PRICE_VOLUME_DIVERGENCE", available_at=_dt(18, 7, 15))]
    a = E.evaluate_exhaustion(ext, comps, _ctx())
    ev = E.exhaustion_to_state_evidence(a, _ctx())
    assert ev.available_at == _dt(18, 7, 15)


def test_exhaustion_adapter_cannot_backdate_warning():
    # no caller timestamp argument exists anymore; derived from evidence
    assert "current_event_timestamp" not in E.exhaustion_to_state_evidence.__code__.co_varnames


# ── lineage (§14/§15/§29/§31) ──
def test_extension_preserves_context_and_scalar_role_lineage():
    ctx = _ctx(source_snapshot_ids=["ctx"])
    cc = _scalar("current_close", 103.0, _dt(18, 7, 0), _dt(18, 7, 30), source_snapshot_ids=["c"])
    pc = _scalar("previous_close", 100.0, _dt(17, 7, 0), _dt(17, 8, 0), source_snapshot_ids=["p"])
    atr = _scalar("atr_baseline", 2.0, _dt(17, 6, 0), _dt(17, 6, 30), atr_period=14,
                  atr_method=E.ATR_METHOD, source_snapshot_ids=["a"])
    a = E.evaluate_extension(ctx, cc, pc, atr)
    assert a.context_source_snapshot_ids == ["ctx"]
    assert set(a.source_snapshot_ids) == {"ctx", "c", "p", "a"}


def test_unverified_extension_preserves_lineage():
    cc = _scalar("current_close", 103.0, _dt(18, 7, 0), _dt(18, 7, 30),
                 provenance_status="UNKNOWN", source_snapshot_ids=["c"])
    a = E.evaluate_extension(_ctx(), cc, _prev_close(), _atr())
    assert a.assessment_status == "UNVERIFIED"
    assert "c" in a.source_snapshot_ids


def test_exhaustion_preserves_context_extension_component_lineage():
    ctx = _ctx(source_snapshot_ids=["ctx"])
    cc = _scalar("current_close", 105.0, _dt(18, 7, 0), _dt(18, 7, 30), source_snapshot_ids=["ext"])
    ext = E.evaluate_extension(ctx, cc, _prev_close(), _atr())
    a = E.evaluate_exhaustion(ext, [_comp("m1", "MOMENTUM_STALL", source_snapshot_ids=["m"]),
                                    _comp("d1", "PRICE_VOLUME_DIVERGENCE", source_snapshot_ids=["d"])], ctx)
    assert set(a.source_snapshot_ids) == {"ctx", "ext", "m", "d"}


# ── direct V2-C outcome block (§32) ──
def test_direct_v2c_outcome_component_is_blocked():
    a = E.evaluate_exhaustion(_ext(curr=105.0),
                              [_comp("s1", "STRUCTURAL_FAILURE", source_type="V2C_OUTCOME"),
                               _comp("m1", "MOMENTUM_STALL")], _ctx())
    assert a.assessment_status == "BLOCKED"
    assert "BLOCKED_DIRECT_FUTURE_OUTCOME_SOURCE" in a.block_reason_codes


# ── semantic IDs (§30/§44) ──
def test_extension_different_source_lineage_changes_assessment_id():
    a1 = _ext(curr=103.0)
    cc = _scalar("current_close", 103.0, _dt(18, 7, 0), _dt(18, 7, 30), source_snapshot_ids=["c2"])
    a2 = E.evaluate_extension(_ctx(), cc, _prev_close(), _atr())
    assert a1.assessment_id != a2.assessment_id


def test_exhaustion_unverified_component_changes_assessment_id():
    a1 = E.evaluate_exhaustion(_ext(curr=105.0), [_comp("m1", "MOMENTUM_STALL")], _ctx())
    a2 = E.evaluate_exhaustion(_ext(curr=105.0),
                               [_comp("m1", "MOMENTUM_STALL"), _comp("r1", "OSCILLATOR_EXTREME", provenance_status="UNKNOWN")],
                               _ctx())
    assert a1.assessment_id != a2.assessment_id


def test_component_order_does_not_change_assessment():
    a1 = E.evaluate_exhaustion(_ext(curr=105.0),
                               [_comp("m1", "MOMENTUM_STALL"), _comp("d1", "PRICE_VOLUME_DIVERGENCE")], _ctx())
    a2 = E.evaluate_exhaustion(_ext(curr=105.0),
                               [_comp("d1", "PRICE_VOLUME_DIVERGENCE"), _comp("m1", "MOMENTUM_STALL")], _ctx())
    assert a1.assessment_id == a2.assessment_id


# ── state adapter / V2-D integration ──
def test_extension_evidence_validates_in_v2d():
    a = _ext(curr=104.0)
    ev = E.extension_to_state_evidence(a, _ctx())
    assert validate_state_evidence(ev, _ctx()) == []


def test_warning_evidence_validates_in_v2d():
    ext = _ext(curr=105.0)
    a = E.evaluate_exhaustion(ext, [_comp("m1", "MOMENTUM_STALL"), _comp("d1", "PRICE_VOLUME_DIVERGENCE")], _ctx())
    ev = E.exhaustion_to_state_evidence(a, _ctx())
    assert validate_state_evidence(ev, _ctx()) == []


def test_exhaustion_warning_does_not_change_direction():
    ext = _ext(curr=105.0)
    a = E.evaluate_exhaustion(ext, [_comp("m1", "MOMENTUM_STALL"), _comp("d1", "PRICE_VOLUME_DIVERGENCE")], _ctx())
    risk_ev = E.exhaustion_to_state_evidence(a, _ctx())
    dir_ev = StateEvidence(evidence_id="d1", layer="DIRECTIONAL", value="BULLISH",
                           instrument="JNU", target_family="OSAKA_MICRO", calendar_id="OSE_DERIVATIVES",
                           frequency="DAILY", horizon="1d", event_timestamp=_dt(18, 0, 0), available_at=_dt(18, 7, 0),
                           source_type="M", source_schema_version="v1", source_version="v1",
                           provenance_status="VERIFIED_INPUT")
    snap = compose_state_snapshot(_ctx(), [dir_ev, risk_ev])
    assert snap.directional_state.value == "BULLISH"
    assert snap.risk_state.value == "EXHAUSTION_WARNING"
    assert snap.chase_risk_state.value is None


def test_exhaustion_warning_is_not_reversal_risk():
    ext = _ext(curr=105.0)
    a = E.evaluate_exhaustion(ext, [_comp("m1", "MOMENTUM_STALL"), _comp("d1", "PRICE_VOLUME_DIVERGENCE")], _ctx())
    ev = E.exhaustion_to_state_evidence(a, _ctx())
    assert ev.value == "EXHAUSTION_WARNING"
    assert ev.value != "REVERSAL_RISK"


# ── safety ──
def test_no_probability_fields():
    d = _ext(curr=105.0).model_dump()
    for k in ("probability", "confidence", "success_rate", "expected_return"):
        assert k not in d


def test_no_trade_fields():
    d = _ext(curr=105.0).model_dump()
    for k in ("trade_instruction", "position", "order", "long", "short", "sell", "buy"):
        assert k not in d


def test_daily_proxy_not_intraday():
    p = E.DailyExtensionPolicy()
    assert p.scope == "DAILY_RESEARCH_PROXY"
    assert p.reference_kind == "PREVIOUS_CLOSE"
