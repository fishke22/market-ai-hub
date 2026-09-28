"""Accuracy v2 P3-A bridge from governed P1 PIT packets to Chronos covariates.

This layer does not fabricate or backfill factor history.  It only converts a
sequence of already-governed REAL/DATA_READY P1 packets.  Synthetic packets
remain useful for engineering tests but cannot become market-ready covariates.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from typing import Any, Sequence

import pandas as pd

from market_ai_hub.models.chronos_model import ChronosPastCovariate

P3A_PROTOCOL_VERSION = "accuracy-v2-p3a-20260927"


def _aware(value: Any) -> datetime:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        raise ValueError("timezone-aware timestamp required")
    return ts.tz_convert("UTC").to_pydatetime()


def _hash(payload: Any) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:24]


def build_chronos_past_covariate_from_p1_packets(
    packets: Sequence[dict[str, Any]],
    *,
    target_index: pd.Index,
    final_decision_time: datetime,
    covariate_name: str = "factor_lagged_return",
) -> dict[str, Any]:
    """Convert one P1 packet per target-history row into a P3-A covariate.

    No sorting or forward filling occurs.  Input order must already match the
    target history.  Any non-REAL/non-DATA_READY packet leaves the bridge at
    DATA_NOT_READY rather than silently promoting synthetic or incomplete data.
    """
    base: dict[str, Any] = {
        "engineering_status": "PASS",
        "data_status": "DATA_NOT_READY",
        "rejection_reason": None,
        "protocol_version": P3A_PROTOCOL_VERSION,
        "packet_count": len(packets),
        "covariate_name": covariate_name,
        "covariate": None,
        "bridge_identity": None,
    }
    try:
        final_decision = _aware(final_decision_time)
    except Exception:
        base.update(engineering_status="FAIL", rejection_reason="FINAL_DECISION_TIME_INVALID")
        return base

    if not packets:
        base["rejection_reason"] = "NO_P1_PACKETS"
        return base
    if len(packets) != len(target_index):
        base.update(
            engineering_status="FAIL",
            rejection_reason="PACKET_TARGET_LENGTH_MISMATCH",
        )
        return base
    if not target_index.is_unique:
        base.update(engineering_status="FAIL", rejection_reason="DUPLICATE_TARGET_INDEX")
        return base
    if not target_index.is_monotonic_increasing:
        base.update(engineering_status="FAIL", rejection_reason="TARGET_INDEX_NOT_MONOTONIC")
        return base

    packet_decisions: list[datetime] = []
    event_times: list[datetime] = []
    available_at: list[datetime] = []
    values: list[float] = []
    source_hashes: list[str] = []
    cache_ids: list[str] = []
    representation_ids: set[str] = set()
    factor_contracts: set[str] = set()
    feature_versions: set[str] = set()
    p1_protocols: set[str] = set()

    for i, packet in enumerate(packets):
        if packet.get("engineering_status") != "PASS":
            base.update(engineering_status="FAIL", rejection_reason=f"P1_ENGINEERING_FAIL[{i}]")
            return base
        if packet.get("data_status") != "DATA_READY" or str(packet.get("evidence_origin") or "").upper() != "REAL":
            base["rejection_reason"] = f"P1_PACKET_NOT_REAL_DATA_READY[{i}]"
            return base
        features = packet.get("features") or {}
        try:
            value = float(features[covariate_name])
        except Exception:
            base.update(engineering_status="FAIL", rejection_reason=f"P1_FEATURE_MISSING[{i}]")
            return base
        if not math.isfinite(value):
            base.update(engineering_status="FAIL", rejection_reason=f"P1_FEATURE_NONFINITE[{i}]")
            return base

        try:
            packet_decision = _aware(packet["decision_time"])
            feature_available = _aware(packet["feature_available_at"])
        except Exception:
            base.update(engineering_status="FAIL", rejection_reason=f"P1_TIMESTAMP_INVALID[{i}]")
            return base
        if feature_available > packet_decision:
            base.update(engineering_status="FAIL", rejection_reason=f"P1_FUTURE_AVAILABLE_AT[{i}]")
            return base
        if packet_decision > final_decision:
            base.update(engineering_status="FAIL", rejection_reason=f"P1_PACKET_AFTER_FINAL_DECISION[{i}]")
            return base

        source = packet.get("source_identity") or {}
        source_hash = str(source.get("source_hash") or "").strip()
        source_events = source.get("event_time") or []
        cache_id = str(packet.get("cache_identity") or "").strip()
        if not source_hash or not cache_id or not source_events:
            base.update(engineering_status="FAIL", rejection_reason=f"P1_PROVENANCE_MISSING[{i}]")
            return base
        try:
            latest_source_event = max(_aware(x) for x in source_events)
        except Exception:
            base.update(engineering_status="FAIL", rejection_reason=f"P1_SOURCE_EVENT_INVALID[{i}]")
            return base
        if latest_source_event > feature_available:
            base.update(engineering_status="FAIL", rejection_reason=f"P1_SOURCE_EVENT_AFTER_AVAILABLE[{i}]")
            return base

        packet_decisions.append(packet_decision)
        event_times.append(latest_source_event)
        available_at.append(feature_available)
        values.append(value)
        source_hashes.append(source_hash)
        cache_ids.append(cache_id)
        representation_ids.add(str(packet.get("representation_id") or ""))
        factor_contracts.add(str(packet.get("factor_contract") or ""))
        feature_versions.add(str(packet.get("feature_version") or ""))
        p1_protocols.add(str(packet.get("protocol_version") or ""))

    if any(b <= a for a, b in zip(packet_decisions, packet_decisions[1:])):
        base.update(engineering_status="FAIL", rejection_reason="P1_DECISION_TIME_NOT_STRICTLY_INCREASING")
        return base
    if any(b <= a for a, b in zip(event_times, event_times[1:])):
        base.update(engineering_status="FAIL", rejection_reason="P1_SOURCE_EVENT_TIME_NOT_STRICTLY_INCREASING")
        return base
    if any(len(x) != 1 or "" in x for x in (representation_ids, factor_contracts, feature_versions, p1_protocols)):
        base.update(engineering_status="FAIL", rejection_reason="P1_PACKET_IDENTITY_MIXED")
        return base

    feature_version = next(iter(feature_versions))
    value_series = pd.Series(values, index=target_index, dtype=float)
    covariate = ChronosPastCovariate(
        values=value_series,
        event_time=event_times,
        available_at=available_at,
        source_hashes=source_hashes,
        feature_version=feature_version,
    )
    identity = {
        "p3a_protocol_version": P3A_PROTOCOL_VERSION,
        "p1_protocol_version": next(iter(p1_protocols)),
        "representation_id": next(iter(representation_ids)),
        "factor_contract": next(iter(factor_contracts)),
        "feature_version": feature_version,
        "packet_cache_ids": cache_ids,
        "source_hashes": source_hashes,
        "target_index_hash": _hash([str(x) for x in target_index]),
        "final_decision_time": final_decision.isoformat(),
    }
    identity["identity_hash"] = _hash(identity)
    base.update(
        data_status="DATA_READY",
        covariate=covariate,
        bridge_identity=identity,
    )
    return base
