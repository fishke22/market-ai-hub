"""Phase V2-H 2H.1 — prediction audit DB tests (temporary DuckDB; never the production DB)."""
from __future__ import annotations

import re
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
    base = dict(
        economic_factor_id="JP_EQUITY", representation_id=rep, instrument_type="FUTURE",
        representation_relation="DIRECT", temporal_role="UNAVAILABLE", resolved_role="NOT_AVAILABLE",
        venue_id="OSE_DERIVATIVES", calendar_id="OSE_DERIVATIVES", session_status="NIGHT_SESSION",
        trading_date="2026-09-25", availability_status="NOT_AVAILABLE", timestamp_precision="UNKNOWN",
        provider="jpx", source_type="settlement", source_frequency="DAILY", data_grade="OFFICIAL_DAILY",
    )
    base.update(kw)
    return PA.make_lineage(**base)


def _prediction(lineage=None, **kw):
    base = dict(
        target_family="OSAKA_MICRO", instrument="JNU", instrument_role="DIRECT",
        calendar_id="OSE_DERIVATIVES", frequency="DAILY", horizon="1d",
        forecast_origin=_dt(24, 9, 0), feature_cutoff_timestamp=_dt(24, 8, 0),
        build_id="test-build", model="m", model_version="v1",
        v2_schema_versions=PA.v2_schema_versions(),
    )
    base.update(kw)
    return PA.make_prediction(list(lineage or []), **base)


def _outcome(prediction_id, **kw):
    base = dict(prediction_id=prediction_id, label_type="RETURN_1D", outcome_kind="RETURN",
                target_period="2026-09-25", actual_value=0.012,
                event_timestamp=_dt(25, 6, 0), available_at=_dt(25, 6, 0),
                label_schema_version="2C.2")
    base.update(kw)
    return PA.make_outcome(**base)


# ── schema / storage ──
def test_schema_version_2h3():
    assert PA.V2_PREDICTION_AUDIT_SCHEMA_VERSION == "2H.3"


def test_default_db_path_is_local_audit_dir():
    from market_ai_hub.config.runtime_paths import data_root

    p = PA.default_audit_db_path()
    assert p == data_root() / "audit" / "prediction_audit.duckdb"


def test_v2_schema_versions_assembled_from_modules():
    v = PA.v2_schema_versions()
    assert v["asof"] == "2A.2" and v["session_truth"] == "2A.2" and v["factor_routing"] == "2A.2"
    assert v["state_machine"] == "2D.4" and v["sequential_update"] == "2G.2"
    assert v["prediction_audit"] == "2H.3"
    assert v["evaluation_governance"] == "W3.1"


# ── temporal order ──
def test_temporal_order_enforced(db):
    bad = _prediction(forecast_origin=_dt(24, 7, 0), feature_cutoff_timestamp=_dt(24, 8, 0))
    with pytest.raises(PA.TemporalOrderError):
        db.append_prediction(bad)


def test_temporal_order_equal_allowed(db):
    ok = _prediction(forecast_origin=_dt(24, 8, 0), feature_cutoff_timestamp=_dt(24, 8, 0))
    assert db.append_prediction(ok) == PA.APPEND_INSERTED


# ── outcome must not enter prediction ──
def test_outcome_cannot_enter_prediction_payload(db):
    bad = _prediction(v2_schema_versions={"outcome": "1.2%"})
    with pytest.raises(PA.OutcomeInPredictionError) as e:
        db.append_prediction(bad)
    assert e.value.code == PA.BLOCKED_OUTCOME_IN_PREDICTION


def test_outcome_keys_blocked_case_insensitive(db):
    for key in ("OUTCOME", "Future_Return", "actual_state"):
        with pytest.raises(PA.OutcomeInPredictionError):
            db.append_prediction(_prediction(v2_schema_versions={key: "x"}))


def test_legit_schema_version_keys_not_blocked(db):
    # 'labels' / 'daily_labels' are legit schema-version keys, not outcome leakage
    assert db.append_prediction(_prediction(v2_schema_versions=PA.v2_schema_versions())) == PA.APPEND_INSERTED


# ── factor lineage leakage / unavailable truth ──
def test_future_factor_after_cutoff_blocked(db):
    lin = _lineage("NQ_FUTURES", availability_status="AVAILABLE",
                   event_timestamp=_dt(24, 9, 0), available_at=_dt(24, 9, 0))
    with pytest.raises(PA.FutureFactorError):
        db.append_prediction(_prediction([lin]), [lin])


def test_factor_available_before_cutoff_allowed(db):
    lin = _lineage("NQ_FUTURES", availability_status="AVAILABLE",
                   event_timestamp=_dt(24, 1, 0), available_at=_dt(24, 1, 0))
    assert db.append_prediction(_prediction([lin]), [lin]) == PA.APPEND_INSERTED


def test_not_available_factor_remains_persisted(db):
    lin = _lineage()  # NOT_AVAILABLE, no timestamps
    pred = _prediction([lin])
    db.append_prediction(pred, [lin])
    stored = db.get_lineage(pred.prediction_id)
    assert len(stored) == 1
    assert stored[0].availability_status == "NOT_AVAILABLE"
    assert stored[0].resolved_role == "NOT_AVAILABLE"


def test_external_entitlement_blocked_is_valid_audit_truth(db):
    lin = _lineage("NQ_FUTURES", availability_status="EXTERNAL_ENTITLEMENT_BLOCKED",
                   data_grade="", provider="yuanta")
    pred = _prediction([lin])
    db.append_prediction(pred, [lin])
    assert db.get_lineage(pred.prediction_id)[0].availability_status == "EXTERNAL_ENTITLEMENT_BLOCKED"


def test_unknown_lineage_availability_rejected():
    with pytest.raises(PA.PredictionAuditError):
        _lineage(availability_status="BANANA")


def test_duplicate_representation_in_lineage_blocked(db):
    a, b = _lineage(), _lineage()
    with pytest.raises(PA.PredictionAuditError):
        db.append_prediction(_prediction(), [a, b])


def test_lineage_digest_mismatch_blocked(db):
    lin = _lineage()
    pred = _prediction([lin])
    tampered = replace(pred, factor_lineage_digest="v2h_lindig_deadbeef")
    with pytest.raises(PA.PredictionAuditError):
        # id no longer matches payload either -> must fail closed
        db.append_prediction(tampered, [lin])


# ── append-only semantics ──
def test_duplicate_exact_insert_idempotent(db):
    pred = _prediction([_lineage()])
    assert db.append_prediction(pred, [_lineage()]) == PA.APPEND_INSERTED
    assert db.append_prediction(pred, [_lineage()]) == PA.APPEND_IDEMPOTENT
    assert len(db.list_prediction_ids()) == 1


def test_same_id_different_payload_blocked(db):
    pred = _prediction()
    db.append_prediction(pred)
    different = replace(pred, model="other")
    with pytest.raises(PA.IdCollisionError) as e:
        db.append_prediction(different)
    assert e.value.code == PA.BLOCKED_ID_COLLISION


def test_forged_prediction_id_rejected(db):
    pred = _prediction()
    forged = replace(pred, prediction_id="v2h_pred_ffffffffffffffff")
    with pytest.raises(PA.IdCollisionError):
        db.append_prediction(forged)


def test_supersede_creates_new_record_and_preserves_original(db):
    original = _prediction()
    db.append_prediction(original)
    corrected = _prediction(model="m2", supersedes_id=original.prediction_id)
    db.append_prediction(corrected)
    assert corrected.prediction_id != original.prediction_id
    assert db.get_prediction(original.prediction_id).supersedes_id == ""
    assert db.get_prediction(corrected.prediction_id).supersedes_id == original.prediction_id
    assert db.verify_prediction(original.prediction_id)


def test_outcome_id_collision_blocked(db):
    pred = _prediction()
    db.append_prediction(pred)
    out = _outcome(pred.prediction_id)
    assert db.append_outcome(out) == PA.APPEND_INSERTED
    assert db.append_outcome(out) == PA.APPEND_IDEMPOTENT
    tampered = replace(out, actual_value=0.5)
    with pytest.raises(PA.IdCollisionError):
        db.append_outcome(tampered)


def test_outcome_requires_known_prediction(db):
    with pytest.raises(PA.UnknownPredictionError):
        db.append_outcome(_outcome("v2h_pred_0000000000000000"))


# ── separation of prediction / outcome ──
def test_outcome_append_does_not_mutate_prediction(db):
    pred = _prediction([_lineage()])
    db.append_prediction(pred, [_lineage()])
    before = db.get_prediction(pred.prediction_id)
    before_lineage = db.get_lineage(pred.prediction_id)
    db.append_outcome(_outcome(pred.prediction_id))
    assert db.get_prediction(pred.prediction_id) == before
    assert db.get_lineage(pred.prediction_id) == before_lineage
    assert len(db.get_outcomes(pred.prediction_id)) == 1


def test_prediction_and_outcome_hash_namespaces_are_separate():
    payload = {"a": 1}
    assert PA.prediction_identity(payload).startswith("v2h_pred_")
    assert PA.outcome_identity(payload).startswith("v2h_out_")
    assert PA.lineage_identity(payload).startswith("v2h_lin_")
    assert PA.prediction_identity(payload) != PA.outcome_identity(payload)


def test_later_provider_refresh_cannot_mutate_old_lineage(db):
    old = _lineage()  # NOT_AVAILABLE at prediction time
    p1 = _prediction([old])
    db.append_prediction(p1, [old])
    # later the provider refresh yields a fresh observation -> NEW record, never a mutation
    fresh = _lineage(availability_status="AVAILABLE", staleness_status="FRESH",
                     event_timestamp=_dt(24, 1, 0), available_at=_dt(24, 1, 0))
    p2 = _prediction([fresh])
    db.append_prediction(p2, [fresh])
    assert p1.prediction_id != p2.prediction_id
    assert db.get_lineage(p1.prediction_id)[0].availability_status == "NOT_AVAILABLE"
    assert db.get_lineage(p2.prediction_id)[0].availability_status == "AVAILABLE"


# ── integrity ──
def test_record_identity_recomputes_from_db(db):
    pred = _prediction([_lineage()])
    db.append_prediction(pred, [_lineage()])
    db.append_outcome(_outcome(pred.prediction_id))
    assert db.verify_prediction(pred.prediction_id) is True
    assert db.verify_prediction("v2h_pred_0000000000000000") is False


def test_reads_are_deterministically_ordered(db):
    pred = _prediction()
    db.append_prediction(pred)
    for i, v in enumerate((0.01, 0.02, 0.03)):
        db.append_outcome(_outcome(pred.prediction_id, actual_value=v,
                                   event_timestamp=_dt(25, 6, i), available_at=_dt(25, 6, i)))
    first = [o.outcome_id for o in db.get_outcomes(pred.prediction_id)]
    second = [o.outcome_id for o in db.get_outcomes(pred.prediction_id)]
    assert first == second          # deterministic across reads
    assert len(first) == 3


# ── API surface / immutability ──
def test_public_api_has_no_update_delete_sql():
    from market_ai_hub.research.v2 import prediction_audit as mod

    src = open(mod.__file__, encoding="utf-8").read()
    assert not re.search(r"\b(UPDATE|DELETE)\s+(predictions|factor_lineage|outcomes)\b", src, re.I)
    assert not hasattr(PA.PredictionAuditDB, "update")
    assert not hasattr(PA.PredictionAuditDB, "delete")


def test_records_are_frozen():
    rec = _prediction()
    with pytest.raises(Exception):
        rec.status = "VOID"  # frozen dataclass
    with pytest.raises(Exception):
        _lineage().representation_id = "X"


def test_naive_datetime_rejected():
    with pytest.raises(PA.PredictionAuditError):
        _prediction(forecast_origin=datetime(2026, 9, 24, 9, 0))


# ── V2-A.2 integration ──
def test_lineage_from_v2a2_observation(db):
    from market_ai_hub.research.v2 import factor_representation as FR

    asof = _dt(24, 8, 0)
    obs = FR.observe_factor("JP_EQUITY", "OSE_MICRO_FUTURES", asof=asof, value=None,
                            event_timestamp=None, availability_status="NOT_AVAILABLE")
    lin = PA.lineage_from_observation(obs)
    assert lin.representation_id == "OSE_MICRO_FUTURES"
    assert lin.venue_id == "OSE_DERIVATIVES"
    assert lin.session_status  # session truth carried through
    pred = _prediction([lin])
    assert db.append_prediction(pred, [lin]) == PA.APPEND_INSERTED
    assert db.get_lineage(pred.prediction_id)[0].lineage_id == lin.lineage_id


def test_lineage_from_live_observation_carries_timestamps(db):
    from market_ai_hub.research.v2 import factor_representation as FR

    asof = _dt(24, 8, 0)
    obs = FR.observe_factor(
        "US_TECH_RISK", "NQ_FUTURES", asof=asof, value=25000.0,
        event_timestamp=_dt(24, 7, 59), available_at=_dt(24, 7, 59),
        received_at=_dt(24, 7, 59), timestamp_precision="INTRADAY_TIMESTAMP",
        provider="broker", source_frequency="1M", data_grade="BROKER_REALTIME",
        contract_code="NQZ6", series_semantics="CONTRACT", roll_status="NONE")
    lin = PA.lineage_from_observation(obs)
    assert lin.available_at == _dt(24, 7, 59)
    assert lin.contract_code == "NQZ6"
    pred = _prediction([lin])
    assert db.append_prediction(pred, [lin]) == PA.APPEND_INSERTED
