"""W4.1 governed calibration fitting regression tests.

Synthetic records prove engine behavior only; they are not market evidence.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from market_ai_hub.research.price_probability_map import (
    DistributionRecord,
    ProbabilityProvenance,
    calibration_evidence_ok,
)
from market_ai_hub.research.v2 import calibration_fitting as CF
from market_ai_hub.research.v2 import evaluation_governance as EG
from market_ai_hub.research.v2 import prediction_audit as PA


def _dt(year: int, month: int, day: int, hour: int = 0) -> datetime:
    return datetime(year, month, day, hour, tzinfo=timezone.utc)


@pytest.fixture
def db(tmp_path):
    return PA.PredictionAuditDB(tmp_path / "audit.duckdb")


def _lineage(trading_date: str):
    return PA.make_lineage(
        economic_factor_id="JP_EQUITY",
        representation_id="OSE_MICRO_FUTURES",
        instrument_type="FUTURE",
        representation_relation="DIRECT",
        temporal_role="PREVIOUS_SESSION_REFERENCE",
        resolved_role="PREVIOUS_SESSION_REFERENCE",
        venue_id="OSE_DERIVATIVES",
        calendar_id="OSE_DERIVATIVES",
        session_status="CLOSED",
        trading_date=trading_date,
        availability_status="NOT_AVAILABLE",
        quality_status="TEST",
        provider="fixture",
        source_type="TEST",
        source_frequency="DAILY",
        data_grade="RESEARCH_PROXY",
        point_in_time_safe=True,
        contract_code="JNU2612",
        contract_month="202612",
        roll_status="NONE",
        series_semantics="CONTRACT",
        source_snapshot_ids=[f"snap-{trading_date}"],
    )


def _store_probability_sample(
    db, *, origin: datetime, probability: float, actual: float,
    distribution_id: str = "dist-touch-v1",
):
    label_day = (origin + timedelta(days=1)).date().isoformat()
    window_start = datetime.combine(
        origin.date() + timedelta(days=1), datetime.min.time(), tzinfo=timezone.utc
    )
    window_end = window_start + timedelta(hours=6)
    lineage = [_lineage(origin.date().isoformat())]
    art = PA.make_forecast_artifact(
        artifact_type="EVENT_PROBABILITY",
        calibration_domain="PRICE_DISTRIBUTION",
        probability_type="TOUCH",
        event_definition_id="EV_TOUCH_UP_1D",
        label_type="TOUCH_UP_1D",
        value=probability,
        distribution_id=distribution_id,
        distribution_version="v1",
        generated_at=origin - timedelta(minutes=30),
        calibration_status_at_origin="UNCALIBRATED",
        source_snapshot_ids=[f"forecast-{origin.isoformat()}"],
    )
    pred = PA.make_prediction(
        lineage,
        [art],
        target_family="OSAKA_MICRO",
        instrument="JNU",
        instrument_role="DIRECT",
        calendar_id="OSE_DERIVATIVES",
        frequency="DAILY",
        horizon="1d",
        sample_origin="FORWARD_PRECOMMITTED",
        label_window_id=label_day,
        label_window_start=window_start,
        label_window_end=window_end,
        forecast_origin=origin,
        feature_cutoff_timestamp=origin - timedelta(minutes=1),
        build_id="w4-test-build",
        model="m",
        model_version="v1",
        v2_schema_versions=PA.v2_schema_versions(),
    )
    bound = replace(art, prediction_id=pred.prediction_id)
    db.append_prediction_bundle(pred, lineage, [bound])
    out = PA.make_outcome(
        prediction_id=pred.prediction_id,
        label_type=bound.label_type,
        outcome_kind="TOUCH",
        target_period=label_day,
        actual_value=actual,
        event_timestamp=window_end,
        available_at=window_end + timedelta(hours=1),
        label_schema_version="2C.2",
        source_snapshot_ids=[f"outcome-{origin.isoformat()}"],
        forecast_artifact_id=bound.forecast_artifact_id,
    )
    db.append_outcome(out)
    return pred


def _series(
    db, *, start: datetime, count: int, reversed_labels: bool = False,
    distribution_id: str = "dist-touch-v1",
):
    preds = []
    for i in range(count):
        y = float(i % 2)
        p = 0.65 if y == 1.0 else 0.35
        if reversed_labels:
            y = 1.0 - y
        preds.append(_store_probability_sample(
            db, origin=start + timedelta(days=i), probability=p, actual=y,
            distribution_id=distribution_id,
        ))
    return preds


def _manifest(db, preds, *, role: str, start: datetime, end: datetime):
    return EG.build_governed_evaluation_dataset(
        db,
        prediction_ids=[p.prediction_id for p in preds],
        evaluation_as_of=end + timedelta(days=2),
        target_family="OSAKA_MICRO",
        instrument="JNU",
        horizon="1d",
        model="m",
        model_version="v1",
        artifact_type="EVENT_PROBABILITY",
        partition_role=role,
        window_start=start - timedelta(hours=1),
        window_end=end + timedelta(hours=1),
        label_type="TOUCH_UP_1D",
        sample_origin="FORWARD_PRECOMMITTED",
        calibration_domain="PRICE_DISTRIBUTION",
        probability_type="TOUCH",
        event_definition_id="EV_TOUCH_UP_1D",
    )


def _test_protocol():
    return replace(
        CF.load_protocol(),
        min_fit_samples=10,
        min_validation_samples=10,
        min_final_oos_samples=10,
        min_class_count=2,
        min_calendar_span_days=5,
        bootstrap_replicates=200,
    )


def _fit_and_validation(db, *, reversed_validation: bool = False, n: int = 12):
    fit_start = _dt(2026, 1, 1, 8)
    val_start = _dt(2026, 5, 1, 8)
    fit_preds = _series(db, start=fit_start, count=n)
    val_preds = _series(db, start=val_start, count=n, reversed_labels=reversed_validation)
    cal = _manifest(
        db, fit_preds, role="CALIBRATION",
        start=fit_start, end=fit_start + timedelta(days=n - 1),
    )
    val = _manifest(
        db, val_preds, role="VALIDATION",
        start=val_start, end=val_start + timedelta(days=n - 1),
    )
    return cal, val


def test_protocol_is_pre_registered_and_forward_only():
    p = CF.load_protocol()
    assert p.schema_version == "W4.1"
    assert p.sample_origin == "FORWARD_PRECOMMITTED"
    assert p.fit_partition_role == "CALIBRATION"
    assert p.validation_partition_role == "VALIDATION"
    assert p.min_fit_samples == p.min_validation_samples == p.min_final_oos_samples == 50
    assert p.min_class_count == 10
    assert p.min_calendar_span_days == 30
    assert p.bootstrap_replicates == 1000
    assert p.confidence_level == pytest.approx(0.95)


def test_sigmoid_validation_creates_candidate_not_public_calibrated(db, tmp_path):
    cal, val = _fit_and_validation(db)
    result = CF.fit_and_validate(
        db, cal, val, protocol=_test_protocol(),
        store=CF.CalibrationArtifactStore(tmp_path / "calibration")
    )
    assert result.status == "EVALUATED_UNCALIBRATED"
    assert result.acceptance["accepted"] is True
    assert result.artifact_id.startswith("w4_cal_")
    assert result.model is not None and result.model.converged and result.model.slope >= 0.0
    assert result.calibrated_validation_metrics["brier_score"] < result.raw_validation_metrics["brier_score"]
    assert result.calibrated_validation_metrics["log_loss"] < result.raw_validation_metrics["log_loss"]
    assert result.evidence is not None
    assert result.evidence.status == "EVALUATED_UNCALIBRATED"
    assert result.evidence.metrics["final_oos_consumed"] is False
    assert result.acceptance["ci_nondegrade"]["brier"] is True
    assert result.acceptance["delta_ci"]["brier"]["confidence_level"] == pytest.approx(0.95)
    assert (tmp_path / "calibration" / f"{result.artifact_id}.json").exists()


def test_validation_regime_reversal_cannot_be_promoted(db):
    cal, val = _fit_and_validation(db, reversed_validation=True)
    result = CF.fit_and_validate(db, cal, val, protocol=_test_protocol())
    assert result.status == "EVALUATED_UNCALIBRATED"
    assert result.evidence.status == "EVALUATED_UNCALIBRATED"
    assert result.acceptance["accepted"] is False
    assert not all(result.acceptance["nondegrade"].values())


def test_sample_and_class_minimums_fail_closed_as_insufficient(db):
    cal, val = _fit_and_validation(db, n=6)
    result = CF.fit_and_validate(db, cal, val, protocol=_test_protocol())
    assert result.status == "INSUFFICIENT_EVIDENCE"
    assert result.artifact_id == ""
    assert result.evidence.status == "INSUFFICIENT_EVIDENCE"
    assert result.evidence.sample_sufficiency_status == "INSUFFICIENT"


def test_final_oos_is_never_accepted_as_validation_or_fit(db):
    cal, val = _fit_and_validation(db)
    final_oos = replace(val, scope=replace(val.scope, partition_role="FINAL_OOS"))
    with pytest.raises(CF.CalibrationFittingError, match="validation manifest must be VALIDATION"):
        CF.fit_and_validate(db, cal, final_oos)
    bad_fit = replace(cal, scope=replace(cal.scope, partition_role="FINAL_OOS"))
    with pytest.raises(CF.CalibrationFittingError, match="fit manifest must be CALIBRATION"):
        CF.fit_and_validate(db, bad_fit, val)


def test_scope_or_distribution_mismatch_is_blocked(db):
    cal, val = _fit_and_validation(db)
    wrong_scope = replace(val, scope=replace(val.scope, model_version="v2"))
    with pytest.raises(CF.CalibrationFittingError, match="scope mismatch"):
        CF.fit_and_validate(db, cal, wrong_scope, protocol=_test_protocol())

    mixed_start = _dt(2026, 5, 1, 8)
    preds = _series(db, start=_dt(2026, 7, 1, 8), count=11)
    preds += _series(
        db, start=_dt(2026, 8, 1, 8), count=1, distribution_id="dist-other-v1"
    )
    mixed = _manifest(
        db, preds, role="VALIDATION",
        start=_dt(2026, 7, 1, 8), end=_dt(2026, 8, 1, 8),
    )
    with pytest.raises(CF.CalibrationFittingError, match="mixed or missing distribution identity"):
        CF.fit_and_validate(db, cal, mixed, protocol=_test_protocol())


def test_one_use_final_oos_promotes_candidate_and_passes_ppm_gate(db, tmp_path):
    cal, val = _fit_and_validation(db)
    store = CF.CalibrationArtifactStore(tmp_path / "calibration")
    candidate = CF.fit_and_validate(db, cal, val, protocol=_test_protocol(), store=store)
    final_start = _dt(2026, 9, 1, 8)
    final_preds = _series(db, start=final_start, count=12)
    final_manifest = _manifest(
        db, final_preds, role="FINAL_OOS",
        start=final_start, end=final_start + timedelta(days=11),
    )
    result = CF.finalize_with_final_oos(db, candidate, final_manifest, store=store)
    assert result.status == "CALIBRATED"
    assert result.artifact_id.startswith("w4_final_")
    assert result.evidence.metrics["final_oos_consumed"] is True
    assert result.evidence.metrics["final_oos_dataset_id"] == final_manifest.dataset_id
    with pytest.raises(CF.CalibrationFittingError, match="FINAL_OOS_ALREADY_CONSUMED"):
        CF.finalize_with_final_oos(db, candidate, final_manifest, store=store)

    prov = ProbabilityProvenance(
        model_id="m",
        model_version="v1",
        dataset_version=result.evidence.dataset_version,
        feature_version="w3.2-terminal-close",
        protocol_version=result.evidence.protocol_version,
        distribution_method="EMPIRICAL",
        calibration_method=result.evidence.method,
        calibration_version=result.evidence.calibration_version,
        evaluation_window=result.evidence.evaluation_window,
        generated_at=result.evidence.evaluated_at,
        target_family="OSAKA_MICRO",
        instrument="JNU",
        horizon="1d",
        distribution_id="dist-touch-v1",
        distribution_version="v1",
    )
    dist = DistributionRecord(
        method="EMPIRICAL",
        capability="TERMINAL_SAMPLES",
        is_full_distribution=True,
        sample_count=12,
        effective_sample_count=12,
        minimum_required_sample=10,
        sample_sufficiency_status="SUFFICIENT",
        target_family="OSAKA_MICRO",
        instrument="JNU",
        horizon="1d",
        distribution_id="dist-touch-v1",
        distribution_version="v1",
    )
    ok, reasons = calibration_evidence_ok(
        result.evidence,
        probability_type="TOUCH",
        calibration_domain="PRICE_DISTRIBUTION",
        calibration_scope="SINGLE_INSTRUMENT",
        provenance=prov,
        distribution=dist,
        map_family="OSAKA_MICRO",
        instrument="JNU",
        horizon="1d",
    )
    assert ok is True
    assert reasons == []


def test_final_oos_failure_never_promotes(db, tmp_path):
    cal, val = _fit_and_validation(db)
    store = CF.CalibrationArtifactStore(tmp_path / "store")
    candidate = CF.fit_and_validate(db, cal, val, protocol=_test_protocol(), store=store)
    final_start = _dt(2026, 9, 1, 8)
    final_preds = _series(db, start=final_start, count=12, reversed_labels=True)
    final_manifest = _manifest(
        db, final_preds, role="FINAL_OOS",
        start=final_start, end=final_start + timedelta(days=11),
    )
    result = CF.finalize_with_final_oos(db, candidate, final_manifest, store=store)
    assert result.status == "EVALUATED_UNCALIBRATED"
    assert result.evidence.status == "EVALUATED_UNCALIBRATED"
    assert result.acceptance["accepted"] is False


def test_prediction_audit_accepts_terminal_event_probability_pair(db):
    origin = _dt(2026, 3, 1, 8)
    label_day = "2026-03-02"
    window_start = _dt(2026, 3, 2, 0)
    window_end = _dt(2026, 3, 2, 6)
    lineage = [_lineage("2026-03-01")]
    art = PA.make_forecast_artifact(
        artifact_type="EVENT_PROBABILITY",
        calibration_domain="PRICE_DISTRIBUTION",
        probability_type="TERMINAL",
        event_definition_id="EV_TERMINAL_ABOVE_1D",
        label_type="TERMINAL_ABOVE_1D",
        value=0.6,
        distribution_id="dist-terminal-v1",
        distribution_version="v1",
        generated_at=origin - timedelta(minutes=30),
        calibration_status_at_origin="UNCALIBRATED",
    )
    pred = PA.make_prediction(
        lineage, [art], target_family="OSAKA_MICRO", instrument="JNU",
        instrument_role="DIRECT", calendar_id="OSE_DERIVATIVES", frequency="DAILY",
        horizon="1d", sample_origin="FORWARD_PRECOMMITTED", label_window_id=label_day,
        label_window_start=window_start, label_window_end=window_end,
        forecast_origin=origin, feature_cutoff_timestamp=origin - timedelta(minutes=1),
        build_id="terminal-prob-test", model="m", model_version="v1",
        v2_schema_versions=PA.v2_schema_versions(),
    )
    bound = replace(art, prediction_id=pred.prediction_id)
    db.append_prediction_bundle(pred, lineage, [bound])
    outcome = PA.make_outcome(
        prediction_id=pred.prediction_id, label_type=bound.label_type,
        outcome_kind="TERMINAL", target_period=label_day, actual_value=1.0,
        event_timestamp=window_end, available_at=window_end + timedelta(hours=1),
        forecast_artifact_id=bound.forecast_artifact_id,
    )
    assert db.append_outcome(outcome) in {PA.APPEND_INSERTED, PA.APPEND_IDEMPOTENT}


def test_content_addressed_candidate_store_is_idempotent(db, tmp_path):
    cal, val = _fit_and_validation(db)
    store = CF.CalibrationArtifactStore(tmp_path / "store")
    first = CF.fit_and_validate(db, cal, val, protocol=_test_protocol(), store=store)
    second = CF.fit_and_validate(db, cal, val, protocol=_test_protocol(), store=store)
    assert first.artifact_id == second.artifact_id
    payload = store.read_payload(first.artifact_id)
    assert payload["artifact_id"] == first.artifact_id
    assert payload["evidence"]["status"] == "EVALUATED_UNCALIBRATED"
