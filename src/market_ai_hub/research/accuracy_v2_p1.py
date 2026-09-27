"""Accuracy v2 P1 prediction contract and one-factor PIT packet.

This module is deliberately narrow.  It does not train or score models.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import json
import math
from typing import Any
from zoneinfo import ZoneInfo

import duckdb
import pandas as pd

from market_ai_hub.feature_store.store import FeatureStore
from market_ai_hub.services.calendar import (
    next_ose_derivatives_session,
    next_trading_sessions,
)

JST = ZoneInfo("Asia/Tokyo")
TARGET_NEXT_OSE_SETTLEMENT = "NEXT_OSE_SESSION_SETTLEMENT"
TARGET_NEXT_PUBLISHED_SETTLEMENT = "NEXT_PUBLISHED_SETTLEMENT_OBSERVATION"
PROTOCOL_VERSION = "accuracy-v2-p1-20260927"


class PredictionContractError(ValueError):
    """A forecast origin/target contract is temporally or semantically invalid."""


@dataclass(frozen=True)
class PredictionContract:
    decision_time: datetime
    reference_price: float
    reference_price_available_at: datetime
    target_start: datetime
    target_end: datetime
    target_measure: str
    exact_contract: str
    forecast_horizon: str
    label_available_at: datetime | None
    full_interval: bool = True

    def __post_init__(self) -> None:
        d = _aware(self.decision_time)
        r = _aware(self.reference_price_available_at)
        start = _aware(self.target_start)
        end = _aware(self.target_end)
        label = _aware(self.label_available_at) if self.label_available_at else None
        if not math.isfinite(float(self.reference_price)):
            raise PredictionContractError("reference_price must be finite")
        if not self.exact_contract:
            raise PredictionContractError("exact_contract is required")
        if r > d:
            raise PredictionContractError("reference_price available after decision_time")
        if d >= end:
            raise PredictionContractError("decision_time must be before target_end")
        if start >= end:
            raise PredictionContractError("target_start must be before target_end")
        if self.full_interval and d > start:
            raise PredictionContractError(
                "full-interval forecast cannot start after target_start; define a nowcast instead"
            )
        if label is not None and label < end:
            raise PredictionContractError("label_available_at cannot precede target_end")
        if self.target_measure not in {
            TARGET_NEXT_OSE_SETTLEMENT,
            TARGET_NEXT_PUBLISHED_SETTLEMENT,
        }:
            raise PredictionContractError(f"unsupported target_measure={self.target_measure}")

    def canonical(self) -> dict[str, Any]:
        raw = asdict(self)
        for key in (
            "decision_time", "reference_price_available_at", "target_start",
            "target_end", "label_available_at",
        ):
            value = raw[key]
            raw[key] = _aware(value).isoformat() if value is not None else None
        return raw


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise PredictionContractError("timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


def _jst_at(d: str | date, hh: int, mm: int = 0) -> datetime:
    day = pd.Timestamp(d).date()
    return datetime.combine(day, time(hh, mm), tzinfo=JST)


def jpx_report_publication_for_session(session_date: str | date) -> datetime:
    """Conservative planned availability: next XTKS business day 09:00 JST.

    OSE holiday sessions therefore converge on the next cash-business publication
    date instead of pretending the holiday-session settlement was public at close.
    """
    publication_dates = next_trading_sessions("^N225", session_date, 1)
    if not publication_dates:
        raise PredictionContractError("JPX publication calendar not available")
    return _jst_at(publication_dates[0], 9, 0)


def make_jnu_contract(
    *,
    decision_time: datetime,
    reference_price: float,
    reference_price_available_at: datetime,
    exact_contract: str,
    target_measure: str = TARGET_NEXT_OSE_SETTLEMENT,
) -> PredictionContract:
    decision = _aware(decision_time)
    local_date = decision.astimezone(JST).date()
    session_date = next_ose_derivatives_session(local_date)
    if session_date is None:
        raise PredictionContractError("next OSE session unavailable")
    settlement_time = _jst_at(session_date, 15, 45)
    publication_time = jpx_report_publication_for_session(session_date)

    if target_measure == TARGET_NEXT_OSE_SETTLEMENT:
        start = _jst_at(session_date, 8, 45)
        end = settlement_time
        horizon = "NEXT_OSE_SESSION"
        label_available = publication_time
    elif target_measure == TARGET_NEXT_PUBLISHED_SETTLEMENT:
        start = publication_time
        end = publication_time + timedelta(seconds=1)
        horizon = "NEXT_PUBLISHED_OBSERVATION"
        label_available = end
    else:
        raise PredictionContractError(f"unsupported target_measure={target_measure}")

    return PredictionContract(
        decision_time=decision,
        reference_price=reference_price,
        reference_price_available_at=reference_price_available_at,
        target_start=start,
        target_end=end,
        target_measure=target_measure,
        exact_contract=exact_contract,
        forecast_horizon=horizon,
        label_available_at=label_available,
    )


def cache_identity(
    *,
    contract: PredictionContract,
    source_identity: dict[str, Any],
    feature_identity: dict[str, Any],
    model_revisions: dict[str, str] | None = None,
    protocol_version: str = PROTOCOL_VERSION,
) -> str:
    payload = {
        "contract": contract.canonical(),
        "source": source_identity,
        "feature": feature_identity,
        "models": dict(sorted((model_revisions or {}).items())),
        "protocol_version": protocol_version,
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _decode_ids(value: Any) -> list[str]:
    try:
        parsed = json.loads(str(value or "[]"))
    except Exception:
        return []
    return sorted({str(x) for x in parsed if str(x)}) if isinstance(parsed, list) else []


def _dt(value: Any) -> datetime:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    return ts.to_pydatetime()


def build_pit_lagged_return_packet(
    *,
    contract: PredictionContract,
    representation_id: str,
    factor_contract: str,
    feature_name: str = "quote_value",
    feature_version: str,
    expected_relation: str = "DERIVATIVE_PROXY",
    max_age_seconds: float = 172800.0,
    max_event_gap_seconds: float = 345600.0,
    model_revisions: dict[str, str] | None = None,
    protocol_version: str = PROTOCOL_VERSION,
    evidence_origin: str = "REAL",
    store: FeatureStore | None = None,
) -> dict[str, Any]:
    """Build exactly one lagged-return factor with strict backward as-of semantics."""
    store = store or FeatureStore()
    decision = _aware(contract.decision_time)
    base = {
        "engineering_status": "PASS",
        "data_status": "DATA_NOT_READY",
        "factor": "lagged_return",
        "representation_id": representation_id,
        "factor_contract": factor_contract,
        "feature_name": feature_name,
        "feature_version": feature_version,
        "decision_time": decision.isoformat(),
        "features": {},
        "rejection_reason": None,
        "protocol_version": protocol_version,
    }
    if not store.db_path.exists():
        base["rejection_reason"] = "NO_FEATURE_STORE"
        return base

    cutoff = decision.replace(tzinfo=None)
    con = duckdb.connect(str(store.db_path), read_only=True)
    try:
        tables = {r[0] for r in con.execute(
            "SELECT table_name FROM information_schema.tables"
        ).fetchall()}
        if not {"features", "factor_observations"} <= tables:
            base["rejection_reason"] = "SCHEMA_NOT_READY"
            return base
        frame = con.execute(
            """
            SELECT f.event_time, f.available_at, f.value, f.lineage_id,
                   f.source_snapshot_ids_json, f.contract_code, f.data_grade,
                   o.received_at, o.provider_timestamp, o.provider, o.source_type,
                   o.source_frequency, o.venue_id, o.session_status,
                   o.representation_relation, o.instrument_type, o.roll_status,
                   o.series_semantics, o.staleness_status, o.availability_status,
                   o.point_in_time_safe, o.model_feature_gate_at_ingest
            FROM features f
            JOIN factor_observations o ON o.lineage_id=f.lineage_id
            WHERE f.representation_id=?
              AND f.feature_name=?
              AND f.feature_version=?
              AND f.contract_code=?
              AND f.available_at <= ?
            ORDER BY f.event_time, f.available_at, f.lineage_id
            """,
            [representation_id, feature_name, feature_version, factor_contract, cutoff],
        ).df()
    finally:
        con.close()

    if frame.empty:
        base["rejection_reason"] = "NO_QUALIFIED_HISTORY"
        return base

    checks = [
        ("DUPLICATE_EVENT_TIME", pd.to_datetime(frame["event_time"], utc=True).duplicated().any()),
        ("NONFINITE_VALUE", any(not math.isfinite(float(v)) for v in frame["value"])),
        ("FUTURE_AVAILABLE_AT", any(_dt(v) > decision for v in frame["available_at"])),
        ("NOT_AVAILABLE", any(str(v) != "AVAILABLE" for v in frame["availability_status"])),
        ("NOT_PIT_SAFE", any(not bool(v) for v in frame["point_in_time_safe"])),
        ("STALE", any(str(v) != "FRESH" for v in frame["staleness_status"])),
        ("RELATION_MISMATCH", any(str(v) != expected_relation for v in frame["representation_relation"])),
        ("ROLL_MISMATCH", any(str(v) != "NONE" for v in frame["roll_status"])),
        ("SERIES_SEMANTICS_MISMATCH", any(str(v) != "CONTRACT" for v in frame["series_semantics"])),
        ("CONTRACT_MISMATCH", any(str(v) != factor_contract for v in frame["contract_code"])),
        ("GATE_REJECTED", any(str(v) not in {"ELIGIBLE", "ELIGIBLE_DERIVED_DAILY"} for v in frame["model_feature_gate_at_ingest"])),
    ]
    for reason, failed in checks:
        if failed:
            base["rejection_reason"] = reason
            return base

    if len(frame) < 2:
        base["rejection_reason"] = "INSUFFICIENT_HISTORY"
        return base

    tail = frame.iloc[-2:].copy()
    event_times = [_dt(x) for x in tail["event_time"]]
    if (event_times[1] - event_times[0]).total_seconds() > max_event_gap_seconds:
        base["rejection_reason"] = "MISSING_BAR_GAP"
        return base
    snapshots = sorted({
        sid for raw in tail["source_snapshot_ids_json"] for sid in _decode_ids(raw)
    })
    if not snapshots:
        base["rejection_reason"] = "SOURCE_SNAPSHOT_MISSING"
        return base

    latest_available = max(_dt(v) for v in tail["available_at"])
    age_seconds = (decision - latest_available).total_seconds()
    if age_seconds < 0:
        base["rejection_reason"] = "FUTURE_AVAILABLE_AT"
        return base
    if age_seconds > max_age_seconds:
        base["rejection_reason"] = "STALE_BY_DECISION_TIME"
        return base

    prior, latest = float(tail.iloc[0]["value"]), float(tail.iloc[1]["value"])
    if prior == 0.0:
        base["rejection_reason"] = "ZERO_DENOMINATOR"
        return base
    lagged_return = latest / prior - 1.0
    if not math.isfinite(lagged_return):
        base["rejection_reason"] = "NONFINITE_FEATURE"
        return base

    source_identity = {
        "lineage_ids": [str(x) for x in tail["lineage_id"]],
        "source_snapshot_ids": snapshots,
        "event_time": [_dt(x).isoformat() for x in tail["event_time"]],
        "available_at": [_dt(x).isoformat() for x in tail["available_at"]],
        "received_at": [_dt(x).isoformat() if not pd.isna(x) else None for x in tail["received_at"]],
        "provider_timestamp": [_dt(x).isoformat() if not pd.isna(x) else None for x in tail["provider_timestamp"]],
        "provider": sorted({str(x) for x in tail["provider"]}),
        "source_type": sorted({str(x) for x in tail["source_type"]}),
        "source_frequency": sorted({str(x) for x in tail["source_frequency"]}),
        "venue_id": sorted({str(x) for x in tail["venue_id"]}),
        "session_status": sorted({str(x) for x in tail["session_status"]}),
        "representation_relation": expected_relation,
        "exact_contract": factor_contract,
        "age_seconds": age_seconds,
        "value_content_hash": hashlib.sha256(
            json.dumps([float(x) for x in tail["value"]], separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:24],
    }
    source_identity["source_hash"] = hashlib.sha256(
        json.dumps(source_identity, sort_keys=True).encode("utf-8")
    ).hexdigest()[:24]
    feature_identity = {
        "feature_name": feature_name,
        "feature_version": feature_version,
        "formula": "latest_value/prior_value-1",
    }
    base.update({
        "data_status": "DATA_READY" if evidence_origin.upper() == "REAL" else "DATA_NOT_READY",
        "evidence_origin": evidence_origin.upper(),
        "features": {"factor_lagged_return": lagged_return},
        "feature_available_at": latest_available.isoformat(),
        "source_identity": source_identity,
        "cache_identity": cache_identity(
            contract=contract,
            source_identity=source_identity,
            feature_identity=feature_identity,
            model_revisions=model_revisions,
            protocol_version=protocol_version,
        ),
    })
    if evidence_origin.upper() != "REAL":
        base["rejection_reason"] = "SYNTHETIC_ENGINEERING_ONLY"
    return base
