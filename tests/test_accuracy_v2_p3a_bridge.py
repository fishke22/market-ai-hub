"""P3-A bridge: P1 PIT packets remain governed when fed to Chronos."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from market_ai_hub.research.accuracy_v2_p3a import (
    build_chronos_past_covariate_from_p1_packets,
)


BASE = datetime(2026, 8, 1, 9, 0, tzinfo=timezone.utc)


def _packet(i: int, *, evidence_origin: str = "REAL", data_status: str = "DATA_READY") -> dict:
    decision = BASE + timedelta(days=i * 2 + 1)
    event = BASE + timedelta(days=i * 2)
    available = event + timedelta(minutes=5)
    return {
        "engineering_status": "PASS",
        "data_status": data_status,
        "evidence_origin": evidence_origin,
        "factor": "lagged_return",
        "representation_id": "NQ_FUTURES",
        "factor_contract": "NQ_2612",
        "feature_name": "quote_value",
        "feature_version": "accuracy-v2-p3a-fixture",
        "decision_time": decision.isoformat(),
        "features": {"factor_lagged_return": 0.001 * (i + 1)},
        "feature_available_at": available.isoformat(),
        "protocol_version": "accuracy-v2-p1-20260927",
        "source_identity": {
            "event_time": [
                (event - timedelta(days=1)).isoformat(),
                event.isoformat(),
            ],
            "source_hash": f"source-{i}",
        },
        "cache_identity": f"cache-{i}",
    }


def test_p3a_bridge_builds_real_data_ready_covariate_without_sort_or_fill():
    idx = pd.date_range("2026-08-01", periods=4, freq="2D", tz="UTC")
    packets = [_packet(i) for i in range(4)]
    out = build_chronos_past_covariate_from_p1_packets(
        packets,
        target_index=idx,
        final_decision_time=BASE + timedelta(days=20),
    )
    assert out["engineering_status"] == "PASS"
    assert out["data_status"] == "DATA_READY"
    cov = out["covariate"]
    assert list(cov.values.index) == list(idx)
    assert list(cov.values) == [0.001, 0.002, 0.003, 0.004]
    assert list(cov.source_hashes) == [f"source-{i}" for i in range(4)]
    assert out["bridge_identity"]["packet_cache_ids"] == [f"cache-{i}" for i in range(4)]


def test_p3a_bridge_never_promotes_synthetic_packet_to_market_ready():
    idx = pd.date_range("2026-08-01", periods=2, freq="2D", tz="UTC")
    packets = [_packet(0), _packet(1, evidence_origin="SYNTHETIC", data_status="DATA_NOT_READY")]
    out = build_chronos_past_covariate_from_p1_packets(
        packets,
        target_index=idx,
        final_decision_time=BASE + timedelta(days=20),
    )
    assert out["engineering_status"] == "PASS"
    assert out["data_status"] == "DATA_NOT_READY"
    assert out["covariate"] is None
    assert out["rejection_reason"] == "P1_PACKET_NOT_REAL_DATA_READY[1]"


def test_p3a_bridge_rejects_mixed_identity_and_future_availability():
    idx = pd.date_range("2026-08-01", periods=2, freq="2D", tz="UTC")
    mixed = [_packet(0), _packet(1)]
    mixed[1]["factor_contract"] = "NQ_2703"
    out = build_chronos_past_covariate_from_p1_packets(
        mixed,
        target_index=idx,
        final_decision_time=BASE + timedelta(days=20),
    )
    assert out["engineering_status"] == "FAIL"
    assert out["rejection_reason"] == "P1_PACKET_IDENTITY_MIXED"

    future = [_packet(0), _packet(1)]
    future[1]["feature_available_at"] = (
        pd.Timestamp(future[1]["decision_time"]) + pd.Timedelta(seconds=1)
    ).isoformat()
    out = build_chronos_past_covariate_from_p1_packets(
        future,
        target_index=idx,
        final_decision_time=BASE + timedelta(days=20),
    )
    assert out["engineering_status"] == "FAIL"
    assert out["rejection_reason"] == "P1_FUTURE_AVAILABLE_AT[1]"


def test_p3a_bridge_rejects_reordered_packets_and_length_mismatch():
    idx = pd.date_range("2026-08-01", periods=3, freq="2D", tz="UTC")
    packets = [_packet(0), _packet(2), _packet(1)]
    out = build_chronos_past_covariate_from_p1_packets(
        packets,
        target_index=idx,
        final_decision_time=BASE + timedelta(days=20),
    )
    assert out["engineering_status"] == "FAIL"
    assert out["rejection_reason"] == "P1_DECISION_TIME_NOT_STRICTLY_INCREASING"

    out = build_chronos_past_covariate_from_p1_packets(
        [_packet(0), _packet(1)],
        target_index=idx,
        final_decision_time=BASE + timedelta(days=20),
    )
    assert out["engineering_status"] == "FAIL"
    assert out["rejection_reason"] == "PACKET_TARGET_LENGTH_MISMATCH"

    bad_idx = pd.DatetimeIndex([idx[0], idx[2], idx[1]])
    out = build_chronos_past_covariate_from_p1_packets(
        [_packet(0), _packet(1), _packet(2)],
        target_index=bad_idx,
        final_decision_time=BASE + timedelta(days=20),
    )
    assert out["engineering_status"] == "FAIL"
    assert out["rejection_reason"] == "TARGET_INDEX_NOT_MONOTONIC"
