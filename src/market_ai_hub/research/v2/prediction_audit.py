"""V2-H 2H.1 — Prediction Audit DB Foundation（LOCAL_ONLY, append-only）。

目的：永久保存「預測當時知道什麼」（prediction + factor lineage）與之後「實際發生什麼」
（outcome），且兩者**永遠分離**，防止 future leakage。

不變式（machine-enforced）：
- `feature_cutoff_timestamp <= forecast_origin`（否則 BLOCKED_TEMPORAL_ORDER）
- prediction payload 不得含 outcome/realized/future 欄位（BLOCKED_OUTCOME_IN_PREDICTION）
- factor lineage 的 `available_at <= feature_cutoff_timestamp`（否則 BLOCKED_FUTURE_FACTOR）
- public API 只有 append + read：**無 UPDATE / DELETE**
- 同 id + 同 payload → IDEMPOTENT；同 id + 不同 payload → BLOCKED_ID_COLLISION
- 修正只能 new record + `supersedes_id`
- canonical JSON + SHA256 identity；讀回後可重驗 `record_identity == stored id`
- prediction 與 outcome payload 分開 hash（不同 namespace）

不在本棒：calibration / Brier / log-loss / model training / trading / broker / scheduled recorder。
Yuanta live capability 不是 gate：live 有 → 存 live lineage；live 無 → 存 unavailable lineage。

Schema: V2_PREDICTION_AUDIT_SCHEMA_VERSION = "2H.1"。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field as dfield, asdict, replace
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

V2_PREDICTION_AUDIT_SCHEMA_VERSION = "2H.1"

PREDICTION_STATUSES = ("PENDING", "SUPERSEDED", "VOID")
LINEAGE_AVAILABILITY = ("AVAILABLE", "NOT_AVAILABLE", "EXTERNAL_ENTITLEMENT_BLOCKED", "UNKNOWN")
OUTCOME_KINDS = ("RETURN", "STATE", "DIRECTION", "TOUCH", "BREAK", "ACCEPTANCE", "CUSTOM")

APPEND_INSERTED = "INSERTED"
APPEND_IDEMPOTENT = "IDEMPOTENT"

BLOCKED_ID_COLLISION = "BLOCKED_ID_COLLISION"
BLOCKED_TEMPORAL_ORDER = "BLOCKED_TEMPORAL_ORDER"
BLOCKED_OUTCOME_IN_PREDICTION = "BLOCKED_OUTCOME_IN_PREDICTION"
BLOCKED_FUTURE_FACTOR = "BLOCKED_FUTURE_FACTOR"
BLOCKED_UNKNOWN_PREDICTION = "BLOCKED_UNKNOWN_PREDICTION"

# 出現在 prediction/lineage payload 即視為 outcome leakage 的 key
_OUTCOME_KEYS = frozenset({
    "outcome", "outcomes", "realized", "realized_return", "realized_state",
    "actual_value", "actual_state", "future_return", "future_price", "future_state",
    "settled_value", "settlement_price", "label_value",
})

_DT_FIELDS = ("forecast_origin", "feature_cutoff_timestamp", "created_at",
              "event_timestamp", "available_at", "provider_timestamp", "received_at")


class PredictionAuditError(Exception):
    """Base for audit contract violations."""


class IdCollisionError(PredictionAuditError):
    code = BLOCKED_ID_COLLISION


class TemporalOrderError(PredictionAuditError):
    code = BLOCKED_TEMPORAL_ORDER


class OutcomeInPredictionError(PredictionAuditError):
    code = BLOCKED_OUTCOME_IN_PREDICTION


class FutureFactorError(PredictionAuditError):
    code = BLOCKED_FUTURE_FACTOR


class UnknownPredictionError(PredictionAuditError):
    code = BLOCKED_UNKNOWN_PREDICTION


# ── canonical serialization / identity ──
def _json_safe(obj: Any) -> Any:
    if isinstance(obj, datetime):
        if obj.tzinfo is None:
            raise PredictionAuditError("naive datetime not allowed in audit payload")
        return obj.astimezone(timezone.utc).isoformat()
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, set):
        return sorted(_json_safe(v) for v in obj)
    return obj


def canonical_json(payload: dict) -> str:
    return json.dumps(_json_safe(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _hash(namespace: str, payload: dict) -> str:
    return sha256(f"{namespace}|{canonical_json(payload)}".encode("utf-8")).hexdigest()[:16]


def prediction_identity(payload: dict) -> str:
    return "v2h_pred_" + _hash("prediction", payload)


def outcome_identity(payload: dict) -> str:
    return "v2h_out_" + _hash("outcome", payload)


def lineage_identity(payload: dict) -> str:
    return "v2h_lin_" + _hash("lineage", payload)


def factor_lineage_digest(lineage: list["FactorLineageRecord"]) -> str:
    keys = sorted(r.lineage_id for r in lineage)
    return "v2h_lindig_" + sha256("|".join(keys).encode("utf-8")).hexdigest()[:16]


def _scan_for_outcome_keys(payload: Any, path: str = "") -> str | None:
    if isinstance(payload, dict):
        for k, v in payload.items():
            if str(k).lower() in _OUTCOME_KEYS:
                return f"{path}.{k}" if path else str(k)
            hit = _scan_for_outcome_keys(v, f"{path}.{k}" if path else str(k))
            if hit:
                return hit
    elif isinstance(payload, list):
        for i, v in enumerate(payload):
            hit = _scan_for_outcome_keys(v, f"{path}[{i}]")
            if hit:
                return hit
    return None


def _require_aware(name: str, value: datetime | None) -> None:
    if value is not None and value.tzinfo is None:
        raise PredictionAuditError(f"{name} must be tz-aware")


# ── records ──
@dataclass(frozen=True)
class FactorLineageRecord:
    """V2-A.2 factor representation lineage as persisted at prediction time (immutable)."""
    economic_factor_id: str = ""
    representation_id: str = ""
    instrument_type: str = ""
    representation_relation: str = ""
    temporal_role: str = ""
    resolved_role: str = ""
    venue_id: str = ""
    calendar_id: str = ""
    session_status: str = ""
    trading_date: str = ""
    event_timestamp: datetime | None = None
    available_at: datetime | None = None
    provider_timestamp: datetime | None = None
    received_at: datetime | None = None
    timestamp_precision: str = "UNKNOWN"
    staleness_status: str = "UNKNOWN"
    availability_status: str = "UNKNOWN"
    quality_status: str = "UNKNOWN"
    provider: str = ""
    source_type: str = ""
    source_frequency: str = ""
    data_grade: str = ""
    point_in_time_safe: bool = False
    contract_code: str = ""
    contract_month: str = ""
    roll_status: str = ""
    series_semantics: str = ""
    source_snapshot_ids: list[str] = dfield(default_factory=list)
    schema_version: str = V2_PREDICTION_AUDIT_SCHEMA_VERSION
    lineage_id: str = ""          # derived, excluded from payload
    prediction_id: str = ""       # FK, excluded from payload

    def __post_init__(self):
        if self.availability_status not in LINEAGE_AVAILABILITY:
            raise PredictionAuditError(f"unknown lineage availability_status: {self.availability_status!r}")
        for n in ("event_timestamp", "available_at", "provider_timestamp", "received_at"):
            _require_aware(n, getattr(self, n))
        object.__setattr__(self, "source_snapshot_ids", sorted({s for s in self.source_snapshot_ids if s}))

    def model_dump(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PredictionRecord:
    target_family: str = ""
    instrument: str = ""
    instrument_role: str = "DIRECT"
    calendar_id: str = ""
    frequency: str = "DAILY"
    horizon: str = "1d"
    forecast_origin: datetime | None = None
    feature_cutoff_timestamp: datetime | None = None
    build_id: str = ""
    model: str = ""
    model_version: str = ""
    v2_schema_versions: dict[str, str] = dfield(default_factory=dict)
    state_snapshot_id: str = ""
    sequence_id: str = ""
    source_snapshot_ids: list[str] = dfield(default_factory=list)
    factor_lineage_digest: str = ""
    status: str = "PENDING"
    supersedes_id: str = ""
    prediction_id: str = ""       # derived, excluded from payload
    created_at: datetime | None = None  # runtime metadata, excluded from payload

    def __post_init__(self):
        if self.status not in PREDICTION_STATUSES:
            raise PredictionAuditError(f"unknown prediction status: {self.status!r}")
        _require_aware("forecast_origin", self.forecast_origin)
        _require_aware("feature_cutoff_timestamp", self.feature_cutoff_timestamp)
        object.__setattr__(self, "source_snapshot_ids", sorted({s for s in self.source_snapshot_ids if s}))

    def model_dump(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class OutcomeRecord:
    prediction_id: str = ""
    label_type: str = ""
    outcome_kind: str = "CUSTOM"
    target_period: str = ""
    actual_value: float | None = None
    actual_state: str = ""
    event_timestamp: datetime | None = None
    available_at: datetime | None = None
    label_schema_version: str = ""
    source_snapshot_ids: list[str] = dfield(default_factory=list)
    notes: str = ""
    outcome_id: str = ""          # derived, excluded from payload
    created_at: datetime | None = None  # runtime metadata, excluded from payload

    def __post_init__(self):
        if self.outcome_kind not in OUTCOME_KINDS:
            raise PredictionAuditError(f"unknown outcome_kind: {self.outcome_kind!r}")
        for n in ("event_timestamp", "available_at"):
            _require_aware(n, getattr(self, n))
        object.__setattr__(self, "source_snapshot_ids", sorted({s for s in self.source_snapshot_ids if s}))

    def model_dump(self) -> dict:
        return asdict(self)


# ── payload builders / identities ──
def prediction_payload(record: PredictionRecord) -> dict:
    d = asdict(record)
    d.pop("prediction_id", None)
    d.pop("created_at", None)
    return d


def outcome_payload(record: OutcomeRecord) -> dict:
    d = asdict(record)
    d.pop("outcome_id", None)
    d.pop("created_at", None)
    return d


def lineage_payload(record: FactorLineageRecord) -> dict:
    d = asdict(record)
    d.pop("lineage_id", None)
    d.pop("prediction_id", None)
    return d


def make_lineage(**kwargs) -> FactorLineageRecord:
    rec = FactorLineageRecord(**kwargs)
    return replace(rec, lineage_id=lineage_identity(lineage_payload(rec)))


def lineage_from_observation(obs: Any) -> FactorLineageRecord:
    """Map a V2-A.2 `FactorRepresentationObservation` into immutable audit lineage."""
    session = getattr(obs, "session", None)
    return make_lineage(
        economic_factor_id=getattr(obs, "economic_factor_id", ""),
        representation_id=getattr(obs, "representation_id", ""),
        instrument_type=getattr(obs, "instrument_type", ""),
        representation_relation=getattr(obs, "representation_relation", ""),
        temporal_role=getattr(obs, "temporal_role", ""),
        resolved_role=getattr(obs, "resolved_role", ""),
        venue_id=getattr(obs, "venue_id", ""),
        calendar_id=getattr(obs, "calendar_id", ""),
        session_status=getattr(session, "session_status", "") if session is not None else "",
        trading_date=getattr(session, "trading_date", "") if session is not None else "",
        event_timestamp=getattr(obs, "event_timestamp", None),
        available_at=getattr(obs, "available_at", None),
        provider_timestamp=getattr(obs, "provider_timestamp", None),
        received_at=getattr(obs, "received_at", None),
        timestamp_precision=getattr(obs, "timestamp_precision", "UNKNOWN"),
        staleness_status=getattr(obs, "staleness_status", "UNKNOWN"),
        availability_status=getattr(obs, "availability_status", "UNKNOWN"),
        quality_status=getattr(obs, "quality_status", "UNKNOWN"),
        provider=getattr(obs, "provider", ""),
        source_type=getattr(obs, "source_type", ""),
        source_frequency=getattr(obs, "source_frequency", ""),
        data_grade=getattr(obs, "data_grade", ""),
        point_in_time_safe=bool(getattr(obs, "point_in_time_safe", False)),
        contract_code=getattr(obs, "contract_code", ""),
        contract_month=getattr(obs, "contract_month", ""),
        roll_status=getattr(obs, "roll_status", ""),
        series_semantics=getattr(obs, "series_semantics", ""),
        source_snapshot_ids=list(getattr(obs, "source_snapshot_ids", []) or []),
    )


def make_prediction(lineage: list[FactorLineageRecord] | None = None, **kwargs) -> PredictionRecord:
    """Build a prediction record with content-addressed id and lineage digest."""
    lineage = list(lineage or [])
    rec = PredictionRecord(**kwargs)
    if lineage:
        rec = replace(rec, factor_lineage_digest=factor_lineage_digest(lineage))
    return replace(rec, prediction_id=prediction_identity(prediction_payload(rec)))


def make_outcome(**kwargs) -> OutcomeRecord:
    rec = OutcomeRecord(**kwargs)
    return replace(rec, outcome_id=outcome_identity(outcome_payload(rec)))


# ── storage ──
def default_audit_db_path() -> Path:
    from market_ai_hub.config.settings import project_root
    return project_root() / "data" / "audit" / "prediction_audit.duckdb"


def _utc_naive(dt: datetime | None):
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def _restore(payload: dict) -> dict:
    out = dict(payload)
    for k in _DT_FIELDS:
        v = out.get(k)
        if isinstance(v, str) and v:
            try:
                out[k] = datetime.fromisoformat(v)
            except ValueError:
                pass
    return out


class PredictionAuditDB:
    """Append-only audit store (LOCAL_ONLY). Public API exposes NO UPDATE / DELETE."""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = str(path) if path is not None else str(default_audit_db_path())
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _conn(self):
        import duckdb
        return duckdb.connect(self.path)

    def _init(self) -> None:
        with self._conn() as con:
            con.execute("""
                CREATE TABLE IF NOT EXISTS predictions (
                    prediction_id VARCHAR PRIMARY KEY,
                    target_family VARCHAR, instrument VARCHAR, horizon VARCHAR,
                    forecast_origin TIMESTAMP, feature_cutoff_timestamp TIMESTAMP,
                    build_id VARCHAR, state_snapshot_id VARCHAR, sequence_id VARCHAR,
                    status VARCHAR, supersedes_id VARCHAR,
                    payload_json VARCHAR NOT NULL, created_at TIMESTAMP NOT NULL
                )""")
            con.execute("""
                CREATE TABLE IF NOT EXISTS factor_lineage (
                    prediction_id VARCHAR NOT NULL, lineage_id VARCHAR NOT NULL,
                    representation_id VARCHAR, availability_status VARCHAR,
                    payload_json VARCHAR NOT NULL,
                    PRIMARY KEY (prediction_id, lineage_id)
                )""")
            con.execute("""
                CREATE TABLE IF NOT EXISTS outcomes (
                    outcome_id VARCHAR PRIMARY KEY, prediction_id VARCHAR NOT NULL,
                    label_type VARCHAR, outcome_kind VARCHAR, available_at TIMESTAMP,
                    payload_json VARCHAR NOT NULL, created_at TIMESTAMP NOT NULL
                )""")

    # ── append ──
    def append_prediction(self, record: PredictionRecord,
                          lineage: list[FactorLineageRecord] | None = None) -> str:
        lineage = list(lineage or [])
        cutoff, origin = record.feature_cutoff_timestamp, record.forecast_origin
        if cutoff is not None and origin is not None and cutoff > origin:
            raise TemporalOrderError(f"{BLOCKED_TEMPORAL_ORDER}: feature_cutoff > forecast_origin")
        payload = prediction_payload(record)
        hit = _scan_for_outcome_keys(payload)
        if hit:
            raise OutcomeInPredictionError(f"{BLOCKED_OUTCOME_IN_PREDICTION}: {hit}")
        expect_digest = factor_lineage_digest(lineage) if lineage else ""
        if expect_digest and record.factor_lineage_digest != expect_digest:
            raise PredictionAuditError("factor_lineage_digest does not match provided lineage")
        reps = [r.representation_id for r in lineage]
        if len(reps) != len(set(reps)):
            raise PredictionAuditError("duplicate representation_id in lineage set")
        for r in lineage:
            if cutoff is not None and r.available_at is not None and r.available_at > cutoff:
                raise FutureFactorError(
                    f"{BLOCKED_FUTURE_FACTOR}: {r.representation_id} available_at > feature_cutoff")

        pid = record.prediction_id or prediction_identity(payload)
        if record.prediction_id and record.prediction_id != prediction_identity(payload):
            raise IdCollisionError(f"{BLOCKED_ID_COLLISION}: prediction_id does not match payload")
        payload_json = canonical_json(payload)
        created = datetime.now(timezone.utc)

        with self._conn() as con:
            row = con.execute("SELECT payload_json FROM predictions WHERE prediction_id = ?",
                              [pid]).fetchone()
            if row is not None:
                if row[0] == payload_json:
                    return APPEND_IDEMPOTENT
                raise IdCollisionError(f"{BLOCKED_ID_COLLISION}: prediction_id {pid} exists with different payload")
            con.execute(
                "INSERT INTO predictions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                [pid, record.target_family, record.instrument, record.horizon,
                 _utc_naive(record.forecast_origin), _utc_naive(record.feature_cutoff_timestamp),
                 record.build_id, record.state_snapshot_id, record.sequence_id,
                 record.status, record.supersedes_id, payload_json, _utc_naive(created)])
            for r in lineage:
                con.execute("INSERT INTO factor_lineage VALUES (?,?,?,?,?)",
                            [pid, r.lineage_id, r.representation_id, r.availability_status,
                             canonical_json(lineage_payload(r))])
        return APPEND_INSERTED

    def append_outcome(self, record: OutcomeRecord) -> str:
        if self.get_prediction(record.prediction_id) is None:
            raise UnknownPredictionError(f"{BLOCKED_UNKNOWN_PREDICTION}: {record.prediction_id}")
        payload = outcome_payload(record)
        oid = record.outcome_id or outcome_identity(payload)
        if record.outcome_id and record.outcome_id != outcome_identity(payload):
            raise IdCollisionError(f"{BLOCKED_ID_COLLISION}: outcome_id does not match payload")
        payload_json = canonical_json(payload)
        created = datetime.now(timezone.utc)
        with self._conn() as con:
            row = con.execute("SELECT payload_json FROM outcomes WHERE outcome_id = ?",
                              [oid]).fetchone()
            if row is not None:
                if row[0] == payload_json:
                    return APPEND_IDEMPOTENT
                raise IdCollisionError(f"{BLOCKED_ID_COLLISION}: outcome_id {oid} exists with different payload")
            con.execute("INSERT INTO outcomes VALUES (?,?,?,?,?,?,?)",
                        [oid, record.prediction_id, record.label_type, record.outcome_kind,
                         _utc_naive(record.available_at), payload_json, _utc_naive(created)])
        return APPEND_INSERTED

    # ── read ──
    def get_prediction(self, prediction_id: str) -> PredictionRecord | None:
        with self._conn() as con:
            row = con.execute(
                "SELECT payload_json, created_at FROM predictions WHERE prediction_id = ?",
                [prediction_id]).fetchone()
        if row is None:
            return None
        d = _restore(json.loads(row[0]))
        d["created_at"] = row[1].replace(tzinfo=timezone.utc) if row[1] is not None else None
        return PredictionRecord(**d, prediction_id=prediction_id)

    def get_lineage(self, prediction_id: str) -> list[FactorLineageRecord]:
        with self._conn() as con:
            rows = con.execute(
                "SELECT lineage_id, payload_json FROM factor_lineage WHERE prediction_id = ? "
                "ORDER BY representation_id, lineage_id", [prediction_id]).fetchall()
        return [FactorLineageRecord(**_restore(json.loads(r[1])), lineage_id=r[0], prediction_id=prediction_id)
                for r in rows]

    def get_outcomes(self, prediction_id: str) -> list[OutcomeRecord]:
        with self._conn() as con:
            rows = con.execute(
                "SELECT outcome_id, payload_json, created_at FROM outcomes WHERE prediction_id = ? "
                "ORDER BY created_at, outcome_id", [prediction_id]).fetchall()
        out = []
        for oid, payload_json, created in rows:
            d = _restore(json.loads(payload_json))
            d["created_at"] = created.replace(tzinfo=timezone.utc) if created is not None else None
            out.append(OutcomeRecord(**d, outcome_id=oid))
        return out

    def list_prediction_ids(self) -> list[str]:
        with self._conn() as con:
            return [r[0] for r in con.execute(
                "SELECT prediction_id FROM predictions ORDER BY created_at, prediction_id").fetchall()]

    # ── integrity ──
    def verify_prediction(self, prediction_id: str) -> bool:
        with self._conn() as con:
            row = con.execute("SELECT payload_json FROM predictions WHERE prediction_id = ?",
                              [prediction_id]).fetchone()
            if row is None:
                return False
            if prediction_identity(json.loads(row[0])) != prediction_id:
                return False
            for (payload_json,) in con.execute(
                    "SELECT payload_json FROM factor_lineage WHERE prediction_id = ?",
                    [prediction_id]).fetchall():
                payload = json.loads(payload_json)
                if lineage_identity(payload) != ("v2h_lin_" + _hash("lineage", payload)):
                    return False
            for oid, payload_json in con.execute(
                    "SELECT outcome_id, payload_json FROM outcomes WHERE prediction_id = ?",
                    [prediction_id]).fetchall():
                if outcome_identity(json.loads(payload_json)) != oid:
                    return False
        return True


def v2_schema_versions() -> dict[str, str]:
    """Assemble the actual V2 schema versions (no hardcoding)."""
    from market_ai_hub.research.v2 import (
        asof, catalyst_response, extension_exhaustion, factor_representation,
        gap_session, labels, sequential_update, session_truth, state_machine,
    )
    return {
        "asof": asof.V2_ASOF_SCHEMA_VERSION,
        "session_truth": session_truth.V2_SESSION_TRUTH_SCHEMA_VERSION,
        "factor_routing": factor_representation.V2_FACTOR_ROUTING_SCHEMA_VERSION,
        "gap_session": gap_session.V2_GAP_SESSION_SCHEMA_VERSION,
        "daily_labels": labels.V2_DAILY_LABEL_SCHEMA_VERSION,
        "state_machine": state_machine.V2_STATE_MACHINE_SCHEMA_VERSION,
        "extension_exhaustion": extension_exhaustion.V2_EXTENSION_EXHAUSTION_SCHEMA_VERSION,
        "catalyst_response": catalyst_response.V2_CATALYST_RESPONSE_SCHEMA_VERSION,
        "sequential_update": sequential_update.V2_SEQUENTIAL_UPDATE_SCHEMA_VERSION,
        "prediction_audit": V2_PREDICTION_AUDIT_SCHEMA_VERSION,
    }
