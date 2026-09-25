"""C2 — typed runtime evidence for W3.3 OSE tick-detail verification.

The raw TickDetailBatch remains immutable and UNVERIFIED.  Runtime verification is a
separate evidence artifact binding the actual request/callback facts to the canonical
raw source snapshot.  The evidence id is an integrity hash, not a cryptographic
signature or broker attestation.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, time, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from market_ai_hub.research.v2 import tick_detail_source as TD

RUNTIME_EVIDENCE_SCHEMA_VERSION = "W3.3-C2.2"
TIMESTAMP_BASIS_METHOD_OSE_LOCAL_CLOCK = "OSE_SESSION_LOCAL_CLOCK_CROSSCHECK_V1"
CALLBACK_INDEX = "GetStkTickDetail"
CROSSCHECK_PASS = "OSE_LOCAL_CLOCK_CROSSCHECK_PASS"
CROSSCHECK_BLOCKED = "OSE_LOCAL_CLOCK_CROSSCHECK_BLOCKED"
CROSSCHECK_NEAR_CLOSE_START = time(15, 30)
CROSSCHECK_MAX_LOCAL_AGE = timedelta(minutes=90)
CROSSCHECK_UTC_FUTURE_MARGIN = timedelta(hours=4)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("runtime evidence timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class TickDetailRuntimeVerificationEvidence:
    runtime_request_id: str
    runtime_build_id: str
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
    if not str(evidence.runtime_build_id or "").strip():
        blockers.append("RUNTIME_BUILD_ID_REQUIRED")
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



def crosscheck_ose_local_timestamp_basis(
    batch: TD.TickDetailBatch,
    *,
    request_time: datetime,
    callback_received_at: datetime,
) -> dict[str, Any]:
    """Fail-closed runtime check that distinguishes OSE-local clock from UTC/other bases."""
    request_utc = _aware(request_time)
    callback_utc = _aware(callback_received_at)
    blockers: list[str] = []
    request_window = TD.ose_close_query_window(request_utc)
    callback_window = TD.ose_close_query_window(callback_utc)
    if request_window["status"] != TD.STATUS_QUERY_WINDOW_READY:
        blockers.append("REQUEST_OUTSIDE_CONTROLLED_WINDOW")
    if callback_window["status"] != TD.STATUS_QUERY_WINDOW_READY:
        blockers.append("CALLBACK_OUTSIDE_CONTROLLED_WINDOW")
    if request_window["trading_date"] != callback_window["trading_date"]:
        blockers.append("REQUEST_CALLBACK_TRADING_DATE_MISMATCH")
    if callback_utc < request_utc:
        blockers.append("CALLBACK_PRECEDES_REQUEST")
    if batch.market_no != TD.OSE_MARKET_NO:
        blockers.append("MARKET_NOT_OSE")
    if not str(batch.stock_code or "").upper().startswith("JNU"):
        blockers.append("NOT_JNU_CONTRACT")
    if batch.received_at.astimezone(timezone.utc) != callback_utc:
        blockers.append("CALLBACK_RECEIPT_BATCH_MISMATCH")

    jst = ZoneInfo(TD.OSE_TIMEZONE)
    trading_date = request_utc.astimezone(jst).date()
    valid = [
        row for row in batch.rows
        if row.raw_timestamp.date() == trading_date
        and float(row.deal_price) > 0
        and int(row.deal_volume) > 0
    ]
    last = max(valid, key=lambda row: (row.raw_timestamp, int(row.seq_no))) if valid else None
    local_interpretation_utc = None
    utc_interpretation = None
    if last is None:
        blockers.append("NO_VALID_SAME_DAY_TRADE")
    else:
        if last.raw_timestamp.time() < CROSSCHECK_NEAR_CLOSE_START:
            blockers.append("NO_NEAR_CLOSE_TRADE_FOR_BASIS_CROSSCHECK")
        if last.raw_timestamp.time() > TD.OSE_DAY_CLOSE:
            blockers.append("RAW_TRADE_AFTER_DAY_CLOSE")
        local_interpretation_utc = last.raw_timestamp.replace(tzinfo=jst).astimezone(timezone.utc)
        utc_interpretation = last.raw_timestamp.replace(tzinfo=timezone.utc)
        if local_interpretation_utc > callback_utc:
            blockers.append("OSE_LOCAL_INTERPRETATION_IS_FUTURE")
        elif callback_utc - local_interpretation_utc > CROSSCHECK_MAX_LOCAL_AGE:
            blockers.append("OSE_LOCAL_INTERPRETATION_TOO_OLD")
        if utc_interpretation <= callback_utc + CROSSCHECK_UTC_FUTURE_MARGIN:
            blockers.append("UTC_ALTERNATIVE_NOT_DISPROVEN")

    passed = not blockers
    return {
        "status": CROSSCHECK_PASS if passed else CROSSCHECK_BLOCKED,
        "reason": ";".join(sorted(set(blockers))),
        "timestamp_basis_status": (
            TD.TIMESTAMP_BASIS_RUNTIME_VERIFIED if passed else TD.TIMESTAMP_BASIS_UNVERIFIED
        ),
        "timestamp_basis_method": (
            TIMESTAMP_BASIS_METHOD_OSE_LOCAL_CLOCK if passed else ""
        ),
        "timestamp_crosscheck_passed": passed,
        "trading_date": trading_date.isoformat(),
        "last_trade_raw_timestamp": (
            last.raw_timestamp.isoformat(timespec="milliseconds") if last is not None else None
        ),
        "local_interpretation_utc": (
            local_interpretation_utc.isoformat() if local_interpretation_utc is not None else None
        ),
        "utc_interpretation": (
            utc_interpretation.isoformat() if utc_interpretation is not None else None
        ),
        "values_exposed": False,
    }

def build_ose_runtime_verification_evidence(
    batch: TD.TickDetailBatch,
    *,
    runtime_request_id: str,
    runtime_build_id: str,
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
        runtime_build_id=str(runtime_build_id),
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
    runtime_build_id: str,
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
        runtime_build_id=runtime_build_id,
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


def batch_from_artifact_payload(payload: dict[str, Any]) -> TD.TickDetailBatch:
    """Reconstruct and revalidate one persisted raw tick-detail artifact."""
    rows = [
        TD.TickDetailRow(
            raw_timestamp=datetime.fromisoformat(str(row["raw_timestamp"])),
            deal_price=float(row["deal_price"]),
            deal_volume=int(row["deal_volume"]),
            buy_price=float(row["buy_price"]),
            sell_price=float(row["sell_price"]),
            seq_no=int(row["seq_no"]),
            in_out_flag=int(row["in_out_flag"]),
        )
        for row in list(payload.get("rows", []))
    ]
    batch = TD.TickDetailBatch(
        market_no=int(payload["market_no"]),
        stock_code=str(payload["stock_code"]),
        rows=rows,
        received_at=datetime.fromisoformat(str(payload["received_at"])),
        provider=str(payload.get("provider", "YUANTA_SPARK")),
        source_type=str(payload.get("source_type", TD.YUANTA_SPARK_TICK_DETAIL)),
    )
    expected = TD.canonical_tick_detail_snapshot_id(batch)
    claimed = str(payload.get("source_snapshot_id", "") or "")
    if not claimed or claimed != expected:
        raise ValueError("SOURCE_SNAPSHOT_ID_CANONICAL_MISMATCH")
    return replace(batch, source_snapshot_id=claimed)


def _require_bool(payload: dict[str, Any], key: str) -> bool:
    value = payload.get(key)
    if type(value) is not bool:
        raise ValueError(f"{key.upper()}_MUST_BE_BOOL")
    return value


def evidence_from_artifact_payload(
    payload: dict[str, Any],
) -> TickDetailRuntimeVerificationEvidence:
    """Reconstruct one persisted typed evidence artifact and verify its integrity id."""
    evidence = TickDetailRuntimeVerificationEvidence(
        runtime_request_id=str(payload["runtime_request_id"]),
        runtime_build_id=str(payload["runtime_build_id"]),
        request_time=datetime.fromisoformat(str(payload["request_time"])),
        callback_received_at=datetime.fromisoformat(str(payload["callback_received_at"])),
        requested_market_no=int(payload["requested_market_no"]),
        requested_stock_code=str(payload["requested_stock_code"]),
        last_count=int(payload["last_count"]),
        request_accepted=_require_bool(payload, "request_accepted"),
        callback_index=str(payload["callback_index"]),
        callback_mark=int(payload["callback_mark"]),
        returned_market_no=int(payload["returned_market_no"]),
        returned_stock_code=str(payload["returned_stock_code"]),
        source_snapshot_id=str(payload["source_snapshot_id"]),
        timestamp_basis_status=str(payload["timestamp_basis_status"]),
        timestamp_basis_method=str(payload["timestamp_basis_method"]),
        timestamp_crosscheck_passed=_require_bool(payload, "timestamp_crosscheck_passed"),
        schema_version=str(payload.get("schema_version", "")),
        evidence_id=str(payload.get("evidence_id", "")),
    )
    if evidence.evidence_id != canonical_evidence_id(evidence):
        raise ValueError("RUNTIME_EVIDENCE_ID_INVALID")
    return evidence


def load_runtime_measurement(
    raw_artifact: str | Path,
    evidence_artifact: str | Path,
) -> tuple[TD.TickDetailBatch, TickDetailRuntimeVerificationEvidence]:
    """Load persisted measurement artifacts and re-run all evidence/batch bindings."""
    raw_payload = json.loads(Path(raw_artifact).read_text(encoding="utf-8"))
    evidence_payload = json.loads(Path(evidence_artifact).read_text(encoding="utf-8"))
    batch = batch_from_artifact_payload(raw_payload)
    evidence = evidence_from_artifact_payload(evidence_payload)
    blockers = verification_blockers(batch, evidence)
    if blockers:
        raise ValueError(";".join(blockers))
    return batch, evidence
