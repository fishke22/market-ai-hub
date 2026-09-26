"""W5.1 daily first-passage regression."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from market_ai_hub.research.v2 import calibration_evaluation as CE
from market_ai_hub.research.v2 import first_passage as FP
from market_ai_hub.research.v2 import prediction_audit as PA
from market_ai_hub.research.v2.labels import BarrierSpec, DailyLabelRequest, DailyOutcomeBar


def _dt(day: int, hour: int = 0):
    return datetime(2026, 9, day, hour, tzinfo=timezone.utc)


def _request(h=2):
    return DailyLabelRequest(
        instrument="JNU2612", target_family="OSAKA_MICRO", instrument_role="DIRECT",
        calendar_id="OSE_DERIVATIVES", feature_cutoff_timestamp=_dt(20, 7),
        forecast_origin=_dt(20, 8), origin_session_date="2026-09-20",
        horizon_sessions=h, source_snapshot_ids=["forecast"],
        asof_status="ASOF_VERIFIED", previous_close=100.0,
        previous_close_available_at=_dt(20, 7),
        previous_close_source_snapshot_ids=["prev"],
        previous_close_provenance="VERIFIED_INPUT",
    )


def _bar(day: int, low: float, high: float, close: float):
    return DailyOutcomeBar(
        instrument="JNU2612", target_family="OSAKA_MICRO", instrument_role="DIRECT",
        calendar_id="OSE_DERIVATIVES", trading_date=f"2026-09-{day:02d}",
        session_open_timestamp=_dt(day, 0), session_close_timestamp=_dt(day, 6),
        open=100.0, high=high, low=low, close=close,
        source_snapshot_ids=[f"bar-{day}"], asof_status="ASOF_VERIFIED",
        roll_status="NONE", series_semantics="CONTRACT",
    )


def _upper():
    return BarrierSpec(
        barrier_id="UP", level=110.0, direction="UP", barrier_source="policy",
        barrier_available_at=_dt(20, 7), source_snapshot_ids=["up"],
    )


def _lower():
    return BarrierSpec(
        barrier_id="DOWN", level=90.0, direction="DOWN", barrier_source="policy",
        barrier_available_at=_dt(20, 7), source_snapshot_ids=["down"],
    )


def _build(bars, h=2):
    return FP.build_daily_first_passage_label(
        _request(h), _upper(), _lower(), bars,
        expected_sessions=[f"2026-09-{d:02d}" for d in range(21, 21+h)],
        calendar_provenance="VERIFIED_INPUT",
    )


def test_upper_first_across_daily_sessions():
    r=_build([_bar(21,95,112,108),_bar(22,88,109,95)])
    assert r.status==FP.OBSERVED and r.outcome=="UPPER_FIRST"
    assert r.first_session_date=="2026-09-21"


def test_lower_first_across_daily_sessions():
    r=_build([_bar(21,88,105,92),_bar(22,95,112,108)])
    assert r.status==FP.OBSERVED and r.outcome=="LOWER_FIRST"
    assert r.first_session_date=="2026-09-21"


def test_same_daily_bar_double_touch_is_ambiguous_not_guessed():
    r=_build([_bar(21,88,112,100),_bar(22,95,105,100)])
    assert r.status==FP.AMBIGUOUS_WITHIN_DAILY_BAR
    assert r.outcome=="AMBIGUOUS_WITHIN_DAILY_BAR"
    assert FP.binary_first_passage_outcome(r,"UPPER_FIRST").value is None


def test_neither_after_mature_horizon():
    r=_build([_bar(21,95,105,100),_bar(22,96,104,101)])
    assert r.status==FP.OBSERVED and r.outcome=="NEITHER"
    assert FP.binary_first_passage_outcome(r,"NEITHER").value is True
    assert FP.binary_first_passage_outcome(r,"UPPER_FIRST").value is False


def test_missing_session_is_unobservable():
    r=_build([_bar(21,95,105,100)])
    assert r.status=="UNOBSERVABLE_MISSING_DATA"
    assert r.outcome==""


def test_gap_cross_is_ambiguous():
    # prior close 100 -> session low above 110 means upper barrier was crossed in an
    # unobserved overnight gap; daily OHLC cannot give an exact first-touch instant.
    r=_build([_bar(21,111,115,112),_bar(22,95,105,100)])
    assert r.status=="AMBIGUOUS_GAP_CROSS"
    assert r.outcome==""


def test_barrier_order_and_direction_fail_closed():
    bad_upper=replace(_upper(), level=85.0)
    r=FP.build_daily_first_passage_label(
        _request(), bad_upper, _lower(), [],
        expected_sessions=["2026-09-21","2026-09-22"],
        calendar_provenance="VERIFIED_INPUT",
    )
    assert r.status=="INVALID_BARRIER_ORDER"
    bad_direction=replace(_upper(), direction="DOWN")
    r=FP.build_daily_first_passage_label(
        _request(), bad_direction, _lower(), [],
        expected_sessions=["2026-09-21","2026-09-22"],
        calendar_provenance="VERIFIED_INPUT",
    )
    assert r.status=="INVALID_BARRIER_DIRECTION"


def test_first_passage_is_independent_audit_outcome_kind(tmp_path):
    db=PA.PredictionAuditDB(tmp_path/"audit.duckdb")
    lineage=[PA.make_lineage(
        economic_factor_id="JP_EQUITY", representation_id="OSE_MICRO_FUTURES",
        instrument_type="FUTURE", representation_relation="DIRECT",
        temporal_role="PREVIOUS_SESSION_REFERENCE", resolved_role="PREVIOUS_SESSION_REFERENCE",
        venue_id="OSE_DERIVATIVES", calendar_id="OSE_DERIVATIVES",
        session_status="CLOSED", trading_date="2026-09-20",
        availability_status="NOT_AVAILABLE", quality_status="TEST",
        provider="fixture", source_type="TEST", source_frequency="DAILY",
        data_grade="RESEARCH_PROXY", point_in_time_safe=True,
        contract_code="JNU2612", contract_month="202612", roll_status="NONE",
        series_semantics="CONTRACT", source_snapshot_ids=["s"],
    )]
    art=PA.make_forecast_artifact(
        artifact_type="EVENT_PROBABILITY", calibration_domain="PRICE_DISTRIBUTION",
        probability_type="FIRST_PASSAGE", event_definition_id="FP_UPPER_FIRST_2D",
        label_type="FIRST_PASSAGE_UPPER_FIRST_2D", value=0.6,
        distribution_id="dist-fp", distribution_version="v1",
        generated_at=_dt(20,7), calibration_status_at_origin="UNCALIBRATED",
    )
    pred=PA.make_prediction(
        lineage,[art],target_family="OSAKA_MICRO",instrument="JNU",
        instrument_role="DIRECT",calendar_id="OSE_DERIVATIVES",frequency="DAILY",
        horizon="2d",sample_origin="FORWARD_PRECOMMITTED",
        label_window_id="2026-09-21/2026-09-22",
        label_window_start=_dt(21),label_window_end=_dt(22,6),
        forecast_origin=_dt(20,8),feature_cutoff_timestamp=_dt(20,7),
        build_id="w5-test",model="m",model_version="v1",
        v2_schema_versions=PA.v2_schema_versions(),
    )
    bound=replace(art,prediction_id=pred.prediction_id)
    db.append_prediction_bundle(pred,lineage,[bound])
    out=PA.make_outcome(
        prediction_id=pred.prediction_id,label_type=bound.label_type,
        outcome_kind="FIRST_PASSAGE",target_period=pred.label_window_id,
        actual_value=1.0,event_timestamp=_dt(22,6),available_at=_dt(22,7),
        forecast_artifact_id=bound.forecast_artifact_id,
    )
    assert db.append_outcome(out)==PA.APPEND_INSERTED
    assert PA.label_scope(bound.label_type)=="FIRST_PASSAGE"
    assert CE.PROBABILITY_TYPE_OUTCOME_KINDS["FIRST_PASSAGE"]==frozenset({"FIRST_PASSAGE"})
    assert PA.v2_schema_versions()["first_passage"]=="W5.1"
