"""C2A — fail-closed OSE terminal-close materialization from verified W3.3 ticks.

Offline-safe: no broker calls.  Raw TickDetailBatch objects never self-upgrade their
timestamp basis.  Eligibility requires a separate typed runtime verification evidence
artifact bound to the exact request, callback, and canonical raw source snapshot.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from math import isfinite
import re
from typing import Any
from zoneinfo import ZoneInfo

from market_ai_hub.feature_store.store import FeatureStore
from market_ai_hub.research.v2.factor_representation import (
    FactorRepresentationObservation,
    definition_for,
)
from market_ai_hub.research.v2.prediction_audit import lineage_from_observation
from market_ai_hub.research.v2.session_truth import resolve_venue_session
from market_ai_hub.research.v2 import tick_detail_source as TD
from market_ai_hub.research.v2 import tick_detail_verification as TV

MATERIALIZER_VERSION = "c2-ose-terminal-close-2"
FEATURE_NAME = "terminal_close"
FEATURE_VERSION = "w3.2-contract-daily-close-1"
STATUS_BLOCKED = "BLOCKED"
STATUS_CANDIDATE = "CANDIDATE"
STATUS_MATERIALIZED = "MATERIALIZED"
STATUS_ALREADY_MATERIALIZED = "ALREADY_MATERIALIZED"


@dataclass(frozen=True)
class TerminalCloseMaterializationResult:
    status: str
    reason: str = ""
    contract_code: str = ""
    contract_month: str = ""
    trading_date: str = ""
    source_trade_timestamp: datetime | None = None
    session_close_timestamp: datetime | None = None
    available_at: datetime | None = None
    close: float | None = None
    source_snapshot_ids: tuple[str, ...] = ()
    lineage_id: str = ""
    values_exposed: bool = False

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


def _blocked(reason: str, *, batch: TD.TickDetailBatch | None = None,
             contract_month: str = "") -> TerminalCloseMaterializationResult:
    return TerminalCloseMaterializationResult(
        status=STATUS_BLOCKED,
        reason=reason,
        contract_code=batch.stock_code if batch is not None else "",
        contract_month=contract_month,
        values_exposed=False,
    )


def _month_from_jnu(code: str) -> str:
    m = re.fullmatch(r"JNU(\d{2})(\d{2})", str(code or "").upper())
    if not m:
        return ""
    yy, mm = int(m.group(1)), int(m.group(2))
    return f"20{yy:02d}{mm:02d}" if 1 <= mm <= 12 else ""


def select_ose_terminal_close(
    batch: TD.TickDetailBatch,
    *,
    contract_month: str,
    verification_evidence: TV.TickDetailRuntimeVerificationEvidence | None = None,
) -> TerminalCloseMaterializationResult:
    """Select the last real day-session trade without fabricating its event time."""
    month = str(contract_month or "").strip()
    blockers: list[str] = TV.verification_blockers(batch, verification_evidence)
    if batch.market_no != TD.OSE_MARKET_NO:
        blockers.append("MARKET_NOT_OSE")
    expected_month = _month_from_jnu(batch.stock_code)
    if not expected_month:
        blockers.append("NOT_JNU_CONTRACT")
    if not re.fullmatch(r"20\d{4}", month):
        blockers.append("CONTRACT_MONTH_REQUIRED")
    elif expected_month and month != expected_month:
        blockers.append("CONTRACT_MONTH_CODE_MISMATCH")
    if not batch.source_snapshot_id:
        blockers.append("SOURCE_SNAPSHOT_ID_REQUIRED")
    if blockers:
        return _blocked(";".join(sorted(set(blockers))), batch=batch, contract_month=month)

    assert verification_evidence is not None
    jst = ZoneInfo(TD.OSE_TIMEZONE)
    trading_date = verification_evidence.request_time.astimezone(jst).date()
    close_local = datetime.combine(trading_date, TD.OSE_DAY_CLOSE, tzinfo=jst)
    after_close = [
        r for r in batch.rows
        if r.raw_timestamp.date() == trading_date and r.raw_timestamp.time() > TD.OSE_DAY_CLOSE
    ]
    if after_close:
        return _blocked("TRADE_AFTER_DAY_CLOSE_BEFORE_NIGHT_OPEN", batch=batch, contract_month=month)


    valid = [
        r for r in batch.rows
        if r.raw_timestamp.date() == trading_date
        and r.raw_timestamp.time() <= TD.OSE_DAY_CLOSE
        and isfinite(float(r.deal_price)) and float(r.deal_price) > 0
        and int(r.deal_volume) > 0 and int(r.seq_no) >= 0
    ]
    if not valid:
        return _blocked("NO_VALID_DAY_SESSION_TRADE", batch=batch, contract_month=month)
    keys = [(r.raw_timestamp, int(r.seq_no)) for r in valid]
    last_key = max(keys)
    if sum(1 for key in keys if key == last_key) != 1:
        return _blocked("AMBIGUOUS_LAST_TRADE", batch=batch, contract_month=month)
    last = max(valid, key=lambda r: (r.raw_timestamp, int(r.seq_no)))
    trade_utc = last.raw_timestamp.replace(tzinfo=jst).astimezone(timezone.utc)
    close_utc = close_local.astimezone(timezone.utc)
    available = batch.received_at.astimezone(timezone.utc)
    if trade_utc > close_utc or close_utc > available:
        return _blocked("TEMPORAL_ORDER_INVALID", batch=batch, contract_month=month)

    return TerminalCloseMaterializationResult(
        status=STATUS_CANDIDATE,
        contract_code=batch.stock_code,
        contract_month=month,
        trading_date=trading_date.isoformat(),
        source_trade_timestamp=trade_utc,
        session_close_timestamp=close_utc,
        available_at=available,
        close=float(last.deal_price),
        source_snapshot_ids=(batch.source_snapshot_id, verification_evidence.evidence_id),
        values_exposed=False,
    )


def _observation(candidate: TerminalCloseMaterializationResult, batch: TD.TickDetailBatch):
    d = definition_for("JP_EQUITY", "OSE_MICRO_FUTURES")
    if d is None:
        raise RuntimeError("OSE_MICRO_FUTURES definition missing")
    session = resolve_venue_session(d.venue_id, candidate.session_close_timestamp)

    if session.trading_date != candidate.trading_date:
        raise ValueError("SESSION_TRADING_DATE_MISMATCH")
    return FactorRepresentationObservation(
        economic_factor_id=d.economic_factor_id,
        representation_id=d.representation_id,
        instrument=d.instrument,
        instrument_type=d.instrument_type,
        representation_relation=d.representation_relation,
        temporal_role="PREVIOUS_SESSION_REFERENCE",
        resolved_role="PREVIOUS_SESSION_REFERENCE",
        venue_id=d.venue_id,
        calendar_id=d.calendar_id,
        timezone=TD.OSE_TIMEZONE,
        session=session,
        value=candidate.close,
        event_timestamp=candidate.session_close_timestamp,
        available_at=candidate.available_at,
        provider_timestamp=candidate.source_trade_timestamp,
        received_at=candidate.available_at,
        timestamp_precision="BAR_CLOSE_TIMESTAMP",
        staleness_status="CLOSED_MARKET_REFERENCE",
        availability_status="AVAILABLE",
        quality_status="RUNTIME_VERIFIED_TERMINAL_CLOSE",
        provider=batch.provider,
        source_type="YUANTA_SPARK_TICK_DETAIL_TERMINAL_CLOSE",
        source_frequency="DAILY",
        source_schema_version=TD.W3_TICK_DETAIL_SOURCE_SCHEMA_VERSION,
        source_version=MATERIALIZER_VERSION,
        source_snapshot_ids=list(candidate.source_snapshot_ids),
        data_grade="BROKER_RUNTIME_VERIFIED",
        point_in_time_safe=True,
        revision_status="ORIGINAL",
        contract_code=candidate.contract_code,
        contract_month=candidate.contract_month,
        roll_status="NONE",
        series_semantics="CONTRACT",
    )


def materialize_ose_terminal_close(
    batch: TD.TickDetailBatch,
    *,
    contract_month: str,
    verification_evidence: TV.TickDetailRuntimeVerificationEvidence | None = None,
    store: FeatureStore | None = None,
) -> TerminalCloseMaterializationResult:

    """Persist one immutable DAILY terminal close after all C2 gates pass."""
    candidate = select_ose_terminal_close(
        batch,
        contract_month=contract_month,
        verification_evidence=verification_evidence,
    )
    if candidate.status != STATUS_CANDIDATE:
        return candidate
    fs = store or FeatureStore()
    obs = _observation(candidate, batch)
    lineage = lineage_from_observation(obs)

    if fs.db_path.exists():
        with fs._conn() as con:
            exists = con.execute(
                """SELECT lineage_id FROM features
                   WHERE representation_id=? AND contract_code=?
                     AND feature_name=? AND feature_version=? AND event_time=?""",
                [
                    "OSE_MICRO_FUTURES", candidate.contract_code,
                    FEATURE_NAME, FEATURE_VERSION,
                    candidate.session_close_timestamp.replace(tzinfo=None),
                ],
            ).fetchall()
        if exists:
            if len(exists) == 1 and str(exists[0][0]) == lineage.lineage_id:
                return TerminalCloseMaterializationResult(
                    **{**candidate.model_dump(), "status": STATUS_ALREADY_MATERIALIZED,
                       "lineage_id": lineage.lineage_id}
                )
            return _blocked("CONFLICTING_TERMINAL_CLOSE", batch=batch,
                            contract_month=candidate.contract_month)

    stored = fs.put_observation(
        obs,
        as_of=candidate.available_at,
        materialize_feature=True,
        feature_name=FEATURE_NAME,
        feature_version=FEATURE_VERSION,
        materialization_mode="DERIVED_DAILY",
    )
    if stored["model_feature_status"] not in ("MATERIALIZED", "IDEMPOTENT_FEATURE"):
        return _blocked(
            f"FEATURE_STORE_REJECTED:{stored['model_feature_status']}",
            batch=batch, contract_month=candidate.contract_month,
        )
    return TerminalCloseMaterializationResult(
        **{**candidate.model_dump(), "status": STATUS_MATERIALIZED,
           "lineage_id": str(stored["lineage_id"])}
    )
