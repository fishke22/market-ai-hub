"""Phase V2-I 2I.1 \u2014 calibration evaluation foundation tests (temporary DuckDB, no fitting)."""
from __future__ import annotations

import math
import sys
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, "src")

from market_ai_hub.research.v2 import calibration_evaluation as CE
from market_ai_hub.research.v2 import prediction_audit as PA

UTC = timezone.utc
T0 = datetime(2026, 9, 24, 9, 0, tzinfo=UTC)


def _dt(d, h=9, m=0):
    return datetime(2026, 9, d, h, m, tzinfo=UTC)


@pytest.fixture()
def db(tmp_path):
    return PA.PredictionAuditDB(tmp_path / "audit.duckdb")


def _lineage():
    return PA.make_lineage(
        economic_factor_id="JP_EQUITY", representation_id="OSE_MICRO_FUTURES",
        instrument_type="FUTURE", representation_relation="DIRECT", temporal_role="UNAVAILABLE",
        resolved_role="NOT_AVAILABLE", venue_id="OSE_DERIVATIVES", session_status="NIGHT_SESSION",
        availability_status="NOT_AVAILABLE", provider="jpx", source_frequency="DAILY")


def _prediction(lin, artifacts, **kw):
    base = dict(target_family="OSAKA_MICRO", instrument="JNU", calendar_id="OSE_DERIVATIVES",
                horizon="1d", forecast_origin=_dt(24), feature_cutoff_timestamp=_dt(24, 8),
                build_id="test-build", model="m", model_version="v1",
                v2_schema_versions=PA.v2_schema_versions())
    base.update(kw)
    return PA.make_prediction(lin, artifacts, **base)


def _artifact(prediction_id, **kw):
    base = dict(artifact_type="EVENT_PROBABILITY", calibration_domain="DIRECTION",
                label_type="TOUCH_UP_1D", probability_type="TOUCH", event_definition_id="EV_UP_1D",
                value=0.7, generated_at=_dt(24, 8, 30))
    base.update(kw)
    return PA.make_forecast_artifact(prediction_id=prediction_id, **base)


def _sample(db, *, value=0.7, actual=1.0, kind="TOUCH", label="TOUCH_UP_1D", ptype="TOUCH",
            event_id="EV_UP_1D", instrument="JNU", target_family="OSAKA_MICRO", horizon="1d",
            origin=T0, available=_dt(25), artifact_type="EVENT_PROBABILITY", **akw):
    """一個完整可評估樣本：prediction + bound EVENT_PROBABILITY artifact + settled outcome."""
    lin = [_lineage()]
    a = _artifact("", artifact_type=artifact_type, label_type=label, value=value,
                  probability_type=ptype, event_definition_id=event_id,
                  generated_at=origin - timedelta(minutes=30), **akw)
    pred = _prediction(lin, [a], forecast_origin=origin, instrument=instrument,
                       target_family=target_family, horizon=horizon,
                       feature_cutoff_timestamp=origin - timedelta(hours=1))
    arts = [replace(x, prediction_id=pred.prediction_id) for x in [a]]
    db.append_prediction_bundle(pred, lin, arts)
    out = PA.make_outcome(prediction_id=pred.prediction_id, label_type=label, outcome_kind=kind,
                          target_period="1d", actual_value=actual, event_timestamp=available,
                          available_at=available, forecast_artifact_id=arts[0].forecast_artifact_id)
    db.append_outcome(out)
    return pred, arts[0], out


def _manifest(db, preds, **kw):
    base = dict(prediction_ids=[p.prediction_id for p in preds], target_family="OSAKA_MICRO",
                instrument="JNU", horizon="1d", artifact_type="EVENT_PROBABILITY",
                partition_role="CALIBRATION", window_start=_dt(20), window_end=_dt(30),
                probability_type="TOUCH", event_definition_id="EV_UP_1D")
    base.update(kw)
    return CE.build_evaluation_dataset(db, **base)


def _no_outcome_sample(db, value=0.4, **kw):
    lin = [_lineage()]
    a = _artifact("", value=value, **kw)
    pred = _prediction(lin, [a])
    db.append_prediction_bundle(pred, lin, [replace(a, prediction_id=pred.prediction_id)])
    return pred


# \u2500\u2500 schema / no-fitting boundary \u2500\u2500
def test_schema_version_2i1_and_no_calibrated_status():
    assert CE.V2_CALIBRATION_EVALUATION_SCHEMA_VERSION == "2I.1"
    assert "CALIBRATED" not in CE.EVIDENCE_STATUSES
    assert "CALIBRATED" not in CE.EVALUATION_STATUSES
    assert PA.v2_schema_versions()["calibration_evaluation"] == "2I.1"


def test_status_vocabulary_is_closed():
    assert set(CE.EVALUATION_STATUSES) == {"EVALUATED", "INSUFFICIENT_SAMPLE",
                                          "NOT_EVALUATABLE", "BLOCKED"}
    assert set(CE.PARTITION_ROLES) == {"CALIBRATION", "VALIDATION", "FINAL_OOS", "FORWARD"}
    assert set(CE.EVIDENCE_STATUSES) == {"INSUFFICIENT_EVIDENCE", "EVALUATED_UNCALIBRATED"}


# \u2500\u2500 exact toy metrics \u2500\u2500
def test_brier_exact_toy_case():
    assert CE.brier_score([(0.1, 0.0), (0.9, 1.0)]) == pytest.approx(0.01)
    assert CE.brier_score([(0.5, 1.0)]) == pytest.approx(0.25)


def test_log_loss_exact_toy_case():
    assert CE.log_loss([(0.5, 1.0), (0.5, 0.0)]) == pytest.approx(math.log(2.0))
    assert CE.log_loss([(0.25, 1.0)]) == pytest.approx(-math.log(0.25))


def test_log_loss_epsilon_clipping_is_stable_and_recorded():
    ll = CE.log_loss([(0.0, 0.0), (1.0, 1.0)])
    assert math.isfinite(ll) and 0.0 <= ll < 1e-12
    assert CE.log_loss([(0.0, 1.0)], epsilon=1e-15) == pytest.approx(-math.log(1e-15))
    assert CE.LOG_LOSS_EPSILON == 1e-15
    m = CE.ProbabilityMetrics(sample_count=2, brier_score=0.0, log_loss=0.0, base_rate=0.0,
                              mean_predicted_probability=0.0, ece=0.0, mce=0.0)
    assert m.log_loss_epsilon == 1e-15
    with pytest.raises(CE.CalibrationEvaluationError):
        CE.log_loss([(0.5, 1.0)], epsilon=0.0)


# \u2500\u2500 reliability bins \u2500\u2500
def test_reliability_bin_boundaries_p0_and_p1():
    bins = CE.reliability_bins([(0.0, 1.0), (1.0, 1.0)])
    assert len(bins) == 10
    assert bins[0].count == 1 and bins[0].lower == 0.0 and bins[0].upper == pytest.approx(0.1)
    assert bins[9].count == 1 and bins[9].upper == 1.0 and bins[9].lower == pytest.approx(0.9)
    assert sum(b.count for b in bins) == 2
    assert all(b.mean_predicted is None and b.gap is None for b in bins[1:9])


def test_reliability_bins_are_equal_width_and_cover_unit_interval():
    bins = CE.reliability_bins([])
    assert bins[0].lower == 0.0 and bins[-1].upper == 1.0
    for lo, hi in zip(bins, bins[1:]):
        assert lo.upper == pytest.approx(hi.lower)
        assert hi.upper - hi.lower == pytest.approx(0.1)


def test_ece_mce_deterministic_toy_case():
    pairs = [(0.1, 1.0), (0.1, 0.0)]          # 兩筆都落在 [0.1, 0.2) 這一 bin
    bins = CE.reliability_bins(pairs)
    b = bins[1]
    assert b.lower == pytest.approx(0.1) and b.upper == pytest.approx(0.2)
    assert b.count == 2 and b.mean_predicted == pytest.approx(0.1)
    assert b.empirical_rate == pytest.approx(0.5) and b.gap == pytest.approx(0.4)
    assert bins[0].count == 0 and bins[2].count == 0
    assert bins == CE.reliability_bins(pairs)
    n = 2
    ece = sum(x.count / n * x.gap for x in bins if x.count)
    mce = max(x.gap for x in bins if x.count)
    assert ece == pytest.approx(0.4) and mce == pytest.approx(0.4)


# \u2500\u2500 probability evaluation through the engine \u2500\u2500
def test_probability_evaluation_end_to_end(db):
    p1, _, _ = _sample(db, value=0.1, actual=1.0, origin=_dt(24))
    p2, _, _ = _sample(db, value=0.1, actual=0.0, origin=_dt(23))
    res = CE.evaluate_manifest(db, _manifest(db, [p1, p2]))
    assert res.status == "EVALUATED" and res.sample_count == 2
    pm = res.probability
    assert pm.brier_score == pytest.approx(0.41)          # (0.81 + 0.01)/2
    assert pm.base_rate == pytest.approx(0.5)
    assert pm.mean_predicted_probability == pytest.approx(0.1)
    assert pm.ece == pytest.approx(0.4) and pm.mce == pytest.approx(0.4)
    assert pm.log_loss_epsilon == 1e-15
    assert sum(b.count for b in pm.reliability_bins) == 2


def test_single_sample_is_insufficient_not_evaluated(db):
    p1, _, _ = _sample(db, value=0.3, actual=1.0)
    res = CE.evaluate_manifest(db, _manifest(db, [p1]))
    assert res.status == "INSUFFICIENT_SAMPLE" and res.probability is None


def test_p0_p1_extremes_evaluated_without_overflow(db):
    p1, _, _ = _sample(db, value=0.0, actual=0.0)
    p2, _, _ = _sample(db, value=1.0, actual=1.0)
    res = CE.evaluate_manifest(db, _manifest(db, [p1, p2]))
    assert res.status == "EVALUATED"
    assert res.probability.brier_score == 0.0
    assert math.isfinite(res.probability.log_loss)


# \u2500\u2500 probability-only gates \u2500\u2500
def test_raw_class_score_cannot_enter_probability_metrics(db):
    a = _artifact("", artifact_type="CLASS_SCORE", class_label="UP", value=None,
                  raw_score=1.7, probability_type="", event_definition_id="",
                  label_type="DIRECTION_1D")
    pred = _prediction([_lineage()], [a])
    arts = [replace(a, prediction_id=pred.prediction_id)]
    db.append_prediction_bundle(pred, [_lineage()], arts)
    db.append_outcome(PA.make_outcome(
        prediction_id=pred.prediction_id, label_type="DIRECTION_1D", outcome_kind="DIRECTION",
        actual_value=1.0, event_timestamp=_dt(25), available_at=_dt(25),
        forecast_artifact_id=arts[0].forecast_artifact_id))
    man = CE.build_evaluation_dataset(
        db, prediction_ids=[pred.prediction_id], target_family="OSAKA_MICRO", instrument="JNU",
        horizon="1d", artifact_type="EVENT_PROBABILITY", partition_role="CALIBRATION",
        window_start=_dt(20), window_end=_dt(30))
    assert man.members == [] and {r.reason for r in man.rejected} == {"WRONG_PROBABILITY_TYPE"}
    assert CE.evaluate_manifest(db, man).probability is None
    man2 = CE.build_evaluation_dataset(
        db, prediction_ids=[pred.prediction_id], target_family="OSAKA_MICRO", instrument="JNU",
        horizon="1d", artifact_type="CLASS_SCORE", partition_role="CALIBRATION",
        window_start=_dt(20), window_end=_dt(30))
    assert len(man2.members) == 1
    res2 = CE.evaluate_manifest(db, man2)
    assert res2.status == "NOT_EVALUATABLE" and res2.probability is None
    assert "never treated as a probability" in res2.reason


def test_event_probability_out_of_range_is_blocked(db):
    p1, _, _ = _sample(db, value=1.5, actual=1.0)
    res = CE.evaluate_manifest(db, _manifest(db, [p1]))
    assert res.status == "BLOCKED" and "NOT_PROBABILITY" in res.reason


def test_terminal_touch_mismatch_blocked(db):
    p1, _, _ = _sample(db, value=0.6, actual=1.0, ptype="TERMINAL", kind="TOUCH")
    res = CE.evaluate_manifest(db, _manifest(db, [p1], probability_type=""))
    assert res.status == "BLOCKED" and "WRONG_PROBABILITY_TYPE" in res.reason


def test_unknown_probability_type_is_fail_closed(db):
    p1, _, _ = _sample(db, value=0.6, actual=1.0, ptype="MADE_UP_FAMILY", kind="TOUCH")
    res = CE.evaluate_manifest(db, _manifest(db, [p1], probability_type=""))
    assert res.status == "BLOCKED" and "WRONG_PROBABILITY_TYPE" in res.reason


def test_not_available_artifact_cannot_become_probability(db):
    a = _artifact("", artifact_type="NOT_AVAILABLE", value=None, probability_type="",
                  event_definition_id="", class_label="", raw_score=None)
    pred = _prediction([_lineage()], [a])
    db.append_prediction_bundle(pred, [_lineage()], [replace(a, prediction_id=pred.prediction_id)])
    man = CE.build_evaluation_dataset(
        db, prediction_ids=[pred.prediction_id], target_family="OSAKA_MICRO", instrument="JNU",
        horizon="1d", artifact_type="EVENT_PROBABILITY", partition_role="CALIBRATION",
        window_start=_dt(20), window_end=_dt(30))
    assert man.members == []
    assert CE.evaluate_manifest(db, man).probability is None


# \u2500\u2500 pairing rejections \u2500\u2500
def test_cross_target_horizon_model_blocked(db):
    p1, _, _ = _sample(db, value=0.4, actual=1.0)
    r_target = CE.evaluate_manifest(db, _manifest(db, [p1], instrument="TX"))
    r_horizon = CE.evaluate_manifest(db, _manifest(db, [p1], horizon="5d"))
    r_model = CE.evaluate_manifest(db, _manifest(db, [p1], model="other"))
    assert r_target.status == r_horizon.status == r_model.status == "BLOCKED"
    assert "WRONG_TARGET" in r_target.reason
    assert "WRONG_HORIZON" in r_horizon.reason
    assert "WRONG_MODEL" in r_model.reason


def test_cross_prediction_and_unknown_prediction_blocked(db):
    p1, _, _ = _sample(db, value=0.4, actual=1.0)
    man = CE.build_evaluation_dataset(
        db, prediction_ids=[p1.prediction_id, "v2h_pred_does_not_exist"],
        target_family="OSAKA_MICRO", instrument="JNU", horizon="1d",
        artifact_type="EVENT_PROBABILITY", partition_role="CALIBRATION",
        window_start=_dt(20), window_end=_dt(30))
    assert [r.reason for r in man.rejected] == ["CROSS_PREDICTION"]
    assert CE.evaluate_manifest(db, man).status == "BLOCKED"


def test_members_never_cross_predictions(db):
    p1, a1, _ = _sample(db, value=0.4, actual=1.0)
    p2, _, _ = _sample(db, value=0.5, actual=0.0)
    man = _manifest(db, [p1, p2])
    assert len(man.members) == 2
    for m in man.members:
        art = db.get_forecast_artifact(m.forecast_artifact_id)
        assert art.prediction_id == m.prediction_id
        assert [o for o in db.get_outcomes(m.prediction_id) if o.outcome_id == m.outcome_id]
    assert {m.forecast_artifact_id for m in man.members} == {
        a1.forecast_artifact_id, man.members[1].forecast_artifact_id}


def test_missing_outcome_is_non_blocking_but_excluded(db):
    pred = _no_outcome_sample(db, value=0.4)
    p2, _, _ = _sample(db, value=0.6, actual=1.0)
    man = _manifest(db, [pred, p2])
    assert {r.reason for r in man.rejected} == {"MISSING_OUTCOME"}
    assert not man.is_blocked()
    res = CE.evaluate_manifest(db, man)
    assert res.status == "INSUFFICIENT_SAMPLE" and res.sample_count == 1


def test_no_settled_outcome_is_not_evaluatable(db):
    man = CE.build_evaluation_dataset(
        db, prediction_ids=[], target_family="OSAKA_MICRO", instrument="JNU", horizon="1d",
        artifact_type="EVENT_PROBABILITY", partition_role="CALIBRATION",
        window_start=_dt(20), window_end=_dt(30))
    res = CE.evaluate_manifest(db, man)
    assert res.status == "NOT_EVALUATABLE" and res.probability is None
    assert res.reason == "NO_SETTLED_PROBABILITY_SAMPLE"


def test_future_outcome_cannot_even_be_stored(db):
    """洩漏防線第一層（2H.2 寫入邊界）：available_at < forecast_origin 直接拒收。"""
    with pytest.raises(PA.OutcomeTemporalError):
        _sample(db, value=0.4, actual=1.0, origin=T0, available=_dt(23))


def test_leakage_recheck_in_evaluation_is_defence_in_depth(db):
    """第二層：即使 DB 內真有違規樣本（繞過寫入邊界），2I.1 也以 LEAKAGE_FUTURE 拒收。"""
    lin = [_lineage()]
    a = _artifact("", value=0.4)
    pred = _prediction(lin, [a], forecast_origin=T0)
    art = replace(a, prediction_id=pred.prediction_id)
    db.append_prediction_bundle(pred, lin, [art])
    leaked = replace(PA.make_outcome(
        prediction_id=pred.prediction_id, label_type="TOUCH_UP_1D", outcome_kind="TOUCH",
        actual_value=1.0, event_timestamp=_dt(23), available_at=_dt(23),
        forecast_artifact_id=art.forecast_artifact_id), outcome_id="")
    import duckdb
    con = duckdb.connect(db.path)
    con.execute(
        "INSERT INTO outcomes (outcome_id, prediction_id, label_type, outcome_kind, available_at, "
        "forecast_artifact_id, payload_json, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, now())",
        [PA.outcome_identity(PA.outcome_payload(leaked)), pred.prediction_id, leaked.label_type,
         leaked.outcome_kind, _dt(23).replace(tzinfo=None),
         leaked.forecast_artifact_id, PA.canonical_json(PA.outcome_payload(leaked))])
    con.close()
    man = CE.build_evaluation_dataset(
        db, prediction_ids=[pred.prediction_id], target_family="OSAKA_MICRO", instrument="JNU",
        horizon="1d", artifact_type="EVENT_PROBABILITY", partition_role="CALIBRATION",
        window_start=_dt(20), window_end=_dt(30))
    assert [r.reason for r in man.rejected] == ["LEAKAGE_FUTURE"]
    assert man.members == []
    res = CE.evaluate_manifest(db, man)
    assert res.status == "BLOCKED" and "LEAKAGE_FUTURE" in res.reason


def test_non_binary_outcome_excluded_from_probability(db):
    p1, _, _ = _sample(db, value=0.4, actual=0.37)
    man = _manifest(db, [p1])
    assert man.members == []
    assert {r.reason for r in man.rejected} == {"NON_BINARY_OUTCOME"}


def test_outside_window_blocked(db):
    p1, _, _ = _sample(db, value=0.4, actual=1.0)
    res = CE.evaluate_manifest(db, _manifest(db, [p1], window_end=_dt(23)))
    assert res.status == "BLOCKED" and "OUTSIDE_WINDOW" in res.reason


# \u2500\u2500 numeric artifact evaluation \u2500\u2500
def _numeric_sample(db, artifact_type, actual, origin=T0, **akw):
    base = dict(artifact_type=artifact_type, calibration_domain="PRICE", label_type="RETURN_1D",
                probability_type="", event_definition_id="",
                generated_at=origin - timedelta(minutes=30))
    base.update(akw)
    a = _artifact("", **base)
    pred = _prediction([_lineage()], [a], forecast_origin=origin,
                       feature_cutoff_timestamp=origin - timedelta(hours=1))
    arts = [replace(a, prediction_id=pred.prediction_id)]
    db.append_prediction_bundle(pred, [_lineage()], arts)
    db.append_outcome(PA.make_outcome(
        prediction_id=pred.prediction_id, label_type="RETURN_1D", outcome_kind="RETURN",
        target_period="1d", actual_value=actual, event_timestamp=_dt(25), available_at=_dt(25),
        forecast_artifact_id=arts[0].forecast_artifact_id))
    return pred


def _numeric_manifest(db, preds, artifact_type):
    return CE.build_evaluation_dataset(
        db, prediction_ids=[p.prediction_id for p in preds], target_family="OSAKA_MICRO",
        instrument="JNU", horizon="1d", artifact_type=artifact_type,
        partition_role="CALIBRATION", window_start=_dt(20), window_end=_dt(30))


def test_point_mae_rmse(db):
    p1 = _numeric_sample(db, "POINT", 102.0, value=100.0, origin=_dt(24))
    p2 = _numeric_sample(db, "POINT", 98.0, value=100.0, origin=_dt(23))
    res = CE.evaluate_manifest(db, _numeric_manifest(db, [p1, p2], "POINT"))
    assert res.status == "EVALUATED"
    assert res.point.mae == pytest.approx(2.0) and res.point.rmse == pytest.approx(2.0)
    assert res.probability is None


def test_quantile_pinball_loss(db):
    p1 = _numeric_sample(db, "QUANTILE", 102.0, value=100.0, quantile_level=0.5, origin=_dt(24))
    p2 = _numeric_sample(db, "QUANTILE", 98.0, value=100.0, quantile_level=0.5, origin=_dt(23))
    res = CE.evaluate_manifest(db, _numeric_manifest(db, [p1, p2], "QUANTILE"))
    assert res.status == "EVALUATED"
    assert res.quantile.quantile_level == pytest.approx(0.5)
    assert res.quantile.pinball_loss == pytest.approx(1.0)
    assert CE.pinball_loss(0.5, 100.0, 102.0) == pytest.approx(1.0)
    assert CE.pinball_loss(0.5, 100.0, 98.0) == pytest.approx(1.0)
    assert res.probability is None


def test_mixed_quantile_levels_blocked(db):
    p1 = _numeric_sample(db, "QUANTILE", 102.0, value=100.0, quantile_level=0.5, origin=_dt(24))
    p2 = _numeric_sample(db, "QUANTILE", 98.0, value=100.0, quantile_level=0.9, origin=_dt(23))
    res = CE.evaluate_manifest(db, _numeric_manifest(db, [p1, p2], "QUANTILE"))
    assert res.status == "BLOCKED" and res.reason == "MIXED_OR_MISSING_QUANTILE_LEVEL"


def test_interval_coverage_and_width(db):
    p1 = _numeric_sample(db, "INTERVAL", 100.0, lower_value=99.0, upper_value=101.0,
                         nominal_coverage=0.9, origin=_dt(24))
    p2 = _numeric_sample(db, "INTERVAL", 105.0, lower_value=99.0, upper_value=101.0,
                         nominal_coverage=0.9, origin=_dt(23))
    res = CE.evaluate_manifest(db, _numeric_manifest(db, [p1, p2], "INTERVAL"))
    assert res.status == "EVALUATED"
    assert res.interval.nominal_coverage == pytest.approx(0.9)
    assert res.interval.empirical_coverage == pytest.approx(0.5)
    assert res.interval.mean_width == pytest.approx(2.0)
    assert res.interval.coverage_error == pytest.approx(-0.4)


# \u2500\u2500 manifest determinism / content addressing \u2500\u2500
def test_manifest_is_deterministic_under_input_order(db):
    p1, _, _ = _sample(db, value=0.1, actual=1.0)
    p2, _, _ = _sample(db, value=0.9, actual=0.0)
    m_a = _manifest(db, [p1, p2])
    m_b = _manifest(db, [p2, p1])
    assert m_a.dataset_id == m_b.dataset_id
    assert m_a.members == m_b.members


def test_manifest_id_changes_when_member_set_changes(db):
    p1, _, _ = _sample(db, value=0.1, actual=1.0)
    p2, _, _ = _sample(db, value=0.9, actual=0.0)
    m1 = _manifest(db, [p1, p2])
    m2 = _manifest(db, [p1])
    assert m1.dataset_id != m2.dataset_id
    assert m1.dataset_id.startswith("v2i_ds_") and len(m1.dataset_id) == len("v2i_ds_") + 16


def test_manifest_records_member_ids_and_partition(db):
    p1, a1, o1 = _sample(db, value=0.2, actual=1.0)
    man = _manifest(db, [p1], partition_role="FINAL_OOS")
    assert man.partition_role == "FINAL_OOS"
    assert man.members[0].prediction_id == p1.prediction_id
    assert man.members[0].forecast_artifact_id == a1.forecast_artifact_id
    assert man.members[0].outcome_id == o1.outcome_id
    assert man.label_types == ["TOUCH_UP_1D"]
    assert man.schema_version == "2I.1"
    assert man.window_start == _dt(20) and man.window_end == _dt(30)


def test_unknown_partition_role_rejected(db):
    with pytest.raises(CE.CalibrationEvaluationError):
        _manifest(db, [], partition_role="WHATEVER")


def test_manifest_window_must_be_aware(db):
    with pytest.raises(CE.CalibrationEvaluationError):
        CE.build_evaluation_dataset(
            db, prediction_ids=[], target_family="OSAKA_MICRO", instrument="JNU", horizon="1d",
            window_start=datetime(2026, 9, 20), window_end=_dt(30))


# \u2500\u2500 adapter never emits CALIBRATED \u2500\u2500
def test_adapter_never_emits_calibrated(db):
    p1, _, _ = _sample(db, value=0.1, actual=1.0, origin=_dt(24))
    p2, _, _ = _sample(db, value=0.1, actual=0.0, origin=_dt(23))
    res = CE.evaluate_manifest(db, _manifest(db, [p1, p2]))
    assert res.status == "EVALUATED"
    ev = CE.evaluation_result_to_calibration_evidence(res)
    assert ev["evidence_status"] == "EVALUATED_UNCALIBRATED"
    assert ev["calibration_status"] == "UNCALIBRATED"
    assert ev["fitted_model"] is False and ev["pre_registered_threshold"] is False
    assert ev["evidence_status"] in CE.EVIDENCE_STATUSES
    assert ev["schema_version"] == "2I.1"


def test_adapter_insufficient_evidence_for_non_evaluated(db):
    p1, _, _ = _sample(db, value=0.1, actual=1.0)
    cases = [
        _manifest(db, [p1]),
        _manifest(db, [p1], window_end=_dt(23)),
        CE.build_evaluation_dataset(
            db, prediction_ids=[], target_family="OSAKA_MICRO", instrument="JNU", horizon="1d",
            artifact_type="EVENT_PROBABILITY", partition_role="VALIDATION",
            window_start=_dt(20), window_end=_dt(30)),
    ]
    for man in cases:
        ev = CE.evaluation_result_to_calibration_evidence(CE.evaluate_manifest(db, man))
        assert ev["evidence_status"] == "INSUFFICIENT_EVIDENCE"
        assert ev["calibration_status"] == "UNCALIBRATED"


def test_adapter_output_status_is_always_uncertain():
    for status in CE.EVALUATION_STATUSES:
        res = CE.EvaluationResult(status=status, artifact_type="EVENT_PROBABILITY",
                                  dataset_id="v2i_ds_x", partition_role="CALIBRATION")
        ev = CE.evaluation_result_to_calibration_evidence(res)
        assert ev["evidence_status"] in ("INSUFFICIENT_EVIDENCE", "EVALUATED_UNCALIBRATED")


def test_evaluation_status_unknown_value_rejected():
    with pytest.raises(CE.CalibrationEvaluationError):
        CE.EvaluationResult(status="GOOD", artifact_type="EVENT_PROBABILITY",
                            dataset_id="x", partition_role="CALIBRATION")


# \u2500\u2500 actual readiness (default DB must not be created) \u2500\u2500
def test_actual_readiness_reports_none_yet_without_creating_db(tmp_path, monkeypatch):
    target = tmp_path / "audit" / "prediction_audit.duckdb"
    monkeypatch.setattr(CE, "default_audit_db_path", lambda: target)
    r = CE.evaluate_default_db()
    assert r["db_present"] is False
    assert r["ACTUAL_PROBABILITY_EVALUATION"] == "INSUFFICIENT_EVIDENCE"
    assert r["ACTUAL_CALIBRATION_EVIDENCE"] == "NONE_YET"
    assert not target.exists()


def test_actual_readiness_on_empty_db(db):
    r = CE.actual_evaluation_readiness(db)
    assert r["db_present"] is True and r["settled_event_probability_samples"] == 0
    assert r["ACTUAL_CALIBRATION_EVIDENCE"] == "NONE_YET"


def test_actual_readiness_counts_real_settled_samples(db):
    _sample(db, value=0.1, actual=1.0)
    _sample(db, value=0.9, actual=0.0)
    r = CE.actual_evaluation_readiness(db)
    assert r["settled_event_probability_samples"] == 2
    assert r["ACTUAL_PROBABILITY_EVALUATION"] == "READY_FOR_EVALUATION"
    assert r["ACTUAL_CALIBRATION_EVIDENCE"] == "NONE_YET"
