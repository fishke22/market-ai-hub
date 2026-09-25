"""C2 terminal-close materializer: offline fail-closed correctness."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

import pytest

from market_ai_hub.feature_store.model_input import build_model_input
from market_ai_hub.feature_store.store import FeatureStore
from market_ai_hub.integrations.yuanta.spark_runtime import (
    TickDetailCallbackTrace,
    TickDetailRequestTrace,
)
from market_ai_hub.research.v2 import terminal_close_materializer as TCM
from market_ai_hub.research.v2 import tick_detail_source as TD
from market_ai_hub.research.v2 import tick_detail_verification as TV

UTC = timezone.utc


def _dt(day: int, hour: int, minute: int = 0, second: int = 0) -> datetime:
    return datetime(2026, 9, day, hour, minute, second, tzinfo=UTC)


def _row(hour: int, minute: int, second: int, price: float, seq: int,
         volume: int = 1) -> TD.TickDetailRow:
    return TD.TickDetailRow(
        raw_timestamp=datetime(2026, 9, 24, hour, minute, second),
        deal_price=price,
        deal_volume=volume,
        buy_price=price - 5,
        sell_price=price + 5,
        seq_no=seq,
        in_out_flag=0,
    )


def _batch(*, rows=None, received_at: datetime | None = None) -> TD.TickDetailBatch:
    raw = TD.TickDetailBatch(
        market_no=TD.OSE_MARKET_NO,
        stock_code="JNU2612",
        rows=list(rows or [
            _row(15, 44, 40, 41995.0, 100),
            _row(15, 44, 58, 42000.0, 101),
        ]),
        received_at=received_at or _dt(24, 6, 46),
    )
    return replace(raw, source_snapshot_id=TD.canonical_tick_detail_snapshot_id(raw))


def _evidence(
    batch: TD.TickDetailBatch,
    *,
    request_time: datetime | None = None,
) -> TV.TickDetailRuntimeVerificationEvidence:
    return TV.build_ose_runtime_verification_evidence(
        batch,
        runtime_request_id="tick_detail_test_1",
        runtime_build_id="TEST_BUILD_C2",
        request_time=request_time or _dt(24, 6, 45, 30),
        callback_received_at=batch.received_at,
        requested_market_no=TD.OSE_MARKET_NO,
        requested_stock_code=batch.stock_code,
        last_count=20,
        request_accepted=True,
        callback_index=TV.CALLBACK_INDEX,
        callback_mark=1,
        returned_market_no=batch.market_no,
        returned_stock_code=batch.stock_code,
        timestamp_basis_status=TD.TIMESTAMP_BASIS_RUNTIME_VERIFIED,
        timestamp_basis_method=TV.TIMESTAMP_BASIS_METHOD_OSE_LOCAL_CLOCK,
        timestamp_crosscheck_passed=True,
    )


def _rehash(evidence: TV.TickDetailRuntimeVerificationEvidence, **changes):
    changed = replace(evidence, **changes, evidence_id="")
    return replace(changed, evidence_id=TV.canonical_evidence_id(changed))


def _materialize(batch, tmp_path, *, evidence=None, month="202612"):
    return TCM.materialize_ose_terminal_close(
        batch,
        contract_month=month,
        verification_evidence=evidence,
        store=FeatureStore(root=tmp_path),
    )


def test_raw_batch_cannot_self_assert_runtime_verified_status():
    with pytest.raises(ValueError, match="must remain timestamp-basis UNVERIFIED"):
        TD.TickDetailBatch(
            market_no=TD.OSE_MARKET_NO,
            stock_code="JNU2612",
            rows=[_row(15, 44, 58, 42000.0, 101)],
            received_at=_dt(24, 6, 46),
            timestamp_basis_status=TD.TIMESTAMP_BASIS_RUNTIME_VERIFIED,
        )


def test_missing_runtime_evidence_cannot_materialize(tmp_path):
    batch = _batch()
    result = _materialize(batch, tmp_path)
    assert result.status == TCM.STATUS_BLOCKED
    assert "RUNTIME_VERIFICATION_EVIDENCE_REQUIRED" in result.reason
    assert not FeatureStore(root=tmp_path).db_path.exists()


def test_terminal_close_keeps_trade_time_separate_from_session_boundary(tmp_path):
    batch = _batch()
    evidence = _evidence(batch)
    store = FeatureStore(root=tmp_path)
    result = TCM.materialize_ose_terminal_close(
        batch,
        contract_month="202612",
        verification_evidence=evidence,
        store=store,
    )
    assert result.status == TCM.STATUS_MATERIALIZED
    assert result.source_trade_timestamp == _dt(24, 6, 44, 58)
    assert result.session_close_timestamp == _dt(24, 6, 45)
    assert result.available_at == _dt(24, 6, 46)
    assert result.source_snapshot_ids == (batch.source_snapshot_id, evidence.evidence_id)

    bundle = build_model_input(
        "OSE_MICRO_FUTURES",
        as_of=_dt(24, 7, 0),
        contract_code="JNU2612",
        requested_frequency="DAILY",
        min_points=1,
        feature_name="terminal_close",
        feature_version="w3.2-contract-daily-close-1",
        store=store,
    )
    assert bundle.status == "READY"
    assert bundle.source_frequency == "DAILY"
    assert bundle.last_event_timestamp == _dt(24, 6, 45)

    rows = store.latest_observations(
        as_of=_dt(24, 7, 0),
        representation_ids=["OSE_MICRO_FUTURES"],
        limit=5,
    )
    assert len(rows) == 1
    assert rows[0]["event_timestamp"] == _dt(24, 6, 45).isoformat()
    assert rows[0]["provider_timestamp"] == _dt(24, 6, 44, 58).isoformat()


def test_request_time_not_callback_time_controls_window(tmp_path):
    batch = _batch()  # callback is 15:46 JST, but request below is 15:44:59 JST.
    valid = _evidence(batch)
    early = _rehash(valid, request_time=_dt(24, 6, 44, 59))
    result = _materialize(batch, tmp_path, evidence=early)
    assert result.status == TCM.STATUS_BLOCKED
    assert "REQUEST_OUTSIDE_CONTROLLED_WINDOW" in result.reason


def test_callback_after_night_open_blocks_even_if_request_was_in_window(tmp_path):
    batch = _batch(received_at=_dt(24, 8, 0, 1))  # 17:00:01 JST
    base = TV.TickDetailRuntimeVerificationEvidence(
        runtime_request_id="tick_detail_test_1",
        runtime_build_id="TEST_BUILD_C2",
        request_time=_dt(24, 7, 59, 59),
        callback_received_at=batch.received_at,
        requested_market_no=TD.OSE_MARKET_NO,
        requested_stock_code=batch.stock_code,
        last_count=20,
        request_accepted=True,
        callback_index=TV.CALLBACK_INDEX,
        callback_mark=1,
        returned_market_no=batch.market_no,
        returned_stock_code=batch.stock_code,
        source_snapshot_id=batch.source_snapshot_id,
        timestamp_basis_status=TD.TIMESTAMP_BASIS_RUNTIME_VERIFIED,
        timestamp_basis_method=TV.TIMESTAMP_BASIS_METHOD_OSE_LOCAL_CLOCK,
        timestamp_crosscheck_passed=True,
    )
    evidence = replace(base, evidence_id=TV.canonical_evidence_id(base))
    result = _materialize(batch, tmp_path, evidence=evidence)
    assert result.status == TCM.STATUS_BLOCKED
    assert "CALLBACK_OUTSIDE_CONTROLLED_WINDOW" in result.reason


def test_runtime_evidence_source_snapshot_mismatch_blocks(tmp_path):
    batch = _batch()
    evidence = _rehash(_evidence(batch), source_snapshot_id="w33_tick_other")
    result = _materialize(batch, tmp_path, evidence=evidence)
    assert result.status == TCM.STATUS_BLOCKED
    assert "RUNTIME_EVIDENCE_SOURCE_SNAPSHOT_MISMATCH" in result.reason


def test_runtime_evidence_request_code_mismatch_blocks(tmp_path):
    batch = _batch()
    evidence = _rehash(_evidence(batch), requested_stock_code="JNU2703")
    result = _materialize(batch, tmp_path, evidence=evidence)
    assert result.status == TCM.STATUS_BLOCKED
    assert "REQUEST_BATCH_CODE_MISMATCH" in result.reason


def test_runtime_evidence_id_tamper_blocks(tmp_path):
    batch = _batch()
    evidence = replace(_evidence(batch), evidence_id="w33_verify_tampered")
    result = _materialize(batch, tmp_path, evidence=evidence)
    assert result.status == TCM.STATUS_BLOCKED
    assert "RUNTIME_EVIDENCE_ID_INVALID" in result.reason


def test_noncanonical_raw_snapshot_id_blocks(tmp_path):
    batch = replace(_batch(), source_snapshot_id="caller_supplied")
    evidence = _rehash(_evidence(_batch()), source_snapshot_id="caller_supplied")
    result = _materialize(batch, tmp_path, evidence=evidence)
    assert result.status == TCM.STATUS_BLOCKED
    assert "SOURCE_SNAPSHOT_ID_CANONICAL_MISMATCH" in result.reason


def test_evidence_creation_does_not_mutate_raw_snapshot_identity():
    batch = _batch()
    before = batch.source_snapshot_id
    evidence = _evidence(batch)
    assert batch.timestamp_basis_status == TD.TIMESTAMP_BASIS_UNVERIFIED
    assert batch.source_snapshot_id == before
    assert TD.canonical_tick_detail_snapshot_id(batch) == before
    assert evidence.source_snapshot_id == before


def test_trade_after_day_close_blocks_fail_closed(tmp_path):
    batch = _batch(rows=[
        _row(15, 44, 58, 42000.0, 101),
        _row(15, 45, 1, 42005.0, 102),
    ])
    forged = _rehash(_evidence(_batch()), source_snapshot_id=batch.source_snapshot_id)
    result = _materialize(batch, tmp_path, evidence=forged)
    assert result.status == TCM.STATUS_BLOCKED
    assert "TIMESTAMP_BASIS_CROSSCHECK_FAILED" in result.reason


def test_contract_month_must_match_requested_jnu_code(tmp_path):
    batch = _batch()
    result = _materialize(batch, tmp_path, evidence=_evidence(batch), month="202703")
    assert result.status == TCM.STATUS_BLOCKED
    assert "CONTRACT_MONTH_CODE_MISMATCH" in result.reason


def test_zero_volume_row_cannot_be_selected_as_terminal_trade(tmp_path):
    batch = _batch(rows=[
        _row(15, 44, 58, 42000.0, 101),
        _row(15, 44, 59, 99999.0, 102, volume=0),
    ])
    result = _materialize(batch, tmp_path, evidence=_evidence(batch))
    assert result.status == TCM.STATUS_MATERIALIZED
    assert result.source_trade_timestamp == _dt(24, 6, 44, 58)


def test_repeat_is_idempotent_but_conflicting_close_is_rejected(tmp_path):
    store = FeatureStore(root=tmp_path)
    batch = _batch()
    evidence = _evidence(batch)
    one = TCM.materialize_ose_terminal_close(
        batch, contract_month="202612", verification_evidence=evidence, store=store,
    )
    two = TCM.materialize_ose_terminal_close(
        batch, contract_month="202612", verification_evidence=evidence, store=store,
    )
    assert one.status == TCM.STATUS_MATERIALIZED
    assert two.status == TCM.STATUS_ALREADY_MATERIALIZED

    changed = _batch(rows=[
        _row(15, 44, 40, 41995.0, 100),
        _row(15, 44, 59, 42010.0, 102),
    ])
    conflict = TCM.materialize_ose_terminal_close(
        changed,
        contract_month="202612",
        verification_evidence=_evidence(changed),
        store=store,
    )
    assert conflict.status == TCM.STATUS_BLOCKED
    assert "CONFLICTING_TERMINAL_CLOSE" in conflict.reason


def test_runtime_exchange_builder_binds_matching_request_callback():
    batch = _batch()
    request = TickDetailRequestTrace(
        request_id="tick_detail_7",
        request_time_utc=_dt(24, 6, 45, 30),
        market_no=TD.OSE_MARKET_NO,
        stock_code=batch.stock_code,
        last_count=20,
        accepted=True,
    )
    callback = TickDetailCallbackTrace(
        request_id="tick_detail_7",
        callback_received_at_utc=batch.received_at,
        callback_mark=1,
        callback_index=TV.CALLBACK_INDEX,
        returned_market_no=batch.market_no,
        returned_stock_code=batch.stock_code,
    )
    evidence = TV.build_ose_runtime_verification_from_exchange(
        batch,
        request_trace=request,
        callback_trace=callback,
        runtime_build_id="TEST_BUILD_C2",
    )
    assert evidence.runtime_request_id == "tick_detail_7"
    assert evidence.source_snapshot_id == batch.source_snapshot_id
    assert evidence.evidence_id == TV.canonical_evidence_id(evidence)


def test_runtime_exchange_builder_recomputes_timestamp_basis():
    batch = _batch(rows=[_row(10, 0, 0, 42000.0, 101)])
    request = TickDetailRequestTrace(
        request_id="tick_detail_8",
        request_time_utc=_dt(24, 6, 45, 30),
        market_no=TD.OSE_MARKET_NO,
        stock_code=batch.stock_code,
        last_count=20,
        accepted=True,
    )
    callback = TickDetailCallbackTrace(
        request_id="tick_detail_8",
        callback_received_at_utc=batch.received_at,
        callback_mark=1,
        callback_index=TV.CALLBACK_INDEX,
        returned_market_no=batch.market_no,
        returned_stock_code=batch.stock_code,
    )
    with pytest.raises(ValueError, match="TIMESTAMP_BASIS_CROSSCHECK_FAILED"):
        TV.build_ose_runtime_verification_from_exchange(
            batch,
            request_trace=request,
            callback_trace=callback,
            runtime_build_id="TEST_BUILD_C2",
        )


def test_runtime_exchange_builder_rejects_uncorrelated_callback():
    batch = _batch()
    request = TickDetailRequestTrace(
        request_id="tick_detail_7",
        request_time_utc=_dt(24, 6, 45, 30),
        market_no=TD.OSE_MARKET_NO,
        stock_code=batch.stock_code,
        last_count=20,
        accepted=True,
    )
    callback = TickDetailCallbackTrace(
        request_id="",
        callback_received_at_utc=batch.received_at,
        callback_mark=1,
        callback_index=TV.CALLBACK_INDEX,
        returned_market_no=batch.market_no,
        returned_stock_code=batch.stock_code,
    )
    with pytest.raises(ValueError, match="RUNTIME_REQUEST_CALLBACK_CORRELATION_MISMATCH"):
        TV.build_ose_runtime_verification_from_exchange(
            batch,
            request_trace=request,
            callback_trace=callback,
            runtime_build_id="TEST_BUILD_C2",
        )
