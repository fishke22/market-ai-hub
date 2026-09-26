"""W3.1 outcome maturity / evaluation-as-of / homogeneous-scope regression."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from market_ai_hub.research.v2 import calibration_evaluation as CE
from market_ai_hub.research.v2 import evaluation_governance as EG
from market_ai_hub.research.v2 import prediction_audit as PA


def _dt(day: int, hour: int = 0, minute: int = 0) -> datetime:
    return datetime(2026, 9, day, hour, minute, tzinfo=timezone.utc)


@pytest.fixture
def db(tmp_path):
    return PA.PredictionAuditDB(tmp_path / "audit.duckdb")


def _lineage():
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
        trading_date="2026-09-24",
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
        source_snapshot_ids=["snap-1"],
    )


def _artifact(prediction_id: str = "", *, value: float = 0.7,
              event_definition_id: str = "EV_TOUCH_UP_1D",
              label_type: str = "TOUCH_UP_1D",
              generated_at: datetime = _dt(24, 7, 30)):
    return PA.make_forecast_artifact(
        prediction_id=prediction_id,
        artifact_type="EVENT_PROBABILITY",
        calibration_domain="TOUCH",
        probability_type="TOUCH",
        event_definition_id=event_definition_id,
        label_type=label_type,
        value=value,
        generated_at=generated_at,
        calibration_status_at_origin="UNCALIBRATED",
        source_snapshot_ids=["snap-1"],
    )


def _prediction(*, origin=_dt(24, 8), window_id="2026-09-25",
                window_start=_dt(25, 0), window_end=_dt(25, 6),
                model="m", model_version="v1",
                sample_origin="FORWARD_PRECOMMITTED",
                build_id="build-a", event_definition_id="EV_TOUCH_UP_1D",
                label_type="TOUCH_UP_1D", value=0.7):
    lin = [_lineage()]
    art = _artifact(
        "",
        value=value,
        event_definition_id=event_definition_id,
        label_type=label_type,
        generated_at=origin - timedelta(minutes=30),
    )
    pred = PA.make_prediction(
        lin,
        [art],
        target_family="OSAKA_MICRO",
        instrument="JNU",
        instrument_role="DIRECT",
        calendar_id="OSE_DERIVATIVES",
        frequency="DAILY",
        horizon="1d",
        sample_origin=sample_origin,
        label_window_id=window_id,
        label_window_start=window_start,
        label_window_end=window_end,
        forecast_origin=origin,
        feature_cutoff_timestamp=origin - timedelta(minutes=1),
        build_id=build_id,
        model=model,
        model_version=model_version,
        v2_schema_versions=PA.v2_schema_versions(),
    )
    bound_art = replace(art, prediction_id=pred.prediction_id)
    return pred, lin, bound_art


def _store_sample(db, *, actual=1.0, outcome_available=_dt(25, 7),
                  target_period="2026-09-25", **pred_kw):
    pred, lin, art = _prediction(**pred_kw)
    db.append_prediction_bundle(pred, lin, [art])
    out = PA.make_outcome(
        prediction_id=pred.prediction_id,
        label_type=art.label_type,
        outcome_kind="TOUCH",
        target_period=target_period,
        actual_value=actual,
        event_timestamp=pred.label_window_end,
        available_at=outcome_available,
        label_schema_version="2C.2",
        source_snapshot_ids=["out-1"],
        forecast_artifact_id=art.forecast_artifact_id,
    )
    db.append_outcome(out)
    return pred, art, out


def _governed(db, preds, *, evaluation_as_of=_dt(27), model="m",
              model_version="v1", sample_origin="FORWARD_PRECOMMITTED",
              label_type="TOUCH_UP_1D", event_definition_id="EV_TOUCH_UP_1D"):
    return EG.build_governed_evaluation_dataset(
        db,
        prediction_ids=[p.prediction_id for p in preds],
        evaluation_as_of=evaluation_as_of,
        target_family="OSAKA_MICRO",
        instrument="JNU",
        horizon="1d",
        model=model,
        model_version=model_version,
        artifact_type="EVENT_PROBABILITY",
        partition_role="FORWARD",
        window_start=_dt(20),
        window_end=_dt(30),
        label_type=label_type,
        sample_origin=sample_origin,
        calibration_domain="TOUCH",
        probability_type="TOUCH",
        event_definition_id=event_definition_id,
    )


def test_prediction_window_and_origin_are_identity_bound():
    a, _, _ = _prediction()
    b, _, _ = _prediction(sample_origin="RETROSPECTIVE_REPLAY")
    c, _, _ = _prediction(window_end=_dt(25, 7))
    assert a.prediction_id != b.prediction_id
    assert a.prediction_id != c.prediction_id
    assert PA.V2_PREDICTION_AUDIT_SCHEMA_VERSION == "2H.3"
    assert PA.v2_schema_versions()["evaluation_governance"] == "W3.1"


def test_partial_or_pre_origin_label_window_rejected():
    with pytest.raises(PA.PredictionAuditError):
        _prediction(window_end=None)
    with pytest.raises(PA.PredictionAuditError):
        _prediction(window_start=_dt(24, 7), window_end=_dt(25, 6))


def test_outcome_cannot_be_written_before_horizon_maturity(db):
    pred, lin, art = _prediction()
    db.append_prediction_bundle(pred, lin, [art])
    early = PA.make_outcome(
        prediction_id=pred.prediction_id,
        label_type=art.label_type,
        outcome_kind="TOUCH",
        target_period=pred.label_window_id,
        actual_value=1.0,
        event_timestamp=_dt(25, 5),
        available_at=_dt(25, 5),
        forecast_artifact_id=art.forecast_artifact_id,
    )
    with pytest.raises(PA.OutcomeMaturityError):
        db.append_outcome(early)


def test_outcome_target_period_must_match_sealed_window(db):
    pred, lin, art = _prediction()
    db.append_prediction_bundle(pred, lin, [art])
    wrong = PA.make_outcome(
        prediction_id=pred.prediction_id,
        label_type=art.label_type,
        outcome_kind="TOUCH",
        target_period="2026-09-26",
        actual_value=1.0,
        event_timestamp=_dt(25, 6),
        available_at=_dt(25, 7),
        forecast_artifact_id=art.forecast_artifact_id,
    )
    with pytest.raises(PA.OutcomeScopeError):
        db.append_outcome(wrong)


def test_governed_manifest_requires_aware_evaluation_as_of(db):
    p, _, _ = _store_sample(db)
    with pytest.raises(EG.EvaluationGovernanceError):
        _governed(db, [p], evaluation_as_of=datetime(2026, 9, 27))


def test_not_mature_at_evaluation_as_of_is_excluded(db):
    p, _, _ = _store_sample(db)
    man = _governed(db, [p], evaluation_as_of=_dt(25, 5))
    assert man.members == []
    assert {r.reason for r in man.rejected} == {"NOT_MATURE_AT_EVALUATION_AS_OF"}
    ready = EG.governance_readiness(man)
    assert ready["state"] == "INSUFFICIENT_EVIDENCE"
    assert ready["CALIBRATED"] is False


def test_outcome_later_than_evaluation_as_of_is_excluded(db):
    p, _, _ = _store_sample(db, outcome_available=_dt(25, 9))
    man = _governed(db, [p], evaluation_as_of=_dt(25, 8))
    assert man.members == []
    assert {r.reason for r in man.rejected} == {"OUTCOME_NOT_AVAILABLE_AT_EVALUATION_AS_OF"}


def test_forward_and_retrospective_samples_never_mix(db):
    p1, _, _ = _store_sample(db)
    p2, _, _ = _store_sample(
        db,
        sample_origin="RETROSPECTIVE_REPLAY",
        origin=_dt(25, 8),
        window_id="2026-09-26",
        window_start=_dt(26, 0),
        window_end=_dt(26, 6),
        outcome_available=_dt(26, 7),
        target_period="2026-09-26",
        build_id="build-b",
    )
    man = _governed(db, [p1, p2], evaluation_as_of=_dt(27))
    assert len(man.members) == 1
    assert {r.reason for r in man.rejected} == {"MIXED_OR_WRONG_SCOPE"}
    assert EG.evaluate_governed_manifest(db, man).status == "BLOCKED"


def test_model_version_scope_is_fail_closed(db):
    p1, _, _ = _store_sample(db)
    p2, _, _ = _store_sample(
        db,
        model_version="v2",
        origin=_dt(25, 8),
        window_id="2026-09-26",
        window_start=_dt(26, 0),
        window_end=_dt(26, 6),
        outcome_available=_dt(26, 7),
        target_period="2026-09-26",
        build_id="build-b",
    )
    man = _governed(db, [p1, p2], evaluation_as_of=_dt(27), model_version="v1")
    assert {r.reason for r in man.base_rejected} == {"WRONG_MODEL"}
    assert EG.evaluate_governed_manifest(db, man).status == "BLOCKED"
    assert EG.governance_readiness(man)["state"] == "BLOCKED"


def test_duplicate_logical_sample_is_blocked(db):
    p1, _, _ = _store_sample(db, build_id="build-a")
    p2, _, _ = _store_sample(db, build_id="build-b", value=0.8)
    assert p1.prediction_id != p2.prediction_id
    man = _governed(db, [p1, p2])
    assert man.members == []
    assert {r.reason for r in man.rejected} == {"DUPLICATE_LOGICAL_SAMPLE"}
    assert EG.evaluate_governed_manifest(db, man).status == "BLOCKED"


def test_valid_governed_samples_feed_closed_2i1_metrics(db):
    p1, _, _ = _store_sample(db, actual=1.0)
    p2, _, _ = _store_sample(
        db,
        actual=0.0,
        origin=_dt(25, 8),
        window_id="2026-09-26",
        window_start=_dt(26, 0),
        window_end=_dt(26, 6),
        outcome_available=_dt(26, 7),
        target_period="2026-09-26",
        build_id="build-b",
    )
    man = _governed(db, [p1, p2], evaluation_as_of=_dt(27))
    assert len(man.members) == 2
    assert man.scope.scope_id.startswith("w3_scope_")
    assert man.dataset_id.startswith("w3_ds_")
    result = EG.evaluate_governed_manifest(db, man)
    assert result.status == "EVALUATED"
    assert result.dataset_id == man.dataset_id
    assert result.probability.sample_count == 2
    ready = EG.governance_readiness(man)
    assert ready["state"] == "READY_FOR_EVALUATION"
    assert ready["CALIBRATION_FITTING"] == "NOT_STARTED"
    assert ready["CALIBRATED"] is False
    assert ready["coverage"]["valid_sample_count"] == 2


def test_missing_outcome_is_visible_in_coverage(db):
    p1, _, _ = _store_sample(db)
    pred, lin, art = _prediction(
        origin=_dt(25, 8),
        window_id="2026-09-26",
        window_start=_dt(26, 0),
        window_end=_dt(26, 6),
        build_id="build-b",
    )
    db.append_prediction_bundle(pred, lin, [art])
    man = _governed(db, [p1, pred], evaluation_as_of=_dt(27))
    assert len(man.members) == 1
    assert man.coverage["missing_outcome_count"] == 1
    assert man.coverage["rejection_counts"]["MISSING_OUTCOME"] == 1


def test_scope_requires_event_identity_for_probabilities(db):
    p, _, _ = _store_sample(db)
    with pytest.raises(EG.EvaluationGovernanceError):
        EG.build_governed_evaluation_dataset(
            db,
            prediction_ids=[p.prediction_id],
            evaluation_as_of=_dt(27),
            target_family="OSAKA_MICRO",
            instrument="JNU",
            horizon="1d",
            model="m",
            model_version="v1",
            artifact_type="EVENT_PROBABILITY",
            partition_role="FORWARD",
            window_start=_dt(20),
            window_end=_dt(30),
            label_type="TOUCH_UP_1D",
            sample_origin="FORWARD_PRECOMMITTED",
            calibration_domain="TOUCH",
            probability_type="TOUCH",
            event_definition_id="",
        )


@pytest.mark.parametrize(
    "artifact_value,actual_value",
    [(float("nan"), 100.0), (100.0, float("inf"))],
)
def test_nonfinite_numeric_samples_block_before_governance(db, artifact_value, actual_value):
    lineage = [_lineage()]
    art = PA.make_forecast_artifact(
        artifact_type="POINT",
        label_type="TERMINAL_CLOSE",
        value=artifact_value,
        generated_at=_dt(24, 7, 30),
        calibration_status_at_origin="UNCALIBRATED",
        source_snapshot_ids=["snap-1"],
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
        label_window_id="2026-09-25",
        label_window_start=_dt(25, 0),
        label_window_end=_dt(25, 6),
        forecast_origin=_dt(24, 8),
        feature_cutoff_timestamp=_dt(24, 7, 59),
        build_id="build-nonfinite",
        model="m",
        model_version="v1",
        v2_schema_versions=PA.v2_schema_versions(),
    )
    bound_art = replace(art, prediction_id=pred.prediction_id)
    db.append_prediction_bundle(pred, lineage, [bound_art])
    outcome = PA.make_outcome(
        prediction_id=pred.prediction_id,
        label_type="TERMINAL_CLOSE",
        outcome_kind="TERMINAL",
        target_period="2026-09-25",
        actual_value=actual_value,
        event_timestamp=_dt(25, 6),
        available_at=_dt(25, 7),
        label_schema_version="W3.2",
        source_snapshot_ids=["out-nonfinite"],
        forecast_artifact_id=bound_art.forecast_artifact_id,
    )
    db.append_outcome(outcome)

    manifest = EG.build_governed_evaluation_dataset(
        db,
        prediction_ids=[pred.prediction_id],
        evaluation_as_of=_dt(27),
        target_family="OSAKA_MICRO",
        instrument="JNU",
        horizon="1d",
        model="m",
        model_version="v1",
        artifact_type="POINT",
        partition_role="FORWARD",
        window_start=_dt(20),
        window_end=_dt(30),
        label_type="TERMINAL_CLOSE",
        sample_origin="FORWARD_PRECOMMITTED",
    )
    assert manifest.members == []
    assert {r.reason for r in manifest.base_rejected} == {"NONFINITE_VALUE"}
    assert EG.evaluate_governed_manifest(db, manifest).status == "BLOCKED"
