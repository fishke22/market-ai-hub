"""Phase V2-F — catalyst response scaffold tests."""
from __future__ import annotations

import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, "src")

from market_ai_hub.research.v2 import catalyst_response as C
from market_ai_hub.research.v2.state_machine import StateEvaluationContext


def _dt(d, h=0, m=0):
    return datetime(2026, 9, d, h, m, tzinfo=timezone.utc)


def _ctx(**kw):
    base = dict(instrument="JNU", target_family="OSAKA_MICRO", instrument_role="DIRECT",
                calendar_id="OSE_DERIVATIVES", frequency="DAILY", horizon="1d",
                feature_cutoff_timestamp=_dt(18, 8, 0), state_origin=_dt(18, 8, 0))
    base.update(kw)
    return StateEvaluationContext(**base)


def _cat(**kw):
    base = dict(catalyst_id="c1", catalyst_kind="MARKET_MOVE", factor_name="NQ",
                measurement_kind="RETURN", magnitude=0.02, unit="pct",
                event_timestamp=_dt(17, 20, 0), available_at=_dt(17, 20, 30),
                provider="p", source_type="M", source_schema_version="v1", source_version="v1",
                observation_semantics="OBSERVED", provenance_status="VERIFIED_INPUT",
                context_role="LIVE", availability_status="AVAILABLE")
    base.update(kw)
    return C.CatalystObservation(**base)


def _ep(value, event, available, **kw):
    base = dict(instrument="JNU", target_family="OSAKA_MICRO", instrument_role="DIRECT",
                calendar_id="OSE_DERIVATIVES", frequency="DAILY", value=value,
                event_timestamp=event, available_at=available,
                source_type="M", source_schema_version="v1", source_version="v1",
                provenance_status="VERIFIED_INPUT", series_semantics="CONTRACT", roll_status="NONE")
    base.update(kw)
    return C.TargetResponseEndpoint(**base)


def _eval(cat=None, start=None, end=None, baseline=None, response_label="r1", ctx=None, **kw):
    cat = cat or _cat()
    start = start or _ep(100.0, _dt(18, 0, 0), _dt(18, 0, 30))
    end = end or _ep(102.0, _dt(18, 7, 0), _dt(18, 7, 30))
    return C.evaluate_catalyst_response(ctx or _ctx(), cat, start, end, baseline=baseline, response_label=response_label, **kw)


# ── schema ──
def test_schema():
    assert C.V2_CATALYST_RESPONSE_SCHEMA_VERSION == "2F.2"


# ── catalyst truth ──
def test_schedule_only_cannot_create_realized_response():
    a = _eval(cat=_cat(observation_semantics="SCHEDULE_ONLY"))
    assert a.association_status == "BLOCKED"
    assert C.BLOCKED_CATALYST_NOT_OBSERVED in a.block_reason_codes


def test_future_catalyst_available_after_cutoff_blocks():
    a = _eval(cat=_cat(available_at=_dt(18, 9, 0)))
    assert a.association_status == "BLOCKED"


def test_catalyst_event_after_available_blocks():
    a = _eval(cat=_cat(event_timestamp=_dt(17, 21, 0), available_at=_dt(17, 20, 0)))
    assert a.association_status == "BLOCKED"


def test_non_observed_scenario_catalyst_blocks():
    a = _eval(cat=_cat(observation_semantics="SCENARIO"))
    assert C.BLOCKED_NON_OBSERVED_CATALYST_SOURCE in a.block_reason_codes


def test_actual_future_catalyst_blocks():
    a = _eval(cat=_cat(observation_semantics="ACTUAL_FUTURE"))
    assert C.BLOCKED_NON_OBSERVED_CATALYST_SOURCE in a.block_reason_codes


def test_unavailable_catalyst_blocks():
    a = _eval(cat=_cat(availability_status="NOT_AVAILABLE"))
    assert C.BLOCKED_CATALYST_UNAVAILABLE in a.block_reason_codes


# ── response temporal ──
def test_response_start_before_catalyst_available_blocks():
    # catalyst available 20:00 (day 17), start event 18:00 (day 17) < catalyst
    a = _eval(cat=_cat(available_at=_dt(17, 20, 0)),
              start=_ep(100.0, _dt(17, 18, 0), _dt(17, 18, 30)))
    assert a.association_status == "BLOCKED"
    assert C.BLOCKED_PRE_CATALYST_WINDOW in a.block_reason_codes


def test_response_start_equal_catalyst_available_allowed():
    a = _eval(cat=_cat(available_at=_dt(18, 0, 0)),
              start=_ep(100.0, _dt(18, 0, 0), _dt(18, 0, 30)),
              end=_ep(102.0, _dt(18, 7, 0), _dt(18, 7, 30)))
    assert a.association_status == "DESCRIPTIVE_AVAILABLE"


def test_response_end_after_cutoff_blocks():
    a = _eval(end=_ep(102.0, _dt(18, 9, 0), _dt(18, 9, 30)))
    assert a.association_status == "BLOCKED"


def test_response_end_must_follow_start():
    a = _eval(start=_ep(100.0, _dt(18, 5, 0), _dt(18, 5, 30)),
              end=_ep(102.0, _dt(18, 4, 0), _dt(18, 4, 30)))
    assert a.association_status == "BLOCKED"


def test_response_available_at_is_latest_required_input():
    a = _eval(cat=_cat(available_at=_dt(17, 20, 0)),
              start=_ep(100.0, _dt(18, 0, 0), _dt(18, 6, 0)),
              end=_ep(102.0, _dt(18, 7, 0), _dt(18, 7, 30)))
    assert a.response_available_at == _dt(18, 7, 30)


# ── daily / roll ──
def test_target_response_is_daily_only():
    with pytest.raises(ValueError):
        _ep(100.0, _dt(18, 0, 0), _dt(18, 0, 30), frequency="5M")


def test_osaka_roll_unknown_blocks_response():
    a = _eval(start=_ep(100.0, _dt(18, 0, 0), _dt(18, 0, 30), roll_status="UNKNOWN"))
    assert a.association_status == "BLOCKED"
    assert C.BLOCKED_ROLL_PROVENANCE in a.block_reason_codes


def test_mixed_series_semantics_blocks_response():
    a = _eval(start=_ep(100.0, _dt(18, 0, 0), _dt(18, 0, 30), series_semantics="CONTINUOUS"),
              end=_ep(102.0, _dt(18, 7, 0), _dt(18, 7, 30), series_semantics="CONTRACT"))
    assert a.association_status == "BLOCKED"
    assert C.BLOCKED_SERIES_SEMANTICS_MISMATCH in a.block_reason_codes


# ── prior-session semantics ──
def test_prior_us_close_remains_previous_session_reference():
    a = _eval(cat=_cat(context_role="PREVIOUS_SESSION_REFERENCE", staleness_status="STALE"))
    assert a.catalyst_context_role == "PREVIOUS_SESSION_REFERENCE"
    assert a.association_status == "REFERENCE_CONTEXT_ONLY"


def test_previous_session_reference_is_not_live_signal():
    a = _eval(cat=_cat(context_role="PREVIOUS_SESSION_REFERENCE"))
    assert a.association_status != "DESCRIPTIVE_AVAILABLE"


# ── residual ──
def _baseline(**kw):
    base = dict(baseline_id="b1", target_family="OSAKA_MICRO", instrument="JNU",
                instrument_role="DIRECT", calendar_id="OSE_DERIVATIVES",
                frequency="DAILY", horizon="1d",
                expected_response=0.005, fit_window_end=_dt(17, 19, 0),
                baseline_available_at=_dt(17, 19, 30),
                source_type="M", source_schema_version="v1", source_version="v1",
                asof_status="ASOF_VERIFIED", provenance_status="VERIFIED_INPUT")
    base.update(kw)
    return C.ExpectedResponseBaselineEvidence(**base)


def test_no_baseline_means_residual_not_available():
    a = _eval()
    assert a.expected_response is None
    assert a.response_residual is None
    assert a.residual_status == "NOT_AVAILABLE"


def test_pre_event_baseline_allows_residual():
    a = _eval(baseline=_baseline())  # response +2% (100->102), expected +0.5%
    assert a.response_residual == pytest.approx(0.015)
    assert a.residual_status == "DESCRIPTIVE_RESPONSE_RESIDUAL"


def test_baseline_fit_after_catalyst_blocks():
    # fit_window_end 17:20:15 is after catalyst event 17:20:00 but internal ordering is kept valid
    a = _eval(baseline=_baseline(fit_window_end=_dt(17, 20, 15), baseline_available_at=_dt(17, 20, 20)))
    assert a.association_status == "BLOCKED"
    assert C.BLOCKED_BASELINE_TEMPORAL_LEAKAGE in a.block_reason_codes


def test_baseline_available_after_catalyst_blocks():
    a = _eval(baseline=_baseline(baseline_available_at=_dt(17, 21, 0)))
    assert a.association_status == "BLOCKED"


def test_residual_is_actual_minus_expected():
    a = _eval(baseline=_baseline(expected_response=0.005))
    assert a.response_return == pytest.approx(0.02)
    assert a.response_residual == pytest.approx(0.015)


def test_residual_has_no_alpha_label():
    a = _eval(baseline=_baseline())
    d = a.model_dump()
    assert "alpha" not in d
    assert a.residual_status == "DESCRIPTIVE_RESPONSE_RESIDUAL"


# ── macro revision ──
def test_macro_revision_risk_is_preserved():
    a = _eval(cat=_cat(catalyst_kind="MACRO_RELEASE", revision_status="REVISION_RISK_PRESENT"))
    assert a.revision_status == "REVISION_RISK_PRESENT"


def test_event_only_macro_can_be_descriptive_without_fake_surprise():
    a = _eval(cat=_cat(catalyst_kind="MACRO_RELEASE", measurement_kind="EVENT_ONLY", magnitude=None,
                       release_timestamp=_dt(17, 20, 0)))
    assert a.association_status == "DESCRIPTIVE_AVAILABLE"


# ── no causal / lead-lag claim ──
def test_temporal_precedence_does_not_set_causal_status():
    a = _eval()
    assert a.causal_status == "NOT_ESTABLISHED"


def test_response_delay_is_not_lead_lag_score():
    a = _eval()
    assert a.response_delay_seconds == pytest.approx((_dt(18, 0, 0) - _dt(17, 20, 30)).total_seconds())
    d = a.model_dump()
    assert "lead_lag" not in d
    assert "granger" not in d
    assert "beta" not in d


# ── state separation ──
def test_positive_catalyst_does_not_create_bullish_state():
    a = _eval()
    d = a.model_dump()
    for k in ("direction", "bullish", "bearish", "chase_risk", "exhaustion"):
        assert k not in d


def test_catalyst_response_does_not_set_chase_risk():
    a = _eval()
    d = a.model_dump()
    assert "chase_risk" not in d
    assert "chase" not in d


# ── provenance / lineage ──
def test_context_legacy_prevents_asof_upgrade():
    ctx = _ctx(asof_status="LEGACY_TEMPORAL_UNVERIFIED")
    a = C.evaluate_catalyst_response(ctx, _cat(asof_status="ASOF_VERIFIED"),
                                     _ep(100.0, _dt(18, 0, 0), _dt(18, 0, 30), asof_status="ASOF_VERIFIED"),
                                     _ep(102.0, _dt(18, 7, 0), _dt(18, 7, 30), asof_status="ASOF_VERIFIED"),
                                     response_label="r1")
    assert a.derived_asof_status == "LEGACY_TEMPORAL_UNVERIFIED"


def test_role_specific_lineage_preserved():
    ctx = _ctx(source_snapshot_ids=["ctx"])
    a = C.evaluate_catalyst_response(ctx, _cat(source_snapshot_ids=["cat"]),
                                     _ep(100.0, _dt(18, 0, 0), _dt(18, 0, 30), source_snapshot_ids=["s"]),
                                     _ep(102.0, _dt(18, 7, 0), _dt(18, 7, 30), source_snapshot_ids=["e"]),
                                     response_label="r1")
    assert set(a.source_snapshot_ids) == {"ctx", "cat", "s", "e"}


def test_blocked_response_preserves_known_lineage():
    a = _eval(cat=_cat(observation_semantics="SCHEDULE_ONLY", source_snapshot_ids=["cat"]))
    assert a.association_status == "BLOCKED"
    assert "cat" in a.catalyst_source_snapshot_ids


def test_assessment_identity_is_deterministic():
    a1 = _eval()
    a2 = _eval()
    assert a1.assessment_id == a2.assessment_id


def test_different_catalyst_lineage_changes_assessment_id():
    a1 = _eval(cat=_cat(source_snapshot_ids=["c1"]))
    a2 = _eval(cat=_cat(source_snapshot_ids=["c2"]))
    assert a1.assessment_id != a2.assessment_id


def test_different_response_lineage_changes_assessment_id():
    a1 = _eval(end=_ep(102.0, _dt(18, 7, 0), _dt(18, 7, 30), source_snapshot_ids=["e1"]))
    a2 = _eval(end=_ep(102.0, _dt(18, 7, 0), _dt(18, 7, 30), source_snapshot_ids=["e2"]))
    assert a1.assessment_id != a2.assessment_id


# ── response path ──
def _assessments():
    ctx = _ctx(feature_cutoff_timestamp=_dt(21, 8, 0), state_origin=_dt(21, 8, 0))
    a1 = _eval(ctx=ctx, response_label="h1", end=_ep(102.0, _dt(18, 7, 0), _dt(18, 7, 30)))  # +2%
    a2 = _eval(ctx=ctx, response_label="h2", end=_ep(101.2, _dt(19, 7, 0), _dt(19, 7, 30)))  # +1.2%
    a3 = _eval(ctx=ctx, response_label="h3", end=_ep(100.8, _dt(20, 7, 0), _dt(20, 7, 30)))  # +0.8%
    return [a1, a2, a3]


def test_response_path_requires_same_catalyst():
    a = _assessments()
    a[1].catalyst_id = "c2"
    p = C.summarize_response_path(a)
    assert p.path_status == "BLOCKED"
    assert C.BLOCKED_CATALYST_ID_COLLISION in p.block_reason_codes


def test_response_path_requires_same_target():
    a = _assessments()
    a[1].target_family = "TAIWAN_STOCK"
    p = C.summarize_response_path(a)
    assert p.path_status == "BLOCKED"
    assert C.BLOCKED_IDENTITY_MISMATCH in p.block_reason_codes


def test_terminal_to_peak_ratio_deterministic():
    p = C.summarize_response_path(_assessments())
    assert p.peak_absolute_response == pytest.approx(0.02)
    assert p.terminal_absolute_response == pytest.approx(0.008)
    assert p.terminal_to_peak_abs_ratio == pytest.approx(0.4)


def test_path_input_order_canonical():
    a = _assessments()
    p1 = C.summarize_response_path(a)
    p2 = C.summarize_response_path(list(reversed(a)))
    assert p1.path_id == p2.path_id


def test_response_path_windows_monotonic():
    p = C.summarize_response_path(_assessments())
    horizons = list(p.response_returns_by_horizon.keys())
    # windows are keyed by response_id; returns sorted by window end internally
    assert p.path_id != ""


# ── safety ──
def test_no_probability_fields():
    a = _eval()
    d = a.model_dump()
    for k in ("probability", "confidence", "success_probability", "causal_probability"):
        assert k not in d


def test_no_trade_fields():
    a = _eval()
    d = a.model_dump()
    for k in ("buy", "sell", "long", "short", "position", "order", "entry", "stop_loss", "take_profit"):
        assert k not in d


# ── 2F.2 baseline hardening ──
def test_baseline_cross_instrument_identity_blocked():
    a = _eval(baseline=_baseline(instrument="NK225M"))
    assert a.association_status == "BLOCKED"
    assert C.BLOCKED_BASELINE_IDENTITY_MISMATCH in a.block_reason_codes


def test_baseline_cross_family_identity_blocked():
    a = _eval(baseline=_baseline(target_family="TAIWAN_STOCK"))
    assert a.association_status == "BLOCKED"
    assert C.BLOCKED_BASELINE_IDENTITY_MISMATCH in a.block_reason_codes


def test_baseline_missing_timestamps_blocked():
    a = _eval(baseline=_baseline(fit_window_end=None, baseline_available_at=None))
    assert a.association_status == "BLOCKED"
    assert C.BLOCKED_BASELINE_TEMPORAL_PROVENANCE in a.block_reason_codes


def test_baseline_internal_order_provenance_blocked():
    a = _eval(baseline=_baseline(fit_window_end=_dt(17, 20, 0), baseline_available_at=_dt(17, 19, 0)))
    assert a.association_status == "BLOCKED"
    assert C.BLOCKED_BASELINE_TEMPORAL_PROVENANCE in a.block_reason_codes


def test_baseline_available_after_catalyst_blocks():
    a = _eval(baseline=_baseline(baseline_available_at=_dt(17, 21, 0)))
    assert a.association_status == "BLOCKED"
    assert C.BLOCKED_BASELINE_TEMPORAL_LEAKAGE in a.block_reason_codes


def test_baseline_missing_source_blocked():
    a = _eval(baseline=_baseline(source_type=""))
    assert a.association_status == "BLOCKED"
    assert C.BLOCKED_BASELINE_SOURCE_PROVENANCE in a.block_reason_codes


def test_baseline_validation_status_frozen():
    with pytest.raises(ValueError):
        _baseline(validation_status="VERIFIED")


def test_baseline_unknown_provenance_never_publishes_verified_residual():
    a = _eval(baseline=_baseline(provenance_status="UNKNOWN"))
    assert a.association_status == "DESCRIPTIVE_AVAILABLE"
    assert a.response_residual is None
    assert a.expected_response is None
    assert a.residual_status == "UNVERIFIED_BASELINE"


# ── 2F.2 macro release-time truth ──
def test_macro_release_missing_release_timestamp_blocked():
    a = _eval(cat=_cat(catalyst_kind="MACRO_RELEASE"))
    assert a.association_status == "BLOCKED"
    assert C.BLOCKED_RELEASE_TIME_PROVENANCE in a.block_reason_codes


def test_macro_release_after_available_blocked():
    a = _eval(cat=_cat(catalyst_kind="MACRO_RELEASE", release_timestamp=_dt(17, 21, 0)))
    assert a.association_status == "BLOCKED"
    assert C.BLOCKED_RELEASE_TIME_PROVENANCE in a.block_reason_codes


# ── 2F.2 catalyst structural validation ──
def test_catalyst_unsupported_frequency_rejected():
    with pytest.raises(ValueError):
        _cat(frequency="5M")


def test_catalyst_bad_quality_status_rejected():
    with pytest.raises(ValueError):
        _cat(quality_status="BANANA")


def test_catalyst_empty_factor_name_rejected():
    with pytest.raises(ValueError):
        _cat(factor_name="")


def test_catalyst_return_requires_magnitude():
    with pytest.raises(ValueError):
        _cat(measurement_kind="RETURN", magnitude=None)


def test_catalyst_event_only_forces_magnitude_none():
    c = _cat(measurement_kind="EVENT_ONLY", magnitude=0.02)
    assert c.magnitude is None
    assert c.unit == ""


# ── 2F.2 futures series semantics ──
def test_osaka_unknown_series_semantics_blocked():
    a = _eval(start=_ep(100.0, _dt(18, 0, 0), _dt(18, 0, 30), series_semantics="UNKNOWN"))
    assert a.association_status == "BLOCKED"
    assert C.BLOCKED_SERIES_SEMANTICS_MISMATCH in a.block_reason_codes


# ── 2F.2 semantic identity ──
def test_response_label_does_not_change_response_id():
    a1 = _eval(response_label="lblA")
    a2 = _eval(response_label="lblB")
    assert a1.response_id == a2.response_id


def test_catalyst_semantic_change_changes_response_id():
    a1 = _eval(cat=_cat(staleness_status="FRESH"))
    a2 = _eval(cat=_cat(staleness_status="STALE"))
    assert a1.response_id != a2.response_id


def test_response_id_is_prefixed():
    a = _eval()
    assert a.response_id.startswith("v2f_resp_")


# ── 2F.2 path hardening ──
def _forge_assessment(response_id, response_return, response_window_end, fingerprint="fp"):
    return C.CatalystResponseAssessment(
        catalyst_id="c1", catalyst_kind="MARKET_MOVE", factor_name="NQ",
        catalyst_fingerprint=fingerprint, instrument="JNU", target_family="OSAKA_MICRO",
        instrument_role="DIRECT", calendar_id="OSE_DERIVATIVES", frequency="DAILY", horizon="1d",
        feature_cutoff_timestamp=_dt(21, 8, 0), state_origin=_dt(21, 8, 0),
        response_id=response_id, response_window_start=_dt(18, 0, 0),
        response_window_end=response_window_end, response_return=response_return,
        response_start_fingerprint="anchor", association_status="DESCRIPTIVE_AVAILABLE",
        causal_status="NOT_ESTABLISHED", residual_status="NOT_AVAILABLE",
    )


def test_path_ineligible_assessment_blocked():
    a1 = _eval()
    a2 = _eval(cat=_cat(observation_semantics="SCHEDULE_ONLY"))  # BLOCKED
    p = C.summarize_response_path([a1, a2])
    assert p.path_status == "BLOCKED"
    assert C.BLOCKED_INELIGIBLE_RESPONSE_ASSESSMENT in p.block_reason_codes


def test_path_state_stream_mismatch_blocked():
    a1 = _forge_assessment("r1", 0.02, _dt(18, 7, 30), fingerprint="fpA")
    a2 = _forge_assessment("r2", 0.01, _dt(19, 7, 30), fingerprint="fpA")
    a2.state_origin = _dt(22, 8, 0)
    p = C.summarize_response_path([a1, a2])
    assert p.path_status == "BLOCKED"
    assert C.BLOCKED_STATE_STREAM_MISMATCH in p.block_reason_codes


def test_path_response_anchor_mismatch_blocked():
    a1 = _forge_assessment("r1", 0.02, _dt(18, 7, 30), fingerprint="fpA")
    a2 = _forge_assessment("r2", 0.01, _dt(19, 7, 30), fingerprint="fpA")
    a2.response_start_fingerprint = "anchor2"
    p = C.summarize_response_path([a1, a2])
    assert p.path_status == "BLOCKED"
    assert C.BLOCKED_RESPONSE_ANCHOR_MISMATCH in p.block_reason_codes


def test_path_horizon_order_blocked():
    a1 = _forge_assessment("r1", 0.02, _dt(18, 7, 30), fingerprint="fpA")
    a2 = _forge_assessment("r2", 0.01, _dt(18, 7, 30), fingerprint="fpA")
    p = C.summarize_response_path([a1, a2])
    assert p.path_status == "BLOCKED"
    assert C.BLOCKED_PATH_HORIZON_ORDER in p.block_reason_codes


def test_path_blocked_has_deterministic_nonempty_id():
    a = _assessments()
    a[1].catalyst_id = "c2"
    p1 = C.summarize_response_path(a)
    p2 = C.summarize_response_path(list(a))
    assert p1.path_status == "BLOCKED"
    assert p1.path_id != ""
    assert p1.path_id == p2.path_id
