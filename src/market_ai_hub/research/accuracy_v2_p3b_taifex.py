"""Accuracy v2 P3-B — forward-safe TAIFEX TMF official settlement ingestion.

Historical TAIFEX daily rows do not expose an exact publication timestamp.  This module
therefore binds available_at to the actual content receipt timestamp captured by the
provider snapshot.  It never backdates availability to the trading date.

Only exact monthly TMF contracts, regular-session official settlement values, immutable
content snapshots, and the existing FeatureStore DERIVED_DAILY gate are accepted.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timezone
import math
import re
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from market_ai_hub.feature_store.store import FeatureStore
from market_ai_hub.integrations.yuanta.resolver import taifex_last_trading_date
from market_ai_hub.providers.taifex import TaifexDailySnapshot
from market_ai_hub.research.v2.factor_representation import (
    FactorRepresentationObservation,
    definition_for,
)
from market_ai_hub.research.v2.prediction_audit import lineage_from_observation
from market_ai_hub.research.v2.session_truth import resolve_venue_session


SCHEMA_VERSION = "accuracy-v2-p3b-taifex-settlement-1"
FEATURE_NAME = "official_settlement"
FEATURE_VERSION = "accuracy-v2-p3b-taifex-settlement-v1"
STATUS_MATERIALIZED = "MATERIALIZED"
STATUS_ALREADY_MATERIALIZED = "ALREADY_MATERIALIZED"
STATUS_BLOCKED = "BLOCKED"
TAIPEI = ZoneInfo("Asia/Taipei")


@dataclass(frozen=True)
class TaifexSettlementMaterializationResult:
    status: str
    reason: str = ""
    contract_code: str = ""
    contract_month: str = ""
    trading_date: str = ""
    event_timestamp: datetime | None = None
    available_at: datetime | None = None
    source_snapshot_id: str = ""
    lineage_id: str = ""
    values_exposed: bool = False

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class _Candidate:
    contract_code: str
    contract_month: str
    trading_date: date
    settlement: float
    event_timestamp: datetime
    available_at: datetime
    source_snapshot_id: str
    session: Any
    days_to_expiry: int


def _blocked(
    reason: str,
    *,
    contract_code: str = "",
    contract_month: str = "",
    trading_date: str = "",
    available_at: datetime | None = None,
    source_snapshot_id: str = "",
) -> TaifexSettlementMaterializationResult:
    return TaifexSettlementMaterializationResult(
        status=STATUS_BLOCKED,
        reason=reason,
        contract_code=contract_code,
        contract_month=contract_month,
        trading_date=trading_date,
        available_at=available_at,
        source_snapshot_id=source_snapshot_id,
        values_exposed=False,
    )


def _parse_price(value: Any) -> float | None:
    raw = str(value or "").strip().replace(",", "")
    if raw in {"", "-", "--"}:
        return None
    try:
        parsed = float(raw)
    except ValueError:
        return None
    return parsed if math.isfinite(parsed) and parsed > 0 else None


def _candidate_from_row(
    snapshot: TaifexDailySnapshot,
    row: pd.Series,
) -> _Candidate | TaifexSettlementMaterializationResult | None:
    session_name = str(row.get("交易時段") or "").strip()
    if session_name != "一般":
        return None

    commodity = str(row.get("契約") or "").strip().upper()
    if commodity != "TMF" or snapshot.commodity != "TMF":
        return _blocked(
            "CONTRACT_FAMILY_MISMATCH",
            available_at=snapshot.received_at,
            source_snapshot_id=snapshot.source_snapshot_id,
        )

    month = str(row.get("到期月份(週別)") or "").strip()
    if not re.fullmatch(r"20\d{4}", month):
        return _blocked(
            "MONTHLY_EXACT_CONTRACT_REQUIRED",
            available_at=snapshot.received_at,
            source_snapshot_id=snapshot.source_snapshot_id,
        )
    year, mon = int(month[:4]), int(month[4:])
    if not 1 <= mon <= 12:
        return _blocked(
            "CONTRACT_MONTH_INVALID",
            contract_month=month,
            available_at=snapshot.received_at,
            source_snapshot_id=snapshot.source_snapshot_id,
        )

    date_raw = str(row.get("交易日期") or "").strip()
    try:
        trading_date = datetime.strptime(date_raw, "%Y/%m/%d").date()
    except ValueError:
        return _blocked(
            "TRADING_DATE_INVALID",
            contract_month=month,
            available_at=snapshot.received_at,
            source_snapshot_id=snapshot.source_snapshot_id,
        )

    settlement = _parse_price(row.get("結算價"))
    contract_code = f"TMF{month}"
    if settlement is None:
        return _blocked(
            "SETTLEMENT_INVALID",
            contract_code=contract_code,
            contract_month=month,
            trading_date=trading_date.isoformat(),
            available_at=snapshot.received_at,
            source_snapshot_id=snapshot.source_snapshot_id,
        )

    expiry = taifex_last_trading_date(year, mon)
    is_expiring = trading_date == expiry
    probe = datetime.combine(trading_date, time(10, 0), tzinfo=TAIPEI)
    session = resolve_venue_session(
        "TAIFEX_DERIVATIVES",
        probe,
        is_expiring_contract=is_expiring,
    )
    if (
        session.session_status != "REGULAR_SESSION"
        or session.trading_date != trading_date.isoformat()
        or session.session_close_timestamp is None
    ):
        return _blocked(
            "SESSION_TRUTH_MISMATCH",
            contract_code=contract_code,
            contract_month=month,
            trading_date=trading_date.isoformat(),
            available_at=snapshot.received_at,
            source_snapshot_id=snapshot.source_snapshot_id,
        )

    event_timestamp = session.session_close_timestamp.astimezone(timezone.utc)
    available_at = snapshot.received_at.astimezone(timezone.utc)
    if event_timestamp > available_at:
        return _blocked(
            "RECEIVED_BEFORE_SESSION_CLOSE",
            contract_code=contract_code,
            contract_month=month,
            trading_date=trading_date.isoformat(),
            available_at=available_at,
            source_snapshot_id=snapshot.source_snapshot_id,
        )
    if not snapshot.source_snapshot_id:
        return _blocked(
            "SOURCE_SNAPSHOT_ID_REQUIRED",
            contract_code=contract_code,
            contract_month=month,
            trading_date=trading_date.isoformat(),
            available_at=available_at,
        )

    return _Candidate(
        contract_code=contract_code,
        contract_month=month,
        trading_date=trading_date,
        settlement=settlement,
        event_timestamp=event_timestamp,
        available_at=available_at,
        source_snapshot_id=snapshot.source_snapshot_id,
        session=session,
        days_to_expiry=(expiry - trading_date).days,
    )


def _observation(candidate: _Candidate, snapshot: TaifexDailySnapshot) -> FactorRepresentationObservation:
    definition = definition_for("TW_INDEX", "TMF_FUTURES")
    if definition is None:
        raise RuntimeError("TMF_FUTURES definition missing")
    return FactorRepresentationObservation(
        economic_factor_id=definition.economic_factor_id,
        representation_id=definition.representation_id,
        instrument=definition.instrument,
        instrument_type=definition.instrument_type,
        representation_relation=definition.representation_relation,
        temporal_role="PREVIOUS_SESSION_REFERENCE",
        resolved_role="PREVIOUS_SESSION_REFERENCE",
        venue_id=definition.venue_id,
        calendar_id=definition.calendar_id,
        timezone="Asia/Taipei",
        session=candidate.session,
        value=candidate.settlement,
        event_timestamp=candidate.event_timestamp,
        available_at=candidate.available_at,
        provider_timestamp=None,
        received_at=candidate.available_at,
        timestamp_precision="BAR_CLOSE_TIMESTAMP",
        staleness_status="CLOSED_MARKET_REFERENCE",
        availability_status="AVAILABLE",
        quality_status="OFFICIAL_SETTLEMENT_RECEIPT_CAPTURED",
        provider="TAIFEX",
        source_type="TAIFEX_OFFICIAL_DAILY_SETTLEMENT_CSV",
        source_frequency="DAILY",
        source_schema_version=SCHEMA_VERSION,
        source_version="dlFutDataDown",
        source_snapshot_ids=[candidate.source_snapshot_id],
        data_grade="OFFICIAL_DAILY",
        point_in_time_safe=True,
        revision_status="SNAPSHOT_CAPTURED",
        contract_code=candidate.contract_code,
        contract_month=candidate.contract_month,
        roll_status="NONE",
        series_semantics="CONTRACT",
        days_to_expiry=candidate.days_to_expiry,
    )


def _existing_feature(
    store: FeatureStore,
    candidate: _Candidate,
) -> list[tuple[str, float]]:
    if not store.db_path.exists():
        return []
    event = candidate.event_timestamp.astimezone(timezone.utc).replace(tzinfo=None)
    with store._conn() as con:
        rows = con.execute(
            """SELECT lineage_id, value
               FROM features
               WHERE representation_id='TMF_FUTURES'
                 AND contract_code=?
                 AND feature_name=?
                 AND feature_version=?
                 AND event_time=?""",
            [
                candidate.contract_code,
                FEATURE_NAME,
                FEATURE_VERSION,
                event,
            ],
        ).fetchall()
    return [(str(lineage), float(value)) for lineage, value in rows]


def materialize_tmf_settlement_snapshot(
    snapshot: TaifexDailySnapshot,
    *,
    store: FeatureStore | None = None,
) -> dict[str, Any]:
    """Materialize exact-contract official TMF settlements with receipt-time availability."""
    if snapshot.received_at.tzinfo is None:
        raise ValueError("snapshot.received_at must be timezone-aware")
    if snapshot.commodity != "TMF":
        raise ValueError("P3-B materializer accepts TMF snapshots only")

    fs = store or FeatureStore()
    results: list[TaifexSettlementMaterializationResult] = []
    ignored_non_regular = 0
    ignored_non_exact_contract = 0
    ignored_invalid_settlement = 0

    for _, row in snapshot.frame.iterrows():
        if str(row.get("交易時段") or "").strip() != "一般":
            ignored_non_regular += 1
            continue
        contract_month = str(row.get("到期月份(週別)") or "").strip()
        if not re.fullmatch(r"20\d{4}", contract_month):
            ignored_non_exact_contract += 1
            continue
        if _parse_price(row.get("結算價")) is None:
            ignored_invalid_settlement += 1
            continue
        candidate = _candidate_from_row(snapshot, row)
        if candidate is None:
            ignored_non_regular += 1
            continue
        if isinstance(candidate, TaifexSettlementMaterializationResult):
            results.append(candidate)
            continue

        existing = _existing_feature(fs, candidate)
        if existing:
            if len(existing) == 1 and math.isclose(
                existing[0][1],
                candidate.settlement,
                rel_tol=0.0,
                abs_tol=1e-12,
            ):
                results.append(
                    TaifexSettlementMaterializationResult(
                        status=STATUS_ALREADY_MATERIALIZED,
                        contract_code=candidate.contract_code,
                        contract_month=candidate.contract_month,
                        trading_date=candidate.trading_date.isoformat(),
                        event_timestamp=candidate.event_timestamp,
                        available_at=candidate.available_at,
                        source_snapshot_id=candidate.source_snapshot_id,
                        lineage_id=existing[0][0],
                        values_exposed=False,
                    )
                )
            else:
                results.append(
                    _blocked(
                        "REVISION_OR_DUPLICATE_CONFLICT",
                        contract_code=candidate.contract_code,
                        contract_month=candidate.contract_month,
                        trading_date=candidate.trading_date.isoformat(),
                        available_at=candidate.available_at,
                        source_snapshot_id=candidate.source_snapshot_id,
                    )
                )
            continue

        obs = _observation(candidate, snapshot)
        lineage = lineage_from_observation(obs)
        stored = fs.put_observation(
            obs,
            as_of=candidate.available_at,
            materialize_feature=True,
            feature_name=FEATURE_NAME,
            feature_version=FEATURE_VERSION,
            materialization_mode="DERIVED_DAILY",
        )
        if stored["model_feature_status"] not in {"MATERIALIZED", "IDEMPOTENT_FEATURE"}:
            results.append(
                _blocked(
                    f"FEATURE_STORE_REJECTED:{stored['model_feature_status']}",
                    contract_code=candidate.contract_code,
                    contract_month=candidate.contract_month,
                    trading_date=candidate.trading_date.isoformat(),
                    available_at=candidate.available_at,
                    source_snapshot_id=candidate.source_snapshot_id,
                )
            )
            continue
        results.append(
            TaifexSettlementMaterializationResult(
                status=STATUS_MATERIALIZED,
                contract_code=candidate.contract_code,
                contract_month=candidate.contract_month,
                trading_date=candidate.trading_date.isoformat(),
                event_timestamp=candidate.event_timestamp,
                available_at=candidate.available_at,
                source_snapshot_id=candidate.source_snapshot_id,
                lineage_id=str(lineage.lineage_id),
                values_exposed=False,
            )
        )

    counts: dict[str, int] = {}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1
    contracts = sorted({r.contract_code for r in results if r.contract_code})
    return {
        "schema_version": SCHEMA_VERSION,
        "feature_name": FEATURE_NAME,
        "feature_version": FEATURE_VERSION,
        "source_snapshot_id": snapshot.source_snapshot_id,
        "received_at": snapshot.received_at.astimezone(timezone.utc).isoformat(),
        "query_start": snapshot.query_start,
        "query_end": snapshot.query_end,
        "commodity": snapshot.commodity,
        "ignored_non_regular_rows": ignored_non_regular,
        "ignored_non_exact_contract_rows": ignored_non_exact_contract,
        "ignored_invalid_settlement_rows": ignored_invalid_settlement,
        "counts": counts,
        "contracts": contracts,
        "results": [r.model_dump() for r in results],
        "retroactive_availability_used": False,
        "values_exposed": False,
    }
