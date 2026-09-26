"""W3.2 precommitted forward prediction / settlement cycle regression."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pandas as pd
import pytest

from market_ai_hub.research.v2 import forward_cycle as FC
from market_ai_hub.research.v2 import prediction_audit as PA
from market_ai_hub.feature_store.store import FeatureRecord, FeatureStore

UTC = timezone.utc


def _dt(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 9, day, hour, minute, tzinfo=UTC)


@pytest.fixture()
def db(tmp_path):
    return PA.PredictionAuditDB(tmp_path / "audit.duckdb")


def _input(**kw) -> FC.OsakaForwardInput:
    base = dict(
        trading_date="2026-09-24",
        close=42000.0,
        session_close_timestamp=_dt(24, 6, 45),  # 15:45 JST
        available_at=_dt(24, 6, 50),
        source_snapshot_ids=["src-input-20260924"],
        provider="fixture",
        source_type="DAILY_BAR_CLOSE",
        data_grade="VERIFIED_TEST_FIXTURE",
        quality_status="VERIFIED",
        availability_status="AVAILABLE",
        point_in_time_safe=True,
        contract_code="JNU2612",
        contract_month="202612",
        roll_status="NONE",
        series_semantics="CONTRACT",
        source_frequency="DAILY",
    )
    base.update(kw)
    return FC.OsakaForwardInput(**base)


def _outcome(**kw) -> FC.OsakaForwardOutcome:
    base = dict(
        trading_date="2026-09-25",
        close=42100.0,
        session_close_timestamp=_dt(25, 6, 45),  # 15:45 JST
        available_at=_dt(25, 6, 50),
        source_snapshot_ids=["src-outcome-20260925"],
        provider="fixture",
        source_type="DAILY_BAR_CLOSE",
        data_grade="VERIFIED_TEST_FIXTURE",
        quality_status="VERIFIED",
        availability_status="AVAILABLE",
        point_in_time_safe=True,
        contract_code="JNU2612",
        contract_month="202612",
        roll_status="NONE",
        series_semantics="CONTRACT",
    )
    base.update(kw)
    return FC.OsakaForwardOutcome(**base)


def _set_clock(monkeypatch, value: datetime) -> None:
    monkeypatch.setattr(FC, "_now_utc", lambda: value)


def _forward_store(tmp_path, *, source_frequency="DAILY",
                   feature_name=FC.FORWARD_DAILY_FEATURE_NAME,
                   feature_version=FC.FORWARD_DAILY_FEATURE_VERSION,
                   trading_date="2026-09-24", day=24, value=42000.0):
    store = FeatureStore(root=tmp_path)
    store.init()
    event = _dt(day, 6, 45)
    available = _dt(day, 6, 50)
    lineage_id = f"lin-forward-daily-{trading_date.replace('-', '')}"
    source_ids = [f"fs-daily-src-{trading_date.replace('-', '')}"]
    store.put(FeatureRecord(
        feature_name=feature_name,
        symbol="JNU2612",
        event_time=event,
        available_at=available,
        feature_version=feature_version,
        source="fixture:DAILY_BAR_CLOSE",
        data_grade="VERIFIED_TEST_FIXTURE",
        value=value,
        lineage_id=lineage_id,
        economic_factor_id="JP_EQUITY",
        representation_id="OSE_MICRO_FUTURES",
        venue_id="OSE_DERIVATIVES",
        session_status="CLOSED",
        trading_date=trading_date,
        timestamp_precision="BAR_CLOSE_TIMESTAMP",
        availability_status="AVAILABLE",
        quality_status="VERIFIED",
        resolved_role="PREVIOUS_SESSION_REFERENCE",
        point_in_time_safe=True,
        contract_code="JNU2612",
        contract_month="202612",
        roll_status="NONE",
        series_semantics="CONTRACT",
        source_snapshot_ids=source_ids,
    ))
    with store._conn() as con:
        con.execute(
            """
            INSERT INTO factor_observations (
                lineage_id, economic_factor_id, representation_id,
                instrument_type, representation_relation, temporal_role, resolved_role,
                venue_id, calendar_id, session_status, trading_date, value,
                event_timestamp, available_at, timestamp_precision, staleness_status,
                availability_status, quality_status, provider, source_type,
                source_frequency, data_grade, point_in_time_safe, contract_code,
                contract_month, roll_status, series_semantics, source_snapshot_ids_json,
                model_feature_gate_at_ingest, payload_json
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            [
                lineage_id, "JP_EQUITY", "OSE_MICRO_FUTURES",
                "FUTURE", "DIRECT", "PREVIOUS_SESSION_REFERENCE", "PREVIOUS_SESSION_REFERENCE",
                "OSE_DERIVATIVES", "OSE_DERIVATIVES", "CLOSED", trading_date, value,
                event.replace(tzinfo=None), available.replace(tzinfo=None),
                "BAR_CLOSE_TIMESTAMP", "FRESH_AT_FORECAST_ORIGIN",
                "AVAILABLE", "VERIFIED", "fixture", "DAILY_BAR_CLOSE",
                source_frequency, "VERIFIED_TEST_FIXTURE", True, "JNU2612",
                "202612", "NONE", "CONTRACT", f'["{source_ids[0]}"]',
                "ELIGIBLE", "{}",
            ],
        )
    return store


def test_schema_version_is_audit_bound():
    assert FC.W3_FORWARD_CYCLE_SCHEMA_VERSION == "W3.2"
    assert PA.v2_schema_versions()["forward_cycle"] == "W3.2"


def test_ose_full_session_window_is_next_exchange_session():
    target, start, end = FC.ose_next_full_session_window("2026-09-24")
    assert target == "2026-09-25"
    assert start == _dt(24, 8, 0)   # 17:00 JST
    assert end == _dt(25, 6, 45)   # 15:45 JST


def test_input_requires_point_in_time_provenance(monkeypatch, db):
    _set_clock(monkeypatch, _dt(24, 7, 0))
    res = FC.precommit_osaka_last_price(_input(point_in_time_safe=False), db=db)
    assert res.status == FC.STATUS_INPUT_NOT_ELIGIBLE
    assert "POINT_IN_TIME_UNSAFE" in res.reason
    assert db.list_prediction_ids() == []


def test_input_requires_contract_and_source_snapshots(monkeypatch, db):
    _set_clock(monkeypatch, _dt(24, 7, 0))
    res = FC.precommit_osaka_last_price(
        _input(contract_code="", contract_month="", source_snapshot_ids=[]),
        db=db,
    )
    assert res.status == FC.STATUS_INPUT_NOT_ELIGIBLE
    assert "CONTRACT_CODE_REQUIRED" in res.reason
    assert "CONTRACT_MONTH_REQUIRED" in res.reason
    assert "SOURCE_SNAPSHOT_IDS_REQUIRED" in res.reason


def test_cannot_precommit_before_input_close(monkeypatch, db):
    _set_clock(monkeypatch, _dt(24, 6, 40))
    res = FC.precommit_osaka_last_price(_input(), db=db)
    assert res.status == FC.STATUS_INPUT_NOT_ELIGIBLE
    assert "SOURCE_SESSION_NOT_CLOSED" in res.reason


def test_cannot_precommit_after_target_night_session_started(monkeypatch, db):
    _set_clock(monkeypatch, _dt(24, 8, 1))
    res = FC.precommit_osaka_last_price(_input(), db=db)
    assert res.status == FC.STATUS_INPUT_NOT_ELIGIBLE
    assert "PRECOMMIT_WINDOW_CLOSED" in res.reason


def test_future_available_input_cannot_be_backfilled(monkeypatch, db):
    _set_clock(monkeypatch, _dt(24, 7, 0))
    res = FC.precommit_osaka_last_price(_input(available_at=_dt(24, 7, 5)), db=db)
    assert res.status == FC.STATUS_INPUT_NOT_ELIGIBLE
    assert "AVAILABLE_AFTER_FORECAST_ORIGIN" in res.reason


def test_precommit_writes_2h3_prediction_artifact_and_lineage(monkeypatch, db):
    _set_clock(monkeypatch, _dt(24, 7, 0))
    res = FC.precommit_osaka_last_price(_input(), db=db)
    assert res.status == FC.STATUS_PRECOMMITTED
    pred = db.get_prediction(res.prediction_id)
    assert pred is not None
    assert pred.sample_origin == "FORWARD_PRECOMMITTED"
    assert pred.label_window_id == "2026-09-25"
    assert pred.label_window_start == _dt(24, 8, 0)
    assert pred.label_window_end == _dt(25, 6, 45)
    assert pred.forecast_origin == _dt(24, 7, 0)
    assert pred.feature_cutoff_timestamp == _dt(24, 6, 50)
    assert pred.model == FC.MODEL_NAME
    assert pred.model_version == FC.MODEL_VERSION
    assert pred.v2_schema_versions["forward_cycle"] == "W3.2"
    assert db.get_outcomes(pred.prediction_id) == []

    lineage = db.get_lineage(pred.prediction_id)
    assert len(lineage) == 1
    assert lineage[0].contract_code == "JNU2612"
    assert lineage[0].contract_month == "202612"
    assert lineage[0].series_semantics == "CONTRACT"
    assert lineage[0].roll_status == "NONE"
    assert lineage[0].source_snapshot_ids == ["src-input-20260924"]

    artifacts = db.get_forecast_artifacts(pred.prediction_id)
    assert len(artifacts) == 1
    assert artifacts[0].artifact_type == "POINT"
    assert artifacts[0].label_type == FC.LABEL_TYPE
    assert artifacts[0].value == pytest.approx(42000.0)
    assert artifacts[0].calibration_status_at_origin == "NOT_APPLICABLE"
    assert db.verify_prediction(pred.prediction_id)


def test_same_scope_window_is_operationally_idempotent(monkeypatch, db):
    _set_clock(monkeypatch, _dt(24, 7, 0))
    one = FC.precommit_osaka_last_price(_input(), db=db)
    _set_clock(monkeypatch, _dt(24, 7, 5))
    two = FC.precommit_osaka_last_price(_input(), db=db)
    assert one.status == FC.STATUS_PRECOMMITTED
    assert two.status == FC.STATUS_ALREADY_PRECOMMITTED
    assert two.prediction_id == one.prediction_id
    assert len(db.list_prediction_ids()) == 1


def test_settlement_before_horizon_end_is_refused(monkeypatch, db):
    _set_clock(monkeypatch, _dt(24, 7, 0))
    pred = FC.precommit_osaka_last_price(_input(), db=db)
    _set_clock(monkeypatch, _dt(25, 6, 30))
    res = FC.settle_osaka_terminal_close(
        pred.prediction_id,
        _outcome(available_at=_dt(25, 6, 30)),
        db=db,
    )
    assert res.status == FC.STATUS_NOT_MATURE
    assert "HORIZON_NOT_MATURE" in res.reason
    assert db.get_outcomes(pred.prediction_id) == []


def test_settlement_rejects_cross_contract_outcome(monkeypatch, db):
    _set_clock(monkeypatch, _dt(24, 7, 0))
    pred = FC.precommit_osaka_last_price(_input(), db=db)
    _set_clock(monkeypatch, _dt(25, 7, 0))
    res = FC.settle_osaka_terminal_close(
        pred.prediction_id,
        _outcome(contract_code="JNU2703", contract_month="202703"),
        db=db,
    )
    assert res.status == FC.STATUS_OUTCOME_NOT_ELIGIBLE
    assert "OUTCOME_CONTRACT_MISMATCH" in res.reason
    assert db.get_outcomes(pred.prediction_id) == []


def test_settlement_requires_target_date_and_source_ids(monkeypatch, db):
    _set_clock(monkeypatch, _dt(24, 7, 0))
    pred = FC.precommit_osaka_last_price(_input(), db=db)
    _set_clock(monkeypatch, _dt(25, 7, 0))
    res = FC.settle_osaka_terminal_close(
        pred.prediction_id,
        _outcome(trading_date="2026-09-28", source_snapshot_ids=[]),
        db=db,
    )
    assert res.status == FC.STATUS_OUTCOME_NOT_ELIGIBLE
    assert "TARGET_TRADING_DATE_MISMATCH" in res.reason
    assert "SOURCE_SNAPSHOT_IDS_REQUIRED" in res.reason


def test_valid_settlement_is_append_only_and_idempotent(monkeypatch, db):
    _set_clock(monkeypatch, _dt(24, 7, 0))
    pred = FC.precommit_osaka_last_price(_input(), db=db)
    _set_clock(monkeypatch, _dt(25, 7, 0))
    one = FC.settle_osaka_terminal_close(pred.prediction_id, _outcome(), db=db)
    two = FC.settle_osaka_terminal_close(pred.prediction_id, _outcome(), db=db)
    assert one.status == FC.STATUS_SETTLED
    assert two.status == FC.STATUS_ALREADY_SETTLED
    assert one.outcome_id == two.outcome_id
    outs = db.get_outcomes(pred.prediction_id)
    assert len(outs) == 1
    assert outs[0].outcome_kind == "TERMINAL"
    assert outs[0].target_period == "2026-09-25"
    assert outs[0].label_schema_version == "W3.2"
    assert outs[0].source_snapshot_ids == ["src-outcome-20260925"]


def test_settled_forward_sample_flows_through_w31_governance(monkeypatch, db):
    _set_clock(monkeypatch, _dt(24, 7, 0))
    pred = FC.precommit_osaka_last_price(_input(), db=db)
    _set_clock(monkeypatch, _dt(25, 7, 0))
    FC.settle_osaka_terminal_close(pred.prediction_id, _outcome(close=42100.0), db=db)

    man, result, readiness = FC.build_forward_evaluation(
        db=db,
        evaluation_as_of=_dt(25, 8, 0),
        window_start=_dt(24, 0, 0),
        window_end=_dt(26, 0, 0),
    )
    assert len(man.members) == 1
    assert result.status == "EVALUATED"
    assert result.sample_count == 1
    assert result.point.sample_count == 1
    assert result.point.mae == pytest.approx(100.0)
    assert readiness["state"] == "READY_FOR_EVALUATION"
    assert readiness["CALIBRATED"] is False
    assert readiness["CALIBRATION_FITTING"] == "NOT_STARTED"
    assert readiness["PREDICTIVE_EVIDENCE"] == "NOT_ESTABLISHED"
    assert readiness["TRADING_EDGE"] == "NOT_ESTABLISHED"


def test_evaluation_as_of_before_outcome_excludes_later_knowledge(monkeypatch, db):
    _set_clock(monkeypatch, _dt(24, 7, 0))
    pred = FC.precommit_osaka_last_price(_input(), db=db)
    _set_clock(monkeypatch, _dt(25, 7, 0))
    FC.settle_osaka_terminal_close(
        pred.prediction_id,
        _outcome(available_at=_dt(25, 6, 55)),
        db=db,
    )
    man, result, readiness = FC.build_forward_evaluation(
        db=db,
        evaluation_as_of=_dt(25, 6, 50),
        window_start=_dt(24, 0, 0),
        window_end=_dt(26, 0, 0),
    )
    assert man.members == []
    assert {r.reason for r in man.rejected} == {"OUTCOME_NOT_AVAILABLE_AT_EVALUATION_AS_OF"}
    assert readiness["state"] == "INSUFFICIENT_EVIDENCE"
    assert result.status == "NOT_EVALUATABLE"


def test_feature_store_adapter_missing_store_is_read_only(tmp_path):
    store = FeatureStore(root=tmp_path)
    snapshot, status = FC.osaka_forward_input_from_feature_store(
        as_of=_dt(24, 7, 0), contract_code="JNU2612", store=store,
    )
    assert snapshot is None
    assert status["status"] == "NO_FEATURE_STORE"
    assert status["forward_input_status"] == "NOT_READY"
    assert status["values_exposed"] is False
    assert not store.db_path.exists()


def test_feature_store_tick_cannot_impersonate_daily(tmp_path):
    store = _forward_store(tmp_path, source_frequency="TICK")
    snapshot, status = FC.osaka_forward_input_from_feature_store(
        as_of=_dt(24, 7, 0), contract_code="JNU2612", store=store,
    )
    assert snapshot is None
    assert status["status"] == "INCOMPATIBLE_FREQUENCY"
    assert status["source_frequency"] == "TICK"
    assert status["values_exposed"] is False


def test_feature_store_daily_candidate_preserves_exact_provenance(tmp_path):
    store = _forward_store(tmp_path)
    snapshot, status = FC.osaka_forward_input_from_feature_store(
        as_of=_dt(24, 7, 0), contract_code="JNU2612", store=store,
    )
    assert snapshot is not None
    assert status["status"] == "READY"
    assert status["forward_input_status"] == "CANDIDATE"
    assert snapshot.trading_date == "2026-09-24"
    assert snapshot.session_close_timestamp == _dt(24, 6, 45)
    assert snapshot.available_at == _dt(24, 6, 50)
    assert snapshot.contract_code == "JNU2612"
    assert snapshot.contract_month == "202612"
    assert snapshot.roll_status == "NONE"
    assert snapshot.series_semantics == "CONTRACT"
    assert snapshot.source_snapshot_ids == ["fs-daily-src-20260924"]


def test_feature_store_daily_candidate_can_precommit(monkeypatch, tmp_path, db):
    store = _forward_store(tmp_path)
    snapshot, _ = FC.osaka_forward_input_from_feature_store(
        as_of=_dt(24, 7, 0), contract_code="JNU2612", store=store,
    )
    assert snapshot is not None
    _set_clock(monkeypatch, _dt(24, 7, 0))
    result = FC.precommit_osaka_last_price(snapshot, db=db)
    assert result.status == FC.STATUS_PRECOMMITTED
    assert db.get_prediction(result.prediction_id).label_window_id == "2026-09-25"


def test_operator_precommit_missing_daily_feature_does_not_write(monkeypatch, tmp_path, db):
    store = FeatureStore(root=tmp_path)
    _set_clock(monkeypatch, _dt(24, 7, 0))
    result = FC.precommit_osaka_from_feature_store(
        contract_code="JNU2612", db=db, store=store,
    )
    assert result.status == FC.STATUS_INPUT_NOT_ELIGIBLE
    assert db.list_prediction_ids() == []
    assert not store.db_path.exists()


def test_operator_precommit_from_feature_store(monkeypatch, tmp_path, db):
    store = _forward_store(tmp_path)
    _set_clock(monkeypatch, _dt(24, 7, 0))
    result = FC.precommit_osaka_from_feature_store(
        contract_code="JNU2612", db=db, store=store,
    )
    assert result.status == FC.STATUS_PRECOMMITTED
    pred = db.get_prediction(result.prediction_id)
    assert pred is not None and pred.label_window_id == "2026-09-25"


def test_outcome_adapter_waits_for_exact_target_session(monkeypatch, tmp_path, db):
    store = _forward_store(tmp_path)
    _set_clock(monkeypatch, _dt(24, 7, 0))
    pred = FC.precommit_osaka_from_feature_store(
        contract_code="JNU2612", db=db, store=store,
    )
    outcome, status = FC.osaka_forward_outcome_from_feature_store(
        pred.prediction_id,
        as_of=_dt(25, 7, 0),
        db=db,
        store=store,
    )
    assert outcome is None
    assert status["status"] == "TARGET_OUTCOME_NOT_AVAILABLE"
    assert status["forward_outcome_status"] == "NOT_READY"


def test_operator_settlement_reads_exact_target_daily_feature(monkeypatch, tmp_path, db):
    store = _forward_store(tmp_path)
    _set_clock(monkeypatch, _dt(24, 7, 0))
    pred = FC.precommit_osaka_from_feature_store(
        contract_code="JNU2612", db=db, store=store,
    )
    _forward_store(
        tmp_path,
        trading_date="2026-09-25",
        day=25,
        value=42100.0,
    )
    _set_clock(monkeypatch, _dt(25, 7, 0))
    result = FC.settle_osaka_from_feature_store(
        pred.prediction_id,
        db=db,
        store=store,
    )
    assert result.status == FC.STATUS_SETTLED
    outcomes = db.get_outcomes(pred.prediction_id)
    assert len(outcomes) == 1
    assert outcomes[0].actual_value == pytest.approx(42100.0)


def test_legacy_continuous_daily_parquet_is_never_forward_evidence(tmp_path):
    p = tmp_path / "legacy.parquet"
    pd.DataFrame({
        "trading_date": [pd.Timestamp("2026-09-01")],
        "open": [42000.0],
        "high": [42100.0],
        "low": [41900.0],
        "close": [42050.0],
        "volume": [10],
    }).to_parquet(p, index=False)
    status = FC.legacy_osaka_daily_source_readiness(p)
    assert status["status"] == "BLOCKED_FORWARD_INPUT"
    assert status["forward_eligible"] is False
    assert status["values_exposed"] is False
    for blocker in (
        "AVAILABLE_AT_MISSING",
        "SOURCE_SNAPSHOT_IDS_MISSING",
        "CONTRACT_CODE_MISSING",
        "CONTRACT_MONTH_MISSING",
        "ROLL_PROVENANCE_MISSING",
    ):
        assert blocker in status["reason"]


def test_raw_event_probability_first_sample_is_uninformative_prior(monkeypatch, db):
    _set_clock(monkeypatch, _dt(24, 7, 0))
    res = FC.precommit_osaka_event_probability(_input(), db=db)
    assert res.status == FC.STATUS_PRECOMMITTED
    pred = db.get_prediction(res.prediction_id)
    assert pred is not None
    assert pred.model == FC.EVENT_MODEL_NAME
    assert pred.model_version == FC.EVENT_MODEL_VERSION
    assert pred.sample_origin == "FORWARD_PRECOMMITTED"
    arts = db.get_forecast_artifacts(pred.prediction_id)
    assert len(arts) == 1
    art = arts[0]
    assert art.artifact_type == "EVENT_PROBABILITY"
    assert art.calibration_domain == "PRICE_DISTRIBUTION"
    assert art.probability_type == "TERMINAL"
    assert art.event_definition_id == FC.EVENT_DEFINITION_ID
    assert art.event_threshold_value == pytest.approx(42000.0)
    assert art.value == pytest.approx(0.5)
    assert art.raw_score == pytest.approx(0.0)
    assert art.calibration_status_at_origin == "UNCALIBRATED"
    assert PA.is_public_probability(art) is False


def test_event_probability_settlement_uses_frozen_threshold(monkeypatch, db):
    _set_clock(monkeypatch, _dt(24, 7, 0))
    pred = FC.precommit_osaka_event_probability(_input(), db=db)
    _set_clock(monkeypatch, _dt(25, 7, 0))
    res = FC.settle_osaka_event_probability(
        pred.prediction_id, _outcome(close=42100.0), db=db
    )
    assert res.status == FC.STATUS_SETTLED
    outs = db.get_outcomes(pred.prediction_id)
    assert len(outs) == 1
    assert outs[0].outcome_kind == "TERMINAL"
    assert outs[0].label_type == FC.EVENT_LABEL_TYPE
    assert outs[0].actual_value == pytest.approx(1.0)
    assert outs[0].label_schema_version == FC.EVENT_PROBABILITY_SCHEMA_VERSION


def test_event_probability_second_precommit_updates_only_from_available_history(monkeypatch, db):
    _set_clock(monkeypatch, _dt(24, 7, 0))
    first = FC.precommit_osaka_event_probability(_input(), db=db)
    _set_clock(monkeypatch, _dt(25, 7, 10))
    settled = FC.settle_osaka_event_probability(
        first.prediction_id,
        _outcome(close=42100.0, available_at=_dt(25, 7, 5)),
        db=db,
    )
    assert settled.status == FC.STATUS_SETTLED

    # At 07:00 the outcome exists in storage but was not yet available, so it is excluded.
    p_early, succ_early, fail_early = FC.raw_event_probability(db, _dt(25, 7, 0), contract_code="JNU2612", contract_month="202612")
    assert (succ_early, fail_early) == (0, 0)
    assert p_early == pytest.approx(0.5)

    # Once available, the same causal history updates Beta(1,1) to Beta(2,1).
    p_late, succ_late, fail_late = FC.raw_event_probability(db, _dt(25, 7, 6), contract_code="JNU2612", contract_month="202612")
    assert (succ_late, fail_late) == (1, 0)
    assert p_late == pytest.approx(2.0 / 3.0)

    second_input = _input(
        trading_date="2026-09-25",
        close=42100.0,
        session_close_timestamp=_dt(25, 6, 45),
        available_at=_dt(25, 6, 50),
        source_snapshot_ids=["src-input-20260925"],
    )
    _set_clock(monkeypatch, _dt(25, 7, 6))
    second = FC.precommit_osaka_event_probability(second_input, db=db)
    assert second.status == FC.STATUS_PRECOMMITTED
    art = db.get_forecast_artifacts(second.prediction_id)[0]
    assert art.value == pytest.approx(2.0 / 3.0)
    assert art.raw_score == pytest.approx(1.0)
    assert art.event_threshold_value == pytest.approx(42100.0)


def test_event_probability_equal_close_is_false_not_ambiguous(monkeypatch, db):
    _set_clock(monkeypatch, _dt(24, 7, 0))
    pred = FC.precommit_osaka_event_probability(_input(), db=db)
    _set_clock(monkeypatch, _dt(25, 7, 0))
    FC.settle_osaka_event_probability(
        pred.prediction_id, _outcome(close=42000.0), db=db
    )
    assert db.get_outcomes(pred.prediction_id)[0].actual_value == pytest.approx(0.0)


def test_event_probability_feature_store_wrappers_accumulate_without_cli_prices(monkeypatch, tmp_path, db):
    store = _forward_store(tmp_path)
    _set_clock(monkeypatch, _dt(24, 7, 0))
    pre = FC.precommit_osaka_event_probability_from_feature_store(
        contract_code="JNU2612", db=db, store=store,
    )
    assert pre.status == FC.STATUS_PRECOMMITTED
    art = db.get_forecast_artifacts(pre.prediction_id)[0]
    assert art.value == pytest.approx(0.5)
    assert art.event_threshold_value == pytest.approx(42000.0)

    # Add the next exact-contract DAILY close; settlement wrapper must use store truth only.
    _forward_store(
        tmp_path, trading_date="2026-09-25", day=25, value=42100.0,
    )
    _set_clock(monkeypatch, _dt(25, 7, 0))
    settled = FC.settle_osaka_event_probability_from_feature_store(
        pre.prediction_id, db=db, store=store,
    )
    assert settled.status == FC.STATUS_SETTLED
    out = db.get_outcomes(pre.prediction_id)[0]
    assert out.actual_value == pytest.approx(1.0)


def test_event_probability_prior_and_idempotency_do_not_cross_contracts(monkeypatch, db):
    _set_clock(monkeypatch, _dt(24, 7, 0))
    first = FC.precommit_osaka_event_probability(_input(), db=db)
    assert first.status == FC.STATUS_PRECOMMITTED

    _set_clock(monkeypatch, _dt(25, 7, 0))
    settled = FC.settle_osaka_event_probability(
        first.prediction_id, _outcome(close=42100.0), db=db,
    )
    assert settled.status == FC.STATUS_SETTLED

    same_contract = FC.raw_event_probability(
        db, _dt(25, 7, 1), contract_code="JNU2612", contract_month="202612",
    )
    other_contract = FC.raw_event_probability(
        db, _dt(25, 7, 1), contract_code="JNU2703", contract_month="202703",
    )
    assert same_contract == pytest.approx((2.0 / 3.0, 1, 0))
    assert other_contract == pytest.approx((0.5, 0, 0))

    # A different exact contract may have its own prediction for the same target window.
    _set_clock(monkeypatch, _dt(24, 7, 5))
    other = FC.precommit_osaka_event_probability(
        _input(
            contract_code="JNU2703",
            contract_month="202703",
            source_snapshot_ids=["src-input-other-contract"],
        ),
        db=db,
    )
    assert other.status == FC.STATUS_PRECOMMITTED
    assert other.prediction_id != first.prediction_id
    art = db.get_forecast_artifacts(other.prediction_id)[0]
    assert art.value == pytest.approx(0.5)
    lineage = db.get_lineage(other.prediction_id)
    assert lineage[0].contract_code == "JNU2703"
    assert lineage[0].contract_month == "202703"
