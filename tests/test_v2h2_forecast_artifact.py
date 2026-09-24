"""Phase V2-H 2H.2 — forecast artifact audit + bundle atomicity tests (temporary DuckDB)."""
from __future__ import annotations

import sys
from dataclasses import replace
from datetime import datetime, timezone

import pytest

sys.path.insert(0, "src")

from market_ai_hub.research.v2 import prediction_audit as PA

UTC = timezone.utc


def _dt(d, h=0, m=0):
    return datetime(2026, 9, d, h, m, tzinfo=UTC)


@pytest.fixture()
def db(tmp_path):
    return PA.PredictionAuditDB(tmp_path / "audit.duckdb")


def _lineage(rep="OSE_MICRO_FUTURES", **kw):
    base = dict(economic_factor_id="JP_EQUITY", representation_id=rep, instrument_type="FUTURE",
                representation_relation="DIRECT", temporal_role="UNAVAILABLE",
                resolved_role="NOT_AVAILABLE", venue_id="OSE_DERIVATIVES",
                session_status="NIGHT_SESSION", availability_status="NOT_AVAILABLE",
                provider="jpx", source_frequency="DAILY")
    base.update(kw)
    return PA.make_lineage(**base)


def _artifact(prediction_id, **kw):
    base = dict(artifact_type="POINT", calibration_domain="PRICE", label_type="RETURN_1D",
                value=102.5, units="index_points", generated_at=_dt(24, 8, 30))
    base.update(kw)
    return PA.make_forecast_artifact(prediction_id=prediction_id, **base)


def _prediction(lineage=None, artifacts=None, **kw):
    base = dict(target_family="OSAKA_MICRO", instrument="JNU", calendar_id="OSE_DERIVATIVES",
                horizon="1d", forecast_origin=_dt(24, 9, 0), feature_cutoff_timestamp=_dt(24, 8, 0),
                build_id="test-build", model="m", model_version="v1",
                v2_schema_versions=PA.v2_schema_versions())
    base.update(kw)
    return PA.make_prediction(list(lineage or []), list(artifacts or []), **base)


def _bundle(db, artifacts=None, lineage=None, **pred_kw):
    lin = list(lineage if lineage is not None else [_lineage()])
    tmpl = list(artifacts or [])
    pred = _prediction(lin, tmpl, **pred_kw)
    arts = [replace(a, prediction_id=pred.prediction_id) for a in tmpl]
    return pred, lin, arts


# ── artifact identity / validation ──
def test_schema_version_2h2():
    assert PA.V2_PREDICTION_AUDIT_SCHEMA_VERSION == "2H.2"


def test_forecast_artifact_deterministic_identity():
    a1 = _artifact("p1", value=1.0)
    a2 = _artifact("p1", value=1.0)
    a3 = _artifact("p1", value=2.0)
    assert a1.forecast_artifact_id == a2.forecast_artifact_id
    assert a1.forecast_artifact_id != a3.forecast_artifact_id
    assert a1.forecast_artifact_id.startswith("v2h_art_")


def test_artifact_type_specific_required_fields():
    with pytest.raises(PA.PredictionAuditError):
        _artifact("p1", artifact_type="QUANTILE")                     # needs quantile_level
    with pytest.raises(PA.PredictionAuditError):
        _artifact("p1", artifact_type="INTERVAL")                     # needs bounds
    with pytest.raises(PA.PredictionAuditError):
        _artifact("p1", artifact_type="EVENT_PROBABILITY")            # needs event_definition_id
    with pytest.raises(PA.PredictionAuditError):
        _artifact("p1", artifact_type="NOT_AVAILABLE", value=1.0)     # must not carry value
    with pytest.raises(PA.PredictionAuditError):
        _artifact("p1", artifact_type="INTERVAL", lower_value=2.0, upper_value=1.0,
                  nominal_coverage=0.9)


def test_not_available_artifact_is_valid_audit_truth():
    a = _artifact("p1", artifact_type="NOT_AVAILABLE", value=None, raw_score=None)
    assert a.value is None and a.artifact_type == "NOT_AVAILABLE"


def test_artifact_generated_at_must_be_aware():
    with pytest.raises(PA.PredictionAuditError):
        _artifact("p1", generated_at=datetime(2026, 9, 24, 8, 30))


# ── prediction binding ──
def test_prediction_digest_binds_forecast_artifacts():
    lin = [_lineage()]
    a = _artifact("x")
    p_no = PA.make_prediction(lin, [], target_family="T", forecast_origin=_dt(24, 9, 0),
                              feature_cutoff_timestamp=_dt(24, 8, 0))
    p_yes = PA.make_prediction(lin, [a], target_family="T", forecast_origin=_dt(24, 9, 0),
                               feature_cutoff_timestamp=_dt(24, 8, 0))
    assert p_no.forecast_artifact_digest == ""
    assert p_yes.forecast_artifact_digest == PA.forecast_artifact_digest([a])
    assert p_no.prediction_id != p_yes.prediction_id


def test_generated_at_after_origin_blocked(db):
    pred, lin, arts = _bundle(db, artifacts=[_artifact("x", generated_at=_dt(24, 10, 0))])
    with pytest.raises(PA.ArtifactTemporalError) as e:
        db.append_prediction_bundle(pred, lin, arts)
    assert e.value.code == PA.BLOCKED_ARTIFACT_TEMPORAL


def test_bundle_insert_round_trip_verifies(db):
    pred, lin, arts = _bundle(db, artifacts=[_artifact("x")])
    assert db.append_prediction_bundle(pred, lin, arts) == PA.APPEND_INSERTED
    assert db.append_prediction_bundle(pred, lin, arts) == PA.APPEND_IDEMPOTENT
    stored = db.get_forecast_artifacts(pred.prediction_id)
    assert [a.forecast_artifact_id for a in stored] == [a.forecast_artifact_id for a in arts]
    assert stored[0].value == 102.5 and stored[0].generated_at == _dt(24, 8, 30)
    assert db.get_forecast_artifact(stored[0].forecast_artifact_id) == stored[0]
    assert db.get_prediction(pred.prediction_id).forecast_artifact_digest == pred.forecast_artifact_digest
    assert db.verify_prediction(pred.prediction_id) is True


def test_bundle_insert_atomic_rollback(db, monkeypatch):
    pred, lin, arts = _bundle(db, artifacts=[_artifact("x")])

    def boom(*a, **k):
        raise RuntimeError("simulated artifact write failure")

    monkeypatch.setattr(db, "_insert_artifact_rows", boom)
    with pytest.raises(RuntimeError):
        db.append_prediction_bundle(pred, lin, arts)
    assert db.list_prediction_ids() == []          # no partial prediction
    assert db.get_lineage(pred.prediction_id) == []
    assert db.get_forecast_artifacts(pred.prediction_id) == []


def test_forecast_artifact_cannot_be_added_secretly_after_prediction(db):
    lin = [_lineage()]
    pred = _prediction(lin, [])
    assert db.append_prediction_bundle(pred, lin, []) == PA.APPEND_INSERTED
    art = _artifact(pred.prediction_id)
    # same prediction_id but now carrying an artifact digest -> different payload
    tampered = replace(pred, forecast_artifact_digest=PA.forecast_artifact_digest([art]))
    with pytest.raises(PA.IdCollisionError):
        db.append_prediction_bundle(tampered, lin, [art])
    assert db.get_forecast_artifacts(pred.prediction_id) == []


def test_2h1_append_prediction_refuses_artifact_digest(db):
    lin = [_lineage()]
    pred = _prediction(lin, [])
    with_art = replace(pred, forecast_artifact_digest="v2h_artdig_deadbeef")
    with pytest.raises(PA.ArtifactBindingError):
        db.append_prediction(with_art, lin)


def test_artifact_from_other_prediction_blocked(db):
    pred, lin, arts = _bundle(db, artifacts=[_artifact("x")])
    foreign = replace(arts[0], prediction_id="v2h_pred_0000000000000000")
    with pytest.raises(PA.ArtifactBindingError):
        db.append_prediction_bundle(pred, lin, [foreign])


def test_artifact_digest_mismatch_blocked(db):
    pred, lin, arts = _bundle(db, artifacts=[_artifact("x")])
    tampered = replace(pred, forecast_artifact_digest="v2h_artdig_deadbeef")
    with pytest.raises(PA.PredictionAuditError):
        db.append_prediction_bundle(tampered, lin, arts)


# ── raw score / calibration separation ──
def test_raw_score_remains_non_probability():
    a = _artifact("p1", artifact_type="CLASS_SCORE", class_label="up", raw_score=1.37, value=None)
    assert a.raw_score == 1.37 and a.value is None
    assert PA.is_public_probability(a) is False


def test_uncalibrated_event_probability_remains_non_public():
    uncal = _artifact("p1", artifact_type="EVENT_PROBABILITY", event_definition_id="TOUCH_1D",
                      label_type="TOUCH_1D", value=0.72, calibration_status_at_origin="UNCALIBRATED")
    assert PA.is_public_probability(uncal) is False
    cal = _artifact("p1", artifact_type="EVENT_PROBABILITY", event_definition_id="TOUCH_1D",
                    label_type="TOUCH_1D", value=0.72,
                    calibration_status_at_origin="CALIBRATED", calibration_evidence_id="ev-1")
    assert PA.is_public_probability(cal) is True


def test_uncalibrated_probability_persisted_but_not_public(db):
    pred, lin, arts = _bundle(db, artifacts=[
        _artifact("x", artifact_type="EVENT_PROBABILITY", event_definition_id="TOUCH_1D",
                  label_type="TOUCH_1D", value=0.72)])
    db.append_prediction_bundle(pred, lin, arts)
    stored = db.get_forecast_artifacts(pred.prediction_id)[0]
    assert stored.value == 0.72
    assert stored.calibration_status_at_origin == "UNCALIBRATED"
    assert PA.is_public_probability(stored) is False


# ── outcome binding ──
def _outcome(prediction_id, **kw):
    base = dict(prediction_id=prediction_id, label_type="RETURN_1D", outcome_kind="RETURN",
                target_period="2026-09-25", actual_value=0.012,
                event_timestamp=_dt(25, 6, 0), available_at=_dt(25, 6, 0),
                label_schema_version="2C.2")
    base.update(kw)
    return PA.make_outcome(**base)


def test_artifact_outcome_compatible_pairing_allowed(db):
    pred, lin, arts = _bundle(db, artifacts=[_artifact("x")])
    db.append_prediction_bundle(pred, lin, arts)
    out = _outcome(pred.prediction_id, forecast_artifact_id=arts[0].forecast_artifact_id)
    assert db.append_outcome(out) == PA.APPEND_INSERTED
    assert db.get_outcomes(pred.prediction_id)[0].forecast_artifact_id == arts[0].forecast_artifact_id


def test_touch_probability_with_terminal_outcome_blocked(db):
    pred, lin, arts = _bundle(db, artifacts=[
        _artifact("x", artifact_type="EVENT_PROBABILITY", event_definition_id="TOUCH_1D",
                  label_type="TOUCH_1D", value=0.7)])
    db.append_prediction_bundle(pred, lin, arts)
    out = _outcome(pred.prediction_id, outcome_kind="TERMINAL", label_type="TERMINAL_1D",
                   forecast_artifact_id=arts[0].forecast_artifact_id)
    with pytest.raises(PA.ArtifactOutcomeMismatchError):
        db.append_outcome(out)


def test_direction_score_with_touch_outcome_blocked(db):
    pred, lin, arts = _bundle(db, artifacts=[
        _artifact("x", artifact_type="CLASS_SCORE", class_label="up", raw_score=1.1,
                  label_type="DIRECTION_1D", value=None)])
    db.append_prediction_bundle(pred, lin, arts)
    out = _outcome(pred.prediction_id, outcome_kind="TOUCH", label_type="TOUCH_1D",
                   forecast_artifact_id=arts[0].forecast_artifact_id)
    with pytest.raises(PA.ArtifactOutcomeMismatchError):
        db.append_outcome(out)


def test_direction_score_with_direction_outcome_allowed(db):
    pred, lin, arts = _bundle(db, artifacts=[
        _artifact("x", artifact_type="CLASS_SCORE", class_label="up", raw_score=1.1,
                  label_type="DIRECTION_1D", value=None)])
    db.append_prediction_bundle(pred, lin, arts)
    out = _outcome(pred.prediction_id, outcome_kind="DIRECTION", label_type="DIRECTION_1D",
                   actual_value=None, actual_state="up",
                   forecast_artifact_id=arts[0].forecast_artifact_id)
    assert db.append_outcome(out) == PA.APPEND_INSERTED


def test_artifact_outcome_cross_prediction_blocked(db):
    p1, l1, a1 = _bundle(db, artifacts=[_artifact("x", value=101.0)])
    db.append_prediction_bundle(p1, l1, a1)
    p2, l2, a2 = _bundle(db, artifacts=[_artifact("y", value=202.0)])
    db.append_prediction_bundle(p2, l2, a2)
    assert p1.prediction_id != p2.prediction_id
    out = _outcome(p2.prediction_id, forecast_artifact_id=a1[0].forecast_artifact_id)
    with pytest.raises(PA.ArtifactBindingError):
        db.append_outcome(out)


def test_artifact_outcome_unknown_artifact_blocked(db):
    pred, lin, arts = _bundle(db, artifacts=[_artifact("x")])
    db.append_prediction_bundle(pred, lin, arts)
    out = _outcome(pred.prediction_id, forecast_artifact_id="v2h_art_0000000000000000")
    with pytest.raises(PA.ArtifactNotFoundError):
        db.append_outcome(out)


def test_outcome_before_forecast_origin_blocked(db):
    pred, lin, arts = _bundle(db, artifacts=[_artifact("x")])
    db.append_prediction_bundle(pred, lin, arts)
    out = _outcome(pred.prediction_id, available_at=_dt(24, 1, 0), event_timestamp=_dt(24, 1, 0))
    with pytest.raises(PA.OutcomeTemporalError):
        db.append_outcome(out)


def test_outcome_without_artifact_binding_still_allowed(db):
    pred, lin, arts = _bundle(db, artifacts=[_artifact("x")])
    db.append_prediction_bundle(pred, lin, arts)
    assert db.append_outcome(_outcome(pred.prediction_id)) == PA.APPEND_INSERTED


# ── append-only / integrity preserved ──
def test_no_update_delete_api_preserved():
    assert not hasattr(PA.PredictionAuditDB, "update")
    assert not hasattr(PA.PredictionAuditDB, "delete")
    src = open(PA.__file__, encoding="utf-8").read()
    assert not __import__("re").search(
        r"\b(UPDATE|DELETE)\s+(predictions|factor_lineage|forecast_artifacts|outcomes)\b", src, __import__("re").I)


def test_outcome_append_does_not_mutate_prediction_or_artifacts(db):
    pred, lin, arts = _bundle(db, artifacts=[_artifact("x")])
    db.append_prediction_bundle(pred, lin, arts)
    before_pred = db.get_prediction(pred.prediction_id)
    before_arts = db.get_forecast_artifacts(pred.prediction_id)
    db.append_outcome(_outcome(pred.prediction_id, forecast_artifact_id=arts[0].forecast_artifact_id))
    assert db.get_prediction(pred.prediction_id) == before_pred
    assert db.get_forecast_artifacts(pred.prediction_id) == before_arts
    assert db.verify_prediction(pred.prediction_id) is True
