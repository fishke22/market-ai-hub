from __future__ import annotations

import json

import pytest

from market_ai_hub.services.taiwan_context_receipts import (
    STATUS_ALREADY_CAPTURED,
    STATUS_CAPTURED,
    STATUS_NOT_AVAILABLE_BEFORE_DECISION,
    TaiwanContextReceiptIntegrityError,
    TaiwanContextReceiptStore,
)


def _snapshot(*, retrieved_at="2026-09-28T01:00:00Z", pe=14.02):
    return {
        "schema_version": "TAIWAN_STOCK_CONTEXT_V3",
        "source_semantics_version": "FINMIND_TWSE_RECEIPT_TARGET_CONTEXT_ASOF_V3",
        "symbol": "3706.TW",
        "stock_id": "3706",
        "cutoff": "2026-09-28T00:00:00Z",
        "as_of": "2026-09-28T00:00:00Z",
        "retrieved_at": retrieved_at,
        "role": "TARGET_CONTEXT_ONLY_NOT_PREDICTIVE_FEATURE",
        "predictive_feature_allowed": False,
        "historical_revision_safe": False,
        "channels": {
            "valuation": {
                "status": "AVAILABLE",
                "values": {"pe_ratio": pe},
            }
        },
    }


def test_receipt_capture_is_content_addressed_append_only_and_idempotent(tmp_path):
    store = TaiwanContextReceiptStore(tmp_path)
    snap = _snapshot()

    first = store.capture(snap, observed_at="2026-09-28T01:00:01Z")
    second = store.capture(snap, observed_at="2026-09-28T01:00:02Z")

    assert first["status"] == STATUS_CAPTURED
    assert second["status"] == STATUS_ALREADY_CAPTURED
    assert first["receipt_id"] == second["receipt_id"]
    assert first["historical_backfill_eligible"] is False
    assert first["predictive_feature_allowed"] is False
    assert len(list((tmp_path / "snapshots").glob("*.json"))) == 1
    loaded = store.load(first["receipt_id"])
    assert loaded["context"]["channels"]["valuation"]["values"]["pe_ratio"] == 14.02


def test_later_revision_creates_new_receipt_and_never_rewrites_prior_decision(tmp_path):
    store = TaiwanContextReceiptStore(tmp_path)
    early = store.capture(
        _snapshot(retrieved_at="2026-09-28T01:00:00Z", pe=14.02),
        observed_at="2026-09-28T01:00:01Z",
    )
    later = store.capture(
        _snapshot(retrieved_at="2026-09-28T03:00:00Z", pe=99.0),
        observed_at="2026-09-28T03:00:01Z",
    )

    assert early["receipt_id"] != later["receipt_id"]
    assert len(store.receipt_ids()) == 2

    before_any = store.select_for_decision("3706", "2026-09-28T00:30:00Z")
    assert before_any["status"] == STATUS_NOT_AVAILABLE_BEFORE_DECISION

    between = store.select_for_decision("3706", "2026-09-28T02:00:00Z")
    assert between["receipt_id"] == early["receipt_id"]
    assert between["context"]["channels"]["valuation"]["values"]["pe_ratio"] == 14.02
    assert between["receipt_time_revision_safe"] is True
    assert between["predictive_feature_allowed"] is False

    after = store.select_for_decision("3706", "2026-09-28T04:00:00Z")
    assert after["receipt_id"] == later["receipt_id"]
    assert after["context"]["channels"]["valuation"]["values"]["pe_ratio"] == 99.0


def test_tampered_receipt_fails_closed(tmp_path):
    store = TaiwanContextReceiptStore(tmp_path)
    captured = store.capture(
        _snapshot(),
        observed_at="2026-09-28T01:00:01Z",
    )
    path = tmp_path / captured["artifact_path"]
    raw = json.loads(path.read_text(encoding="utf-8"))
    raw["context"]["channels"]["valuation"]["values"]["pe_ratio"] = 999.0
    path.write_text(json.dumps(raw), encoding="utf-8")

    with pytest.raises(TaiwanContextReceiptIntegrityError, match="mismatch"):
        store.load(captured["receipt_id"])
    with pytest.raises(TaiwanContextReceiptIntegrityError, match="mismatch"):
        store.capture(_snapshot(), observed_at="2026-09-28T01:00:02Z")


def test_retrieved_at_after_observed_capture_time_is_rejected(tmp_path):
    store = TaiwanContextReceiptStore(tmp_path)
    with pytest.raises(TaiwanContextReceiptIntegrityError, match="later"):
        store.capture(
            _snapshot(retrieved_at="2026-09-28T02:00:00Z"),
            observed_at="2026-09-28T01:59:59Z",
        )


def test_naive_receipt_timestamp_is_rejected(tmp_path):
    store = TaiwanContextReceiptStore(tmp_path)
    with pytest.raises(TaiwanContextReceiptIntegrityError, match="timezone-aware"):
        store.capture(
            _snapshot(retrieved_at="2026-09-28T01:00:00"),
            observed_at="2026-09-28T01:00:01Z",
        )
