"""Versioned Feature Store + V2-A.2 factor-observation snapshots.

The legacy Phase-2C feature table is preserved.  W2 adds immutable V2-A.2
observation snapshots and provenance columns without inventing exchange time.

Model-ready quote features are materialized only when the V2-A.2 observation is
actually LIVE-eligible at ingestion time.  Receipt-only / stale / unknown-time
records remain queryable as provenance snapshots but never become live features.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd
from pydantic import BaseModel, Field

from market_ai_hub.config.runtime_paths import feature_store_root

SCHEMA_VERSION = 2
QUOTE_FEATURE_VERSION = "v2a2-quote-1"


class FeatureStoreError(ValueError):
    """Typed fail-closed Feature Store rejection."""


class FeatureRecord(BaseModel):
    feature_name: str
    symbol: str
    event_time: datetime
    available_at: datetime
    feature_version: str
    source: str
    data_grade: str
    value: float

    # W2 provenance.  Empty defaults preserve existing Phase-2C callers.
    lineage_id: str = ""
    economic_factor_id: str = ""
    representation_id: str = ""
    venue_id: str = ""
    session_status: str = ""
    trading_date: str = ""
    timestamp_precision: str = "UNKNOWN"
    availability_status: str = "UNKNOWN"
    quality_status: str = "UNKNOWN"
    resolved_role: str = ""
    point_in_time_safe: bool = False
    contract_code: str = ""
    contract_month: str = ""
    roll_status: str = ""
    series_semantics: str = ""
    source_snapshot_ids: list[str] = Field(default_factory=list)

    @classmethod
    def _aware(cls, v: datetime) -> datetime:
        return v if v.tzinfo is not None else v.replace(tzinfo=timezone.utc)

    def model_post_init(self, __context) -> None:
        self.event_time = self._aware(self.event_time)
        self.available_at = self._aware(self.available_at)
        self.source_snapshot_ids = sorted({str(x) for x in self.source_snapshot_ids if str(x)})


FEATURE_DB_COLUMNS = [
    "feature_name", "symbol", "event_time", "available_at", "feature_version",
    "source", "data_grade", "value", "lineage_id", "economic_factor_id",
    "representation_id", "venue_id", "session_status", "trading_date",
    "timestamp_precision", "availability_status", "quality_status", "resolved_role",
    "point_in_time_safe", "contract_code", "contract_month", "roll_status",
    "series_semantics", "source_snapshot_ids_json",
]


def _utc_naive(dt) -> datetime:
    """Normalize to naive UTC for DuckDB TIMESTAMP."""
    t = pd.Timestamp(dt)
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    else:
        t = t.tz_convert("UTC")
    return t.tz_localize(None).to_pydatetime()


def _utc_naive_or_none(dt) -> datetime | None:
    return None if dt is None else _utc_naive(dt)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _json_ids(ids: list[str] | None) -> str:
    return json.dumps(sorted({str(x) for x in (ids or []) if str(x)}), separators=(",", ":"))


def _decode_ids(raw: Any) -> list[str]:
    if raw in (None, ""):
        return []
    try:
        out = json.loads(str(raw))
    except Exception:
        return []
    return [str(x) for x in out] if isinstance(out, list) else []


def _model_feature_gate(obs: Any, as_of: datetime) -> str:
    """Return ELIGIBLE or a stable fail-closed reason for live model features."""
    cutoff = _aware(as_of)
    value = getattr(obs, "value", None)
    try:
        fv = float(value)
    except Exception:
        return "BLOCKED_INVALID_VALUE"
    if not math.isfinite(fv):
        return "BLOCKED_INVALID_VALUE"
    if getattr(obs, "availability_status", "") != "AVAILABLE":
        return "BLOCKED_NOT_AVAILABLE"
    available_at = getattr(obs, "available_at", None)
    event_timestamp = getattr(obs, "event_timestamp", None)
    if available_at is None:
        return "BLOCKED_AVAILABLE_AT_UNKNOWN"
    if _aware(available_at) > cutoff:
        return "BLOCKED_FUTURE_AVAILABLE_AT"
    if event_timestamp is None:
        return "BLOCKED_EVENT_TIME_UNKNOWN"
    if _aware(event_timestamp) > _aware(available_at):
        return "BLOCKED_EVENT_AFTER_AVAILABLE"
    if getattr(obs, "timestamp_precision", "") not in ("TICK_TIMESTAMP", "INTRADAY_TIMESTAMP"):
        return "BLOCKED_TIMESTAMP_PRECISION"
    if getattr(obs, "staleness_status", "") != "FRESH":
        return "BLOCKED_NOT_FRESH"
    if getattr(obs, "resolved_role", "") not in ("DIRECT_LIVE", "LIVE_DERIVATIVE_PROXY", "LIVE_SPOT_PROXY"):
        return "BLOCKED_NOT_LIVE_ROLE"
    if not bool(getattr(obs, "point_in_time_safe", False)):
        return "BLOCKED_POINT_IN_TIME_UNSAFE"
    if "LEGACY_TOP_LEVEL_RECEIPT_ONLY" in str(getattr(obs, "quality_status", "")):
        return "BLOCKED_LEGACY_RECEIPT_ONLY"
    if getattr(obs, "instrument_type", "") == "FUTURE":
        if getattr(obs, "series_semantics", "") != "CONTRACT":
            return "BLOCKED_FUTURE_SERIES_SEMANTICS"
        if getattr(obs, "roll_status", "") != "NONE":
            return "BLOCKED_FUTURE_ROLL"
        if not getattr(obs, "contract_code", ""):
            return "BLOCKED_CONTRACT_UNKNOWN"
    return "ELIGIBLE"


class FeatureStore:
    def __init__(self, root: Path | None = None) -> None:
        # Explicit root preserves the old test/API meaning (<root>/data/feature_store).
        # Runtime default uses the canonical MARKET_AI_DATA_ROOT resolver.
        self.dir = (Path(root) / "data" / "feature_store") if root is not None else feature_store_root()
        self.db_path = self.dir / "features.duckdb"

    def _conn(self) -> duckdb.DuckDBPyConnection:
        return duckdb.connect(str(self.db_path))

    def init(self) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        with self._conn() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS features (
                    feature_name VARCHAR, symbol VARCHAR, event_time TIMESTAMP,
                    available_at TIMESTAMP, feature_version VARCHAR, source VARCHAR,
                    data_grade VARCHAR, value DOUBLE,
                    lineage_id VARCHAR DEFAULT '', economic_factor_id VARCHAR DEFAULT '',
                    representation_id VARCHAR DEFAULT '', venue_id VARCHAR DEFAULT '',
                    session_status VARCHAR DEFAULT '', trading_date VARCHAR DEFAULT '',
                    timestamp_precision VARCHAR DEFAULT 'UNKNOWN',
                    availability_status VARCHAR DEFAULT 'UNKNOWN',
                    quality_status VARCHAR DEFAULT 'UNKNOWN', resolved_role VARCHAR DEFAULT '',
                    point_in_time_safe BOOLEAN DEFAULT FALSE, contract_code VARCHAR DEFAULT '',
                    contract_month VARCHAR DEFAULT '', roll_status VARCHAR DEFAULT '',
                    series_semantics VARCHAR DEFAULT '', source_snapshot_ids_json VARCHAR DEFAULT '[]'
                )
                """
            )
            # Non-destructive migration for existing Phase-2C databases.
            migrations = [
                ("lineage_id", "VARCHAR DEFAULT ''"),
                ("economic_factor_id", "VARCHAR DEFAULT ''"),
                ("representation_id", "VARCHAR DEFAULT ''"),
                ("venue_id", "VARCHAR DEFAULT ''"),
                ("session_status", "VARCHAR DEFAULT ''"),
                ("trading_date", "VARCHAR DEFAULT ''"),
                ("timestamp_precision", "VARCHAR DEFAULT 'UNKNOWN'"),
                ("availability_status", "VARCHAR DEFAULT 'UNKNOWN'"),
                ("quality_status", "VARCHAR DEFAULT 'UNKNOWN'"),
                ("resolved_role", "VARCHAR DEFAULT ''"),
                ("point_in_time_safe", "BOOLEAN DEFAULT FALSE"),
                ("contract_code", "VARCHAR DEFAULT ''"),
                ("contract_month", "VARCHAR DEFAULT ''"),
                ("roll_status", "VARCHAR DEFAULT ''"),
                ("series_semantics", "VARCHAR DEFAULT ''"),
                ("source_snapshot_ids_json", "VARCHAR DEFAULT '[]'"),
            ]
            for name, typ in migrations:
                con.execute(f"ALTER TABLE features ADD COLUMN IF NOT EXISTS {name} {typ}")
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS factor_observations (
                    lineage_id VARCHAR PRIMARY KEY,
                    economic_factor_id VARCHAR, representation_id VARCHAR,
                    instrument_type VARCHAR, representation_relation VARCHAR,
                    temporal_role VARCHAR, resolved_role VARCHAR,
                    venue_id VARCHAR, calendar_id VARCHAR,
                    session_status VARCHAR, trading_date VARCHAR,
                    value DOUBLE, event_timestamp TIMESTAMP, available_at TIMESTAMP,
                    provider_timestamp TIMESTAMP, received_at TIMESTAMP,
                    timestamp_precision VARCHAR, staleness_status VARCHAR,
                    availability_status VARCHAR, quality_status VARCHAR,
                    provider VARCHAR, source_type VARCHAR, source_frequency VARCHAR,
                    data_grade VARCHAR, point_in_time_safe BOOLEAN,
                    contract_code VARCHAR, contract_month VARCHAR,
                    roll_status VARCHAR, series_semantics VARCHAR,
                    source_snapshot_ids_json VARCHAR,
                    model_feature_gate_at_ingest VARCHAR,
                    payload_json VARCHAR NOT NULL
                )
                """
            )
            con.execute(
                "CREATE TABLE IF NOT EXISTS schema_meta (key VARCHAR PRIMARY KEY, value VARCHAR)"
            )
            con.execute("DELETE FROM schema_meta WHERE key='schema_version'")
            con.execute("INSERT INTO schema_meta VALUES ('schema_version', ?)", [str(SCHEMA_VERSION)])

    def put(self, rec: FeatureRecord) -> None:
        self.init()
        d = rec.model_dump()
        values = []
        for c in FEATURE_DB_COLUMNS:
            if c == "source_snapshot_ids_json":
                v = _json_ids(rec.source_snapshot_ids)
            else:
                v = d[c]
            if c in ("event_time", "available_at"):
                v = _utc_naive(v)
            values.append(v)
        with self._conn() as con:
            con.execute(
                f"INSERT INTO features ({','.join(FEATURE_DB_COLUMNS)}) "
                f"VALUES ({','.join(['?'] * len(FEATURE_DB_COLUMNS))})",
                values,
            )

    def put_observation(self, obs: Any, *, as_of: datetime,
                        materialize_feature: bool = True,
                        feature_name: str = "quote_value",
                        feature_version: str = QUOTE_FEATURE_VERSION) -> dict:
        """Persist immutable V2-A.2 provenance and optionally a gated model feature."""
        from market_ai_hub.research.v2.prediction_audit import (
            canonical_json,
            lineage_from_observation,
            lineage_payload,
        )

        cutoff = _aware(as_of)
        available_at = getattr(obs, "available_at", None)
        if available_at is None:
            raise FeatureStoreError("BLOCKED_AVAILABLE_AT_UNKNOWN")
        if _aware(available_at) > cutoff:
            raise FeatureStoreError("BLOCKED_FUTURE_AVAILABLE_AT")
        value = getattr(obs, "value", None)
        try:
            fvalue = float(value)
        except Exception as exc:
            raise FeatureStoreError("BLOCKED_INVALID_VALUE") from exc
        if not math.isfinite(fvalue):
            raise FeatureStoreError("BLOCKED_INVALID_VALUE")

        lineage = lineage_from_observation(obs)
        payload_json = canonical_json(lineage_payload(lineage))
        gate = _model_feature_gate(obs, cutoff)
        session = getattr(obs, "session", None)
        source_ids_json = _json_ids(getattr(obs, "source_snapshot_ids", []))

        self.init()
        with self._conn() as con:
            existing = con.execute(
                "SELECT value, payload_json FROM factor_observations WHERE lineage_id=?",
                [lineage.lineage_id],
            ).fetchone()
            if existing is not None:
                if float(existing[0]) != fvalue or str(existing[1]) != payload_json:
                    raise FeatureStoreError("BLOCKED_LINEAGE_ID_COLLISION")
                snapshot_status = "IDEMPOTENT"
            else:
                con.execute(
                    """
                    INSERT INTO factor_observations VALUES
                    (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    [
                        lineage.lineage_id, lineage.economic_factor_id, lineage.representation_id,
                        lineage.instrument_type, lineage.representation_relation,
                        lineage.temporal_role, lineage.resolved_role, lineage.venue_id,
                        lineage.calendar_id, lineage.session_status, lineage.trading_date,
                        fvalue, _utc_naive_or_none(lineage.event_timestamp),
                        _utc_naive_or_none(lineage.available_at),
                        _utc_naive_or_none(lineage.provider_timestamp),
                        _utc_naive_or_none(lineage.received_at), lineage.timestamp_precision,
                        lineage.staleness_status, lineage.availability_status,
                        lineage.quality_status, lineage.provider, lineage.source_type,
                        lineage.source_frequency, lineage.data_grade,
                        bool(lineage.point_in_time_safe), lineage.contract_code,
                        lineage.contract_month, lineage.roll_status, lineage.series_semantics,
                        source_ids_json, gate, payload_json,
                    ],
                )
                snapshot_status = "STORED"

        feature_status = gate
        if materialize_feature and gate == "ELIGIBLE":
            symbol = (getattr(obs, "contract_code", "") or getattr(obs, "instrument", "")
                      or getattr(obs, "representation_id", ""))
            with self._conn() as con:
                already = con.execute(
                    """SELECT COUNT(*) FROM features
                       WHERE lineage_id=? AND feature_name=? AND feature_version=?""",
                    [lineage.lineage_id, feature_name, feature_version],
                ).fetchone()[0]
            if already:
                feature_status = "IDEMPOTENT_FEATURE"
            else:
                self.put(FeatureRecord(
                    feature_name=feature_name,
                    symbol=symbol,
                    event_time=getattr(obs, "event_timestamp"),
                    available_at=getattr(obs, "available_at"),
                    feature_version=feature_version,
                    source=f"{getattr(obs, 'provider', '')}:{getattr(obs, 'source_type', '')}",
                    data_grade=getattr(obs, "data_grade", ""),
                    value=fvalue,
                    lineage_id=lineage.lineage_id,
                    economic_factor_id=getattr(obs, "economic_factor_id", ""),
                    representation_id=getattr(obs, "representation_id", ""),
                    venue_id=getattr(obs, "venue_id", ""),
                    session_status=getattr(session, "session_status", "") if session is not None else "",
                    trading_date=getattr(session, "trading_date", "") if session is not None else "",
                    timestamp_precision=getattr(obs, "timestamp_precision", "UNKNOWN"),
                    availability_status=getattr(obs, "availability_status", "UNKNOWN"),
                    quality_status=getattr(obs, "quality_status", "UNKNOWN"),
                    resolved_role=getattr(obs, "resolved_role", ""),
                    point_in_time_safe=bool(getattr(obs, "point_in_time_safe", False)),
                    contract_code=getattr(obs, "contract_code", ""),
                    contract_month=getattr(obs, "contract_month", ""),
                    roll_status=getattr(obs, "roll_status", ""),
                    series_semantics=getattr(obs, "series_semantics", ""),
                    source_snapshot_ids=list(getattr(obs, "source_snapshot_ids", []) or []),
                ))
                feature_status = "MATERIALIZED"

        return {
            "lineage_id": lineage.lineage_id,
            "snapshot_status": snapshot_status,
            "model_feature_status": feature_status,
            "feature_version": feature_version if feature_status in ("MATERIALIZED", "IDEMPOTENT_FEATURE") else "",
        }

    def latest_observations(self, *, as_of: datetime,
                            representation_ids: list[str] | None = None,
                            limit: int = 20) -> list[dict]:
        """Read-only provenance query. Missing/old stores return [] without migration."""
        if not self.db_path.exists():
            return []
        cutoff = _utc_naive(as_of)
        with self._conn() as con:
            has_table = con.execute(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_name='factor_observations'"
            ).fetchone()[0]
            if not has_table:
                return []
            q = "SELECT * FROM factor_observations WHERE available_at <= ?"
            params: list[Any] = [cutoff]
            reps = [str(x) for x in (representation_ids or []) if str(x)]
            if reps:
                q += f" AND representation_id IN ({','.join(['?'] * len(reps))})"
                params.extend(reps)
            q += " ORDER BY available_at DESC, received_at DESC LIMIT ?"
            params.append(max(1, int(limit)))
            df = con.execute(q, params).df()
        out: list[dict] = []
        for row in df.to_dict("records"):
            row["source_snapshot_ids"] = _decode_ids(row.pop("source_snapshot_ids_json", "[]"))
            row.pop("payload_json", None)
            for key in ("event_timestamp", "available_at", "provider_timestamp", "received_at"):
                val = row.get(key)
                if val is not None and not pd.isna(val):
                    row[key] = pd.Timestamp(val, tz="UTC").isoformat() if pd.Timestamp(val).tzinfo is None else pd.Timestamp(val).tz_convert("UTC").isoformat()
                else:
                    row[key] = None
            out.append(row)
        return out

    def get(self, symbol: str, feature_name: str, as_of: datetime,
            feature_version: str | None = None) -> pd.DataFrame:
        """No-look-ahead: only available_at <= as_of."""
        self.init()
        as_of = _utc_naive(as_of)
        q = "SELECT * FROM features WHERE symbol=? AND feature_name=? AND available_at <= ?"
        params: list[Any] = [symbol, feature_name, as_of]
        if feature_version:
            q += " AND feature_version = ?"
            params.append(feature_version)
        q += " ORDER BY event_time"
        with self._conn() as con:
            return con.execute(q, params).df()

    def get_all_asof(self, as_of: datetime) -> pd.DataFrame:
        self.init()
        as_of = _utc_naive(as_of)
        with self._conn() as con:
            return con.execute(
                "SELECT * FROM features WHERE available_at <= ? ORDER BY event_time", [as_of]
            ).df()

    def versions(self) -> list[str]:
        self.init()
        with self._conn() as con:
            return [r[0] for r in con.execute(
                "SELECT DISTINCT feature_version FROM features ORDER BY 1"
            ).fetchall()]


def build_panel_features(panel_closes: dict[str, pd.Series], as_of: datetime,
                         feature_version: str = "v1") -> list[FeatureRecord]:
    """Build daily panel features without look-ahead."""
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    recs: list[FeatureRecord] = []
    for symbol, s in panel_closes.items():
        s = s.sort_index()
        for ts, val in s.items():
            ts = pd.Timestamp(ts)
            if ts.tzinfo is None:
                ts = ts.tz_localize("UTC")
            event_time = ts.tz_convert("UTC").normalize().to_pydatetime()
            available_at = event_time
            if available_at > as_of:
                continue
            recs.append(FeatureRecord(
                feature_name="close", symbol=symbol, event_time=event_time,
                available_at=available_at, feature_version=feature_version,
                source="panel", data_grade="RESEARCH_PROXY", value=float(val),
            ))
    return recs
