"""W2 model-input contract for gated Feature Store observations.

This layer proves that persisted broker observations can reach a model-input
boundary without pretending that TICK data is daily bars.  Current production
forecast adapters are daily; incompatible frequencies must abstain.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from market_ai_hub.feature_store.store import FeatureStore, QUOTE_FEATURE_VERSION


@dataclass
class ModelInputBundle:
    status: str
    reason: str
    representation_id: str
    contract_code: str
    requested_frequency: str
    source_frequency: str
    feature_name: str
    feature_version: str
    information_cutoff: datetime
    row_count: int = 0
    lineage_ids: list[str] = field(default_factory=list)
    source_snapshot_ids: list[str] = field(default_factory=list)
    first_event_timestamp: datetime | None = None
    last_event_timestamp: datetime | None = None
    latest_available_at: datetime | None = None
    series: pd.Series | None = None

    def public_status(self) -> dict[str, Any]:
        """Metadata-only status; model values stay out of public readiness output."""
        return {
            "status": self.status,
            "reason": self.reason,
            "representation_id": self.representation_id,
            "contract_code": self.contract_code,
            "requested_frequency": self.requested_frequency,
            "source_frequency": self.source_frequency,
            "feature_name": self.feature_name,
            "feature_version": self.feature_version,
            "information_cutoff": _iso(self.information_cutoff),
            "row_count": self.row_count,
            "lineage_ids": list(self.lineage_ids),
            "source_snapshot_ids": list(self.source_snapshot_ids),
            "first_event_timestamp": _iso(self.first_event_timestamp),
            "last_event_timestamp": _iso(self.last_event_timestamp),
            "latest_available_at": _iso(self.latest_available_at),
            "values_exposed": False,
        }


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return _aware(value).isoformat() if value is not None else None


def _dt(value: Any) -> datetime:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    return ts.to_pydatetime()


def _empty(*, status: str, reason: str, representation_id: str,
           contract_code: str, requested_frequency: str,
           feature_name: str, feature_version: str,
           cutoff: datetime, source_frequency: str = "") -> ModelInputBundle:
    return ModelInputBundle(
        status=status,
        reason=reason,
        representation_id=representation_id,
        contract_code=contract_code,
        requested_frequency=requested_frequency,
        source_frequency=source_frequency,
        feature_name=feature_name,
        feature_version=feature_version,
        information_cutoff=_aware(cutoff),
    )


def build_model_input(
    representation_id: str,
    *,
    as_of: datetime,
    contract_code: str = "",
    requested_frequency: str = "1d",
    min_points: int = 20,
    feature_name: str = "quote_value",
    feature_version: str = QUOTE_FEATURE_VERSION,
    store: FeatureStore | None = None,
) -> ModelInputBundle:
    """Build a homogeneous, cutoff-safe input series from materialized features.

    The function is read-only: a missing/old Feature Store returns a typed status
    and is never created or migrated here.
    """
    store = store or FeatureStore()
    cutoff = _aware(as_of)
    rep = str(representation_id or "").strip()
    contract = str(contract_code or "").strip()
    requested = str(requested_frequency or "").strip().upper()
    if not rep:
        return _empty(
            status="INVALID_REQUEST", reason="representation_id required",
            representation_id=rep, contract_code=contract,
            requested_frequency=requested, feature_name=feature_name,
            feature_version=feature_version, cutoff=cutoff,
        )
    if min_points < 1:
        return _empty(
            status="INVALID_REQUEST", reason="min_points must be positive",
            representation_id=rep, contract_code=contract,
            requested_frequency=requested, feature_name=feature_name,
            feature_version=feature_version, cutoff=cutoff,
        )
    if not store.db_path.exists():
        return _empty(
            status="NO_FEATURE_STORE", reason="Feature Store database not present",
            representation_id=rep, contract_code=contract,
            requested_frequency=requested, feature_name=feature_name,
            feature_version=feature_version, cutoff=cutoff,
        )

    cutoff_db = pd.Timestamp(cutoff).tz_convert("UTC").tz_localize(None).to_pydatetime()
    try:
        con = duckdb.connect(str(store.db_path), read_only=True)
    except Exception:
        return _empty(
            status="STORE_UNREADABLE", reason="Feature Store cannot be opened read-only",
            representation_id=rep, contract_code=contract,
            requested_frequency=requested, feature_name=feature_name,
            feature_version=feature_version, cutoff=cutoff,
        )
    try:
        tables = {r[0] for r in con.execute(
            "SELECT table_name FROM information_schema.tables"
        ).fetchall()}
        if not {"features", "factor_observations"} <= tables:
            return _empty(
                status="SCHEMA_NOT_READY",
                reason="Feature Store lacks W2 features/factor_observations tables",
                representation_id=rep, contract_code=contract,
                requested_frequency=requested, feature_name=feature_name,
                feature_version=feature_version, cutoff=cutoff,
            )
        q = """
            SELECT
                f.event_time, f.available_at, f.value, f.lineage_id,
                f.contract_code, f.representation_id, f.source_snapshot_ids_json,
                o.source_frequency, o.model_feature_gate_at_ingest
            FROM features f
            JOIN factor_observations o ON o.lineage_id = f.lineage_id
            WHERE f.representation_id=?
              AND f.feature_name=?
              AND f.feature_version=?
              AND f.available_at <= ?
              AND f.point_in_time_safe=TRUE
              AND f.availability_status='AVAILABLE'
              AND o.model_feature_gate_at_ingest='ELIGIBLE'
        """
        params: list[Any] = [rep, feature_name, feature_version, cutoff_db]
        if contract:
            q += " AND f.contract_code=?"
            params.append(contract)
        q += " ORDER BY f.event_time, f.available_at, f.lineage_id"
        frame = con.execute(q, params).df()
    finally:
        con.close()

    if frame.empty:
        return _empty(
            status="NO_ELIGIBLE_ROWS",
            reason="no gated model features at or before cutoff",
            representation_id=rep, contract_code=contract,
            requested_frequency=requested, feature_name=feature_name,
            feature_version=feature_version, cutoff=cutoff,
        )

    contracts = sorted({str(x) for x in frame["contract_code"].dropna() if str(x)})
    if not contract and len(contracts) > 1:
        return _empty(
            status="MIXED_CONTRACTS",
            reason="contract_code required because multiple contracts are present",
            representation_id=rep, contract_code="",
            requested_frequency=requested, feature_name=feature_name,
            feature_version=feature_version, cutoff=cutoff,
        )
    resolved_contract = contract or (contracts[0] if contracts else "")

    freqs = sorted({str(x).upper() for x in frame["source_frequency"].dropna() if str(x)})
    if len(freqs) != 1:
        return _empty(
            status="MIXED_OR_UNKNOWN_FREQUENCY",
            reason="eligible rows do not have one source frequency",
            representation_id=rep, contract_code=resolved_contract,
            requested_frequency=requested, feature_name=feature_name,
            feature_version=feature_version, cutoff=cutoff,
            source_frequency=",".join(freqs),
        )
    source_frequency = freqs[0]
    if source_frequency != requested:
        return _empty(
            status="INCOMPATIBLE_FREQUENCY",
            reason=f"source_frequency={source_frequency} cannot satisfy requested_frequency={requested}",
            representation_id=rep, contract_code=resolved_contract,
            requested_frequency=requested, feature_name=feature_name,
            feature_version=feature_version, cutoff=cutoff,
            source_frequency=source_frequency,
        )

    events = pd.to_datetime(frame["event_time"], utc=True)
    if events.duplicated().any():
        return _empty(
            status="DUPLICATE_EVENT_TIME",
            reason="multiple gated values share one event timestamp",
            representation_id=rep, contract_code=resolved_contract,
            requested_frequency=requested, feature_name=feature_name,
            feature_version=feature_version, cutoff=cutoff,
            source_frequency=source_frequency,
        )
    if len(frame) < min_points:
        return ModelInputBundle(
            status="INSUFFICIENT_HISTORY",
            reason=f"need at least {min_points} points; found {len(frame)}",
            representation_id=rep,
            contract_code=resolved_contract,
            requested_frequency=requested,
            source_frequency=source_frequency,
            feature_name=feature_name,
            feature_version=feature_version,
            information_cutoff=cutoff,
            row_count=int(len(frame)),
            lineage_ids=[str(x) for x in frame["lineage_id"]],
            source_snapshot_ids=_snapshot_ids(frame),
            first_event_timestamp=_dt(events.iloc[0]),
            last_event_timestamp=_dt(events.iloc[-1]),
            latest_available_at=_dt(pd.to_datetime(frame["available_at"], utc=True).max()),
        )

    series = pd.Series(
        frame["value"].astype(float).to_numpy(),
        index=pd.DatetimeIndex(events),
        name=f"{rep}:{resolved_contract or 'UNSPECIFIED'}",
    )
    return ModelInputBundle(
        status="READY",
        reason="gated homogeneous Feature Store input",
        representation_id=rep,
        contract_code=resolved_contract,
        requested_frequency=requested,
        source_frequency=source_frequency,
        feature_name=feature_name,
        feature_version=feature_version,
        information_cutoff=cutoff,
        row_count=int(len(frame)),
        lineage_ids=[str(x) for x in frame["lineage_id"]],
        source_snapshot_ids=_snapshot_ids(frame),
        first_event_timestamp=_dt(events.iloc[0]),
        last_event_timestamp=_dt(events.iloc[-1]),
        latest_available_at=_dt(pd.to_datetime(frame["available_at"], utc=True).max()),
        series=series,
    )


def _snapshot_ids(frame: pd.DataFrame) -> list[str]:
    import json

    out: set[str] = set()
    for raw in frame["source_snapshot_ids_json"]:
        try:
            values = json.loads(str(raw or "[]"))
        except Exception:
            continue
        if isinstance(values, list):
            out.update(str(x) for x in values if str(x))
    return sorted(out)
