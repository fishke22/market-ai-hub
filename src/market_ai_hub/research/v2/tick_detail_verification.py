"""C2 — typed runtime evidence for W3.3 OSE tick-detail verification.

The raw TickDetailBatch remains immutable and UNVERIFIED.  Runtime verification is a
separate evidence artifact binding the actual request/callback facts to the canonical
raw source snapshot.  The evidence id is an integrity hash, not a cryptographic
signature or broker attestation.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any

from market_ai_hub.research.v2 import tick_detail_source as TD

RUNTIME_EVIDENCE_SCHEMA_VERSION = "W3.3-C2.1"
TIMESTAMP_BASIS_METHOD_OSE_LOCAL_CLOCK = "OSE_SESSION_LOCAL_CLOCK_CROSSCHECK_V1"
CALLBACK_INDEX = "GetStkTickDetail"


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("runtime evidence timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class TickDetailRuntimeVerificationEvidence:
    runtime_request_id: str
    request_time: datetime
    callback_received_at: datetime
    requested_market_no: int
    requested_stock_code: str
    last_count: int
    request_accepted: bool
    callback_index: str
    callback_mark: int
    returned_market_no: int
    returned_stock_code: str
    source_snapshot_id: str
    timestamp_basis_status: str
    timestamp_basis_method: str
    timestamp_crosscheck_passed: bool
    schema_version: str = RUNTIME_EVIDENCE_SCHEMA_VERSION
    evidence_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "request_time", _aware(self.request_time))
        object.__setattr__(self, "callback_received_at", _aware(self.callback_received_at))

    def identity_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        payload.pop("evidence_id", None)
        payload["request_time"] = self.request_time.isoformat()
        payload["callback_received_at"] = self.callback_received_at.isoformat()
        return payload

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


def canonical_evidence_id(evidence: TickDetailRuntimeVerificationEvidence) -> str:
    encoded = json.dumps(
        evidence.identity_payload(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    ).encode("utf-8")
    return "w33_verify_" + sha256(encoded).hexdigest()[:24]


def verification_blockers(
    batch: TD.TickDetailBatch,
    evidence: TickDetailRuntimeVerificationEvidence | None,
) -> list[str]:
    blockers: list[str] = []
    if evidence is None:
        return ["RUNTIME_VERIFICATION_EVIDENCE_REQUIRED"]

    if batch.timestamp_basis_status != TD.TIMESTAMP_BASIS_UNVERIFIED:
        blockers.append("RAW_BATCH_VERIFICATION_STATE_MUTATED")
    expected_snapshot = TD.canonical_tick_detail_snapshot_id(batch)
    if not batch.source_snapshot_id:
        blockers.append("SOURCE_SNAPSHOT_ID_REQUIRED")
    elif batch.source_snapshot_id != expected_snapshot:
        blockers.append("SOURCE_SNAPSHOT_ID_CANONICAL_MISMATCH")

    if evidence.schema_version != RUNTIME_EVIDENCE_SCHEMA_VERSION:
        blockers.append("RUNTIME_EVIDENCE_SCHEMA_MISMATCH")
    if not str(evidence.runtime_request_id or "").strip():
        blockers.append("RUNTIME_REQUEST_ID_REQUIRED")
    if not evidence.evidence_id or evidence.evidence_id != canonical_evidence_id(evidence):
        blockers.append("RUNTIME_EVIDENCE_ID_INVALID")
    if evidence.source_snapshot_id != batch.source_snapshot_id:
        blockers.append("RUNTIME_EVIDENCE_SOURCE_SNAPSHOT_MISMATCH")

    if evidence.requested_market_no != TD.OSE_MARKET_NO:
        blockers.append("REQUEST_MARKET_NOT_OSE")
    if evidence.requested_market_no != batch.market_no:
        blockers.append("REQUEST_BATCH_MARKET_MISMATCH")
    if evidence.returned_market_no != batch.market_no:
        blockers.append("CALLBACK_BATCH_MARKET_MISMATCH")

    requested_code = str(evidence.requested_stock_code or "").strip()
    returned_code = str(evidence.returned_stock_code or "").strip()
    batch_code = str(batch.stock_code or "").strip()
    if requested_code != batch_code:
        blockers.append("REQUEST_BATCH_CODE_MISMATCH")
    if returned_code != batch_code:
        blockers.append("CALLBACK_BATCH_CODE_MISMATCH")

    if not evidence.request_accepted:
        blockers.append("REQUEST_NOT_ACCEPTED")
    if not 1 <= int(evidence.last_count) <= TD.MAX_LAST_COUNT:
        blockers.append("LAST_COUNT_OUT_OF_RANGE")
    if evidence.callback_index != CALLBACK_INDEX:
        blockers.append("CALLBACK_INDEX_MISMATCH")
    if evidence.callback_received_at != batch.received_at.astimezone(timezone.utc):
        blockers.append("CALLBACK_RECEIPT_BATCH_MISMATCH")
    if evidence.request_time > evidence.callback_received_at:
        blockers.append("CALLBACK_PRECEDES_REQUEST")

    request_window = TD.ose_close_query_window(evidence.request_time)
    if request_window["status"] != TD.STATUS_QUERY_WINDOW_READY:
        blockers.append("REQUEST_OUTSIDE_CONTROLLED_WINDOW")
    callback_window = TD.ose_close_query_window(evidence.callback_received_at)
    if callback_window["status"] != TD.STATUS_QUERY_WINDOW_READY:
        blockers.append("CALLBACK_OUTSIDE_CONTROLLED_WINDOW")
    if request_window["trading_date"] != callback_window["trading_date"]:
        blockers.append("REQUEST_CALLBACK_TRADING_DATE_MISMATCH")

    if evidence.timestamp_basis_status != TD.TIMESTAMP_BASIS_RUNTIME_VERIFIED:
        blockers.append("TIMESTAMP_BASIS_RUNTIME_VERIFICATION_REQUIRED")
    if not evidence.timestamp_crosscheck_passed:
        blockers.append("TIMESTAMP_BASIS_CROSSCHECK_FAILED")
    if evidence.timestamp_basis_method != TIMESTAMP_BASIS_METHOD_OSE_LOCAL_CLOCK:
        blockers.append("TIMESTAMP_BASIS_METHOD_UNSUPPORTED")

    return sorted(set(blockers))


def build_ose_runtime_verification_evidence(
    batch: TD.TickDetailBatch,
    *,
    runtime_request_id: str,
    request_time: datetime,
    callback_received_at: datetime,
    requested_market_no: int,
    requested_stock_code: str,
    last_count: int,
    request_accepted: bool,
    callback_index: str,
    callback_mark: int,
    returned_market_no: int,
    returned_stock_code: str,
    timestamp_basis_status: str,
    timestamp_basis_method: str,
    timestamp_crosscheck_passed: bool,
) -> TickDetailRuntimeVerificationEvidence:
    """Build validated evidence from a matched request/callback measurement."""
    evidence = TickDetailRuntimeVerificationEvidence(
        runtime_request_id=str(runtime_request_id),
        request_time=request_time,
        callback_received_at=callback_received_at,
        requested_market_no=int(requested_market_no),
        requested_stock_code=str(requested_stock_code),
        last_count=int(last_count),
        request_accepted=bool(request_accepted),
        callback_index=str(callback_index),
        callback_mark=int(callback_mark),
        returned_market_no=int(returned_market_no),
        returned_stock_code=str(returned_stock_code),
        source_snapshot_id=str(batch.source_snapshot_id),
        timestamp_basis_status=str(timestamp_basis_status),
        timestamp_basis_method=str(timestamp_basis_method),
        timestamp_crosscheck_passed=bool(timestamp_crosscheck_passed),
    )
    evidence = replace(evidence, evidence_id=canonical_evidence_id(evidence))
    blockers = verification_blockers(batch, evidence)
    if blockers:
        raise ValueError(";".join(blockers))
    return evidence


def build_ose_runtime_verification_from_exchange(
    batch: TD.TickDetailBatch,
    *,
    request_trace: Any,
    callback_trace: Any,
    timestamp_basis_status: str,
    timestamp_basis_method: str,
    timestamp_crosscheck_passed: bool,
) -> TickDetailRuntimeVerificationEvidence:
    """Build evidence only from one runtime-correlated request/callback pair."""
    request_id = str(getattr(request_trace, "request_id", "") or "")
    callback_request_id = str(getattr(callback_trace, "request_id", "") or "")
    if not request_id or request_id != callback_request_id:
        raise ValueError("RUNTIME_REQUEST_CALLBACK_CORRELATION_MISMATCH")
    accepted = getattr(request_trace, "accepted", None)
    if accepted is None:
        raise ValueError("REQUEST_ACCEPTANCE_NOT_FINAL")
    return build_ose_runtime_verification_evidence(
        batch,
        runtime_request_id=request_id,
        request_time=getattr(request_trace, "request_time_utc"),
        callback_received_at=getattr(callback_trace, "callback_received_at_utc"),
        requested_market_no=getattr(request_trace, "market_no"),
        requested_stock_code=getattr(request_trace, "stock_code"),
        last_count=getattr(request_trace, "last_count"),
        request_accepted=bool(accepted),
        callback_index=getattr(callback_trace, "callback_index"),
        callback_mark=getattr(callback_trace, "callback_mark"),
        returned_market_no=getattr(callback_trace, "returned_market_no"),
        returned_stock_code=getattr(callback_trace, "returned_stock_code"),
        timestamp_basis_status=timestamp_basis_status,
        timestamp_basis_method=timestamp_basis_method,
        timestamp_crosscheck_passed=timestamp_crosscheck_passed,
    )
