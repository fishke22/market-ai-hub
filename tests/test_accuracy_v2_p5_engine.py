"""Accuracy v2 P5 immutable forward ledger and downgrade regression."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from market_ai_hub.research.accuracy_v2_p5_engine import (
    LABEL_TYPE,
    MODEL_NAME,
    MODEL_VERSION,
    STATUS_ABSTAIN,
    STATUS_ALREADY_PRECOMMITTED,
    STATUS_ALREADY_SETTLED,
    STATUS_BEFORE_START,
    STATUS_BLOCKED,
    STATUS_MISSED,
    STATUS_PRECOMMITTED,
    STATUS_SETTLED,
    STATUS_WAITING,
    p5_forward_evidence_summary,
    precommit_p5_forward,
    preview_p5_origin,
    settle_p5_pending,
    run_p5_cycle,
)
from market_ai_hub.research.v2 import prediction_audit as PA
from market_ai_hub.integrations.yuanta.resolver import ose_last_trading_date
from market_ai_hub.research.accuracy_v2_p1 import jpx_report_publication_for_session

UTC = timezone.utc
ORIGIN = datetime(2026, 9, 28, 0, 6, tzinfo=UTC)


@pytest.fixture()
def db(tmp_path):
    return PA.PredictionAuditDB(tmp_path / "p5.duckdb")


def _series():
    idx = pd.date_range("2026-08-01", periods=56, freq="D", tz="UTC")
    values = np.linspace(59000.0, 60000.0, len(idx))
    return pd.Series(values, index=idx, name="settlement")


def _meta():
    return {
        "status": "OK",
        "contract_month": "202610",
        "quote_code": "JNU2610",
        "sample_count": 56,
        "first_date": "2026-08-01",
        "latest_date": "2026-09-25",
        "latest_settlement": 60000.0,
        "source": "fixture",
        "series_semantics": "EXACT_CONTRACT",
        "price_semantics": "SETTLEMENT",
    }


def _receipts(
    *,
    reference_date="2026-09-25",
    reference_value=60000.0,
    reference_received=datetime(2026, 9, 28, 0, 4, tzinfo=UTC),
    target=False,
    target_value=60300.0,
    target_received=datetime(2026, 9, 29, 0, 1, tzinfo=UTC),
):
    rows = [{
        "contract_month": "202610",
        "date": reference_date,
        "settlement": reference_value,
        "_received_at": reference_received,
        "source_hash": "refhash",
        "source_url": "https://example.invalid/ref",
        "_source_path": "fixture-ref",
    }]
    if target:
        rows.append({
            "contract_month": "202610",
            "date": "2026-09-28",
            "settlement": target_value,
            "_received_at": target_received,
            "source_hash": "targethash",
            "source_url": "https://example.invalid/target",
            "_source_path": "fixture-target",
        })
    return pd.DataFrame(rows)


def _robust(*, crossing=False):
    q10, q50, q90 = (59500.0, 60100.0, 60500.0)
    if crossing:
        q10, q50, q90 = (60500.0, 60100.0, 59500.0)
    return {
        "status": "OK",
        "point_reference": {"price": 60000.0},
        "empirical_interval": {
            "status": "DEVELOPMENT_FIT_UNVALIDATED_FORWARD",
            "nominal_coverage": 0.90,
            "lower_price": 57000.0,
            "upper_price": 63000.0,
        },
        "lightgbm_quantile_challenger": {
            "status": "CHALLENGER_UNVALIDATED",
            "price_quantiles": {"q10": q10, "q50": q50, "q90": q90},
        },
    }


def test_before_first_forward_boundary_never_writes(db):
    receipts = _receipts(
        reference_date="2026-09-24",
        reference_received=datetime(2026, 9, 25, 0, 4, tzinfo=UTC),
    )
    now = datetime(2026, 9, 25, 0, 6, tzinfo=UTC)
    preview = preview_p5_origin(now=now, receipts=receipts, contract_month="202610")
    assert preview["status"] == STATUS_BEFORE_START
    out = precommit_p5_forward(
        now=now, db=db, current_series=_series(), current_meta=_meta(),
        receipts=receipts, robust_analysis=_robust(),
    )
    assert out.status == STATUS_BEFORE_START
    assert db.list_prediction_ids() == []


def test_canonical_origin_freezes_point_interval_and_three_quantiles(db):
    out = precommit_p5_forward(
        now=ORIGIN, db=db, current_series=_series(), current_meta=_meta(),
        receipts=_receipts(), robust_analysis=_robust(),
    )
    assert out.status == STATUS_PRECOMMITTED
    assert out.canonical is True
    assert out.target_session_date == "2026-09-28"
    assert out.exact_contract == "JNU2610"
    assert out.artifact_count == 5
    pred = db.get_prediction(out.prediction_id)
    assert pred is not None
    assert pred.model == MODEL_NAME
    assert pred.model_version == MODEL_VERSION
    assert pred.sample_origin == "FORWARD_PRECOMMITTED"
    assert pred.forecast_origin == ORIGIN
    assert pred.feature_cutoff_timestamp == datetime(2026, 9, 28, 0, 4, tzinfo=UTC)
    assert pred.label_window_id == "2026-09-28"
    assert pred.label_window_end == datetime(2026, 9, 29, 0, 0, 1, tzinfo=UTC)
    lineage = db.get_lineage(out.prediction_id)
    assert len(lineage) == 1
    assert lineage[0].contract_code == "JNU2610"
    assert lineage[0].source_snapshot_ids == ["jpx-settlement:refhash"]
    arts = db.get_forecast_artifacts(out.prediction_id)
    assert sorted(a.artifact_type for a in arts) == ["INTERVAL", "POINT", "QUANTILE", "QUANTILE", "QUANTILE"]
    assert all(a.generated_at == ORIGIN for a in arts)
    assert db.get_outcomes(out.prediction_id) == []
    assert db.verify_prediction(out.prediction_id)

    again = precommit_p5_forward(
        now=ORIGIN + timedelta(minutes=2), db=db,
        current_series=_series(), current_meta=_meta(),
        receipts=_receipts(), robust_analysis=_robust(),
    )
    assert again.status == STATUS_ALREADY_PRECOMMITTED
    assert again.prediction_id == out.prediction_id
    assert len(db.list_prediction_ids()) == 1


def test_late_origin_and_stale_reference_never_write(db):
    late = precommit_p5_forward(
        now=datetime(2026, 9, 28, 0, 25, tzinfo=UTC),
        db=db, current_series=_series(), current_meta=_meta(),
        receipts=_receipts(), robust_analysis=_robust(),
    )
    assert late.status == STATUS_MISSED
    assert db.list_prediction_ids() == []

    stale_receipts = _receipts(
        reference_received=datetime(2026, 9, 27, 23, 20, tzinfo=UTC),
    )
    stale = precommit_p5_forward(
        now=ORIGIN, db=db, current_series=_series(), current_meta=_meta(),
        receipts=stale_receipts, robust_analysis=_robust(),
    )
    assert stale.status == STATUS_ABSTAIN
    assert stale.reason == "STALE_REFERENCE"
    assert db.list_prediction_ids() == []


def test_crossing_quantiles_are_omitted_but_baseline_and_interval_survive(db):
    out = precommit_p5_forward(
        now=ORIGIN, db=db, current_series=_series(), current_meta=_meta(),
        receipts=_receipts(), robust_analysis=_robust(crossing=True),
    )
    assert out.status == STATUS_PRECOMMITTED
    arts = db.get_forecast_artifacts(out.prediction_id)
    assert sorted(a.artifact_type for a in arts) == ["INTERVAL", "POINT"]


def test_settlement_waits_for_official_label_maturity_then_binds_every_artifact(db):
    pred = precommit_p5_forward(
        now=ORIGIN, db=db, current_series=_series(), current_meta=_meta(),
        receipts=_receipts(), robust_analysis=_robust(),
    )
    before = settle_p5_pending(
        now=datetime(2026, 9, 28, 23, 59, tzinfo=UTC),
        db=db, receipts=_receipts(target=False),
    )
    assert len(before) == 1
    assert before[0].status == STATUS_WAITING
    assert db.get_outcomes(pred.prediction_id) == []

    after = settle_p5_pending(
        now=datetime(2026, 9, 29, 0, 2, tzinfo=UTC),
        db=db, receipts=_receipts(target=True),
    )
    assert after[0].status == STATUS_SETTLED
    arts = db.get_forecast_artifacts(pred.prediction_id)
    outs = db.get_outcomes(pred.prediction_id)
    assert len(outs) == len(arts) == 5
    assert {o.forecast_artifact_id for o in outs} == {a.forecast_artifact_id for a in arts}
    assert {o.actual_value for o in outs} == {60300.0}
    assert {o.label_type for o in outs} == {LABEL_TYPE}
    assert {o.source_snapshot_ids[0] for o in outs} == {"jpx-settlement:targethash"}

    again = settle_p5_pending(
        now=datetime(2026, 9, 29, 0, 3, tzinfo=UTC),
        db=db, receipts=_receipts(target=True),
    )
    assert again[0].status == STATUS_ALREADY_SETTLED
    assert len(db.get_outcomes(pred.prediction_id)) == 5


def test_target_revision_conflict_preserves_first_outcome(db):
    pred = precommit_p5_forward(
        now=ORIGIN, db=db, current_series=_series(), current_meta=_meta(),
        receipts=_receipts(), robust_analysis=_robust(),
    )
    settle_p5_pending(
        now=datetime(2026, 9, 29, 0, 2, tzinfo=UTC),
        db=db, receipts=_receipts(target=True),
    )
    original_ids = [o.outcome_id for o in db.get_outcomes(pred.prediction_id)]
    revised = _receipts(target=True)
    revised = pd.concat([
        revised,
        pd.DataFrame([{
            "contract_month": "202610",
            "date": "2026-09-28",
            "settlement": 61000.0,
            "_received_at": datetime(2026, 9, 29, 0, 3, tzinfo=UTC),
            "source_hash": "revisionhash",
            "source_url": "https://example.invalid/revision",
            "_source_path": "fixture-revision",
        }]),
    ], ignore_index=True)
    result = settle_p5_pending(
        now=datetime(2026, 9, 29, 0, 4, tzinfo=UTC),
        db=db, receipts=revised,
    )
    assert result[0].status == STATUS_BLOCKED
    assert result[0].reason == "OUTCOME_REVISION_CONFLICT"
    assert [o.outcome_id for o in db.get_outcomes(pred.prediction_id)] == original_ids


def test_roll_boundary_selects_next_exact_contract():
    expiry = ose_last_trading_date(2026, 10)
    ref_date = expiry.isoformat()
    receipt = jpx_report_publication_for_session(ref_date).astimezone(UTC) + timedelta(minutes=1)
    receipts = pd.DataFrame([
        {
            "contract_month": "202610", "date": ref_date, "settlement": 60000.0,
            "_received_at": receipt, "source_hash": "oct", "source_url": "", "_source_path": "",
        },
        {
            "contract_month": "202612", "date": ref_date, "settlement": 60100.0,
            "_received_at": receipt, "source_hash": "dec", "source_url": "", "_source_path": "",
        },
    ])
    now = jpx_report_publication_for_session(ref_date).astimezone(UTC) + timedelta(minutes=6)
    out = preview_p5_origin(now=now, receipts=receipts)
    assert out["contract_month"] == "202612"
    assert out["exact_contract"] == "JNU2612"


def test_missing_forward_origins_trigger_pipeline_downgrade(db):
    summary = p5_forward_evidence_summary(
        now=datetime(2026, 10, 8, 1, 0, tzinfo=UTC),
        db=db,
    )
    assert summary["expected_canonical_origins"] >= 5
    assert summary["canonical_prediction_count"] == 0
    assert summary["canonical_origin_coverage"] == 0.0
    assert "DATA_PIPELINE_DEGRADED" in summary["downgrade_reasons"]
    assert summary["downgrade_state"] == "BASELINE_ONLY_DEGRADED"


def test_cycle_attempt_limit_skips_third_collection(monkeypatch, tmp_path, db):
    import market_ai_hub.research.accuracy_v2_p5_engine as engine

    monkeypatch.setattr(engine, "data_root", lambda: tmp_path)
    calls = {"collect": 0}

    def fake_collect():
        calls["collect"] += 1
        return {
            "status": "OK", "broker_used": False, "credentials_used": False,
            "recorder_touched": False, "order_action": False,
        }

    monkeypatch.setattr(engine, "collect_public_sources", fake_collect)
    monkeypatch.setattr(engine, "settle_p5_pending", lambda **kwargs: [])
    monkeypatch.setattr(
        engine, "precommit_p5_forward",
        lambda **kwargs: engine.P5CycleResult(status=engine.STATUS_WAITING),
    )
    monkeypatch.setattr(
        engine, "p5_forward_evidence_summary",
        lambda **kwargs: {
            "PREDICTIVE_GAIN": False, "CALIBRATED": False, "TRADING_EDGE": False,
        },
    )
    now = datetime(2026, 9, 28, 0, 5, tzinfo=UTC)
    one = run_p5_cycle(now=now, db=db)
    two = run_p5_cycle(now=now + timedelta(minutes=1), db=db)
    three = run_p5_cycle(now=now + timedelta(minutes=2), db=db)
    assert one["attempt_count"] == 1
    assert two["attempt_count"] == 2
    assert three["status"] == "ATTEMPT_LIMIT"
    assert three["collection"]["status"] == "SKIPPED_ATTEMPT_LIMIT"
    assert calls["collect"] == 2


def test_forward_summary_counts_only_p5_and_never_promotes(db):
    pred = precommit_p5_forward(
        now=ORIGIN, db=db, current_series=_series(), current_meta=_meta(),
        receipts=_receipts(), robust_analysis=_robust(),
    )
    settle_p5_pending(
        now=datetime(2026, 9, 29, 0, 2, tzinfo=UTC),
        db=db, receipts=_receipts(target=True),
    )
    # Unrelated historical record cannot enter P5 scope.
    unrelated = PA.make_prediction(
        target_family="OSAKA_MICRO",
        instrument="JNU",
        calendar_id="OSE_DERIVATIVES",
        horizon="1d",
        sample_origin="RETROSPECTIVE_REPLAY",
        forecast_origin=ORIGIN,
        feature_cutoff_timestamp=ORIGIN,
        build_id="fixture",
        model="other",
        model_version="other",
    )
    db.append_prediction(unrelated)

    summary = p5_forward_evidence_summary(
        now=datetime(2026, 9, 29, 0, 6, tzinfo=UTC),
        db=db,
    )
    assert summary["canonical_prediction_count"] == 1
    assert summary["settled_canonical_origin_count"] == 1
    assert summary["interval"]["sample_count"] == 1
    assert summary["quantile"]["sample_count"] == 1
    assert summary["evidence_state"] == "COLLECTING_FORWARD_EVIDENCE"
    assert summary["PREDICTIVE_GAIN"] is False
    assert summary["CALIBRATED"] is False
    assert summary["TRADING_EDGE"] is False
    assert summary["automatic_model_promotion"] is False
    assert summary["strong_direction_allowed"] is False
