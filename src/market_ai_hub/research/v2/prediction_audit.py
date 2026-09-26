"""V2-H — Prediction Audit DB（LOCAL_ONLY, append-only）。

2H.1：prediction metadata + V2-A.2 factor lineage + outcome（分表、不可合併）。
2H.2：把「預測當時實際輸出的 forecast artifact」納入同一 append-only chain，並以
      `append_prediction_bundle()` 單一 transaction 原子寫入 prediction + lineage + artifacts。
2H.3（W3）：prediction identity 另綁定 sample_origin + label window；若有 sealed label window，
      outcome 必須在 horizon window 到期後才可 append，且 target_period 必須匹配。

不變式（machine-enforced）：
- `feature_cutoff_timestamp <= forecast_origin`（BLOCKED_TEMPORAL_ORDER）
- prediction payload 不得含 outcome/realized/future 欄位（BLOCKED_OUTCOME_IN_PREDICTION）
- factor lineage `available_at <= feature_cutoff_timestamp`（BLOCKED_FUTURE_FACTOR）
- forecast artifact `generated_at <= forecast_origin`（BLOCKED_ARTIFACT_TEMPORAL；future artifact 禁止）
- outcome `available_at >= forecast_origin`（BLOCKED_OUTCOME_TEMPORAL）
- prediction identity 綁定 `factor_lineage_digest` + `forecast_artifact_digest`
  （同一 prediction 不能事後偷偷追加 forecast output）
- artifact / outcome 指定時必須存在、同 prediction、type/label scope 相容
- public API 只有 append + read：**無 UPDATE / DELETE**
- 同 id + 同 payload → IDEMPOTENT；同 id + 不同 payload → BLOCKED_ID_COLLISION
- canonical JSON + SHA256；prediction / outcome / lineage / forecast artifact 分開 hash namespace

`raw score != calibrated probability`；`EVENT_PROBABILITY != automatically CALIBRATED`。
沒有真實 CalibrationEvidence 的值只能留在 audit（`is_public_probability()` == False），不得對外公開機率。

不在本棒：calibration fitting / Brier / log-loss / model training / trading / broker / recorder。
Yuanta live capability 不是 gate：live → 存 live lineage；unavailable → 存 unavailable lineage。

Schema: V2_PREDICTION_AUDIT_SCHEMA_VERSION = "2H.3"。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field as dfield, asdict, replace
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

V2_PREDICTION_AUDIT_SCHEMA_VERSION = "2H.3"

PREDICTION_STATUSES = ("PENDING", "SUPERSEDED", "VOID")
PREDICTION_SAMPLE_ORIGINS = ("FORWARD_PRECOMMITTED", "RETROSPECTIVE_REPLAY", "UNKNOWN")
LINEAGE_AVAILABILITY = ("AVAILABLE", "NOT_AVAILABLE", "EXTERNAL_ENTITLEMENT_BLOCKED", "UNKNOWN")
OUTCOME_KINDS = ("RETURN", "STATE", "DIRECTION", "TOUCH", "BREAK", "ACCEPTANCE", "TERMINAL", "CUSTOM")

FORECAST_ARTIFACT_TYPES = ("POINT", "QUANTILE", "INTERVAL", "CLASS_SCORE",
                           "EVENT_PROBABILITY", "STATE", "NOT_AVAILABLE")
CALIBRATION_STATUSES = ("UNCALIBRATED", "CALIBRATED", "NOT_APPLICABLE", "UNKNOWN")

APPEND_INSERTED = "INSERTED"
APPEND_IDEMPOTENT = "IDEMPOTENT"

BLOCKED_ID_COLLISION = "BLOCKED_ID_COLLISION"
BLOCKED_TEMPORAL_ORDER = "BLOCKED_TEMPORAL_ORDER"
BLOCKED_OUTCOME_IN_PREDICTION = "BLOCKED_OUTCOME_IN_PREDICTION"
BLOCKED_FUTURE_FACTOR = "BLOCKED_FUTURE_FACTOR"
BLOCKED_UNKNOWN_PREDICTION = "BLOCKED_UNKNOWN_PREDICTION"
BLOCKED_ARTIFACT_TEMPORAL = "BLOCKED_ARTIFACT_TEMPORAL"
BLOCKED_ARTIFACT_PREDICTION_MISMATCH = "BLOCKED_ARTIFACT_PREDICTION_MISMATCH"
BLOCKED_ARTIFACT_NOT_FOUND = "BLOCKED_ARTIFACT_NOT_FOUND"
BLOCKED_ARTIFACT_OUTCOME_MISMATCH = "BLOCKED_ARTIFACT_OUTCOME_MISMATCH"
BLOCKED_OUTCOME_TEMPORAL = "BLOCKED_OUTCOME_TEMPORAL"
BLOCKED_OUTCOME_IMMATURE = "BLOCKED_OUTCOME_IMMATURE"
BLOCKED_OUTCOME_SCOPE = "BLOCKED_OUTCOME_SCOPE"

# 出現在 prediction/lineage payload 即視為 outcome leakage 的 key
_OUTCOME_KEYS = frozenset({
    "outcome", "outcomes", "realized", "realized_return", "realized_state",
    "actual_value", "actual_state", "future_return", "future_price", "future_state",
    "settled_value", "settlement_price", "label_value",
})

# artifact_type -> 允許的 outcome_kind（避免 DIRECTION score 配 price-touch outcome）
_ARTIFACT_OUTCOME_KINDS = {
    "POINT": {"RETURN", "TERMINAL", "CUSTOM"},
    "QUANTILE": {"RETURN", "TERMINAL", "CUSTOM"},
    "INTERVAL": {"RETURN", "TERMINAL", "CUSTOM"},
    "CLASS_SCORE": {"DIRECTION", "STATE", "CUSTOM"},
    "EVENT_PROBABILITY": {"TOUCH", "BREAK", "ACCEPTANCE", "TERMINAL", "CUSTOM"},
    "STATE": {"STATE", "CUSTOM"},
    "NOT_AVAILABLE": set(),
}

_DT_FIELDS = ("forecast_origin", "feature_cutoff_timestamp", "label_window_start", "label_window_end",
              "created_at", "generated_at", "event_timestamp", "available_at",
              "provider_timestamp", "received_at")


def label_scope(label_type: str) -> str:
    """TOUCH / TERMINAL / DIRECTION / STATE scope token（TOUCH != TERMINAL）。"""
    t = (label_type or "").upper()
    for token in ("TOUCH", "BREAK", "ACCEPT", "TERMINAL", "RETURN", "DIRECTION", "STATE"):
        if token in t:
            return "ACCEPTANCE" if token == "ACCEPT" else ("TERMINAL" if token == "RETURN" else token)
    return "UNKNOWN"


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


class ArtifactTemporalError(PredictionAuditError):
    code = BLOCKED_ARTIFACT_TEMPORAL


class ArtifactBindingError(PredictionAuditError):
    code = BLOCKED_ARTIFACT_PREDICTION_MISMATCH


class ArtifactNotFoundError(PredictionAuditError):
    code = BLOCKED_ARTIFACT_NOT_FOUND


class ArtifactOutcomeMismatchError(PredictionAuditError):
    code = BLOCKED_ARTIFACT_OUTCOME_MISMATCH


class OutcomeTemporalError(PredictionAuditError):
    code = BLOCKED_OUTCOME_TEMPORAL


class OutcomeMaturityError(PredictionAuditError):
    code = BLOCKED_OUTCOME_IMMATURE


class OutcomeScopeError(PredictionAuditError):
    code = BLOCKED_OUTCOME_SCOPE


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


def forecast_artifact_identity(payload: dict) -> str:
    return "v2h_art_" + _hash("forecast_artifact", payload)


def _digest_of_ids(prefix: str, ids: list[str]) -> str:
    if not ids:
        return ""
    return prefix + sha256("|".join(sorted(ids)).encode("utf-8")).hexdigest()[:16]


def factor_lineage_digest(lineage: list["FactorLineageRecord"]) -> str:
    return _digest_of_ids("v2h_lindig_", [r.lineage_id for r in lineage])


def forecast_artifact_digest(artifacts: list["ForecastArtifactRecord"]) -> str:
    return _digest_of_ids("v2h_artdig_", [a.forecast_artifact_id for a in artifacts])


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


def _canon_ids(ids) -> list[str]:
    return sorted({s for s in (ids or []) if s})


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
        object.__setattr__(self, "source_snapshot_ids", _canon_ids(self.source_snapshot_ids))

    def model_dump(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ForecastArtifactRecord:
    """The forecast output actually produced at prediction time (immutable audit artifact)."""
    prediction_id: str = ""
    artifact_type: str = "NOT_AVAILABLE"
    calibration_domain: str = ""
    probability_type: str = ""
    event_definition_id: str = ""
    label_type: str = ""
    value: float | None = None
    raw_score: float | None = None
    class_label: str = ""
    quantile_level: float | None = None
    lower_value: float | None = None
    upper_value: float | None = None
    nominal_coverage: float | None = None
    units: str = ""
    status: str = "OK"
    calibration_status_at_origin: str = "UNCALIBRATED"
    calibration_evidence_id: str = ""
    distribution_id: str = ""
    distribution_version: str = ""
    generated_at: datetime | None = None
    source_snapshot_ids: list[str] = dfield(default_factory=list)
    schema_version: str = V2_PREDICTION_AUDIT_SCHEMA_VERSION
    forecast_artifact_id: str = ""  # derived, excluded from payload
    created_at: datetime | None = None  # runtime metadata, excluded from payload

    def __post_init__(self):
        if self.artifact_type not in FORECAST_ARTIFACT_TYPES:
            raise PredictionAuditError(f"unknown artifact_type: {self.artifact_type!r}")
        if self.calibration_status_at_origin not in CALIBRATION_STATUSES:
            raise PredictionAuditError(
                f"unknown calibration_status_at_origin: {self.calibration_status_at_origin!r}")
        _require_aware("generated_at", self.generated_at)
        # 不適用欄位保持 None/""：只在對應 type 才要求必填
        if self.artifact_type == "QUANTILE" and self.quantile_level is None:
            raise PredictionAuditError("QUANTILE artifact requires quantile_level")
        if self.artifact_type == "INTERVAL":
            if self.lower_value is None or self.upper_value is None or self.nominal_coverage is None:
                raise PredictionAuditError("INTERVAL artifact requires lower_value/upper_value/nominal_coverage")
            if self.lower_value > self.upper_value:
                raise PredictionAuditError("INTERVAL lower_value > upper_value")
        if self.artifact_type == "CLASS_SCORE" and not self.class_label and self.raw_score is None:
            raise PredictionAuditError("CLASS_SCORE artifact requires class_label or raw_score")
        if self.artifact_type == "EVENT_PROBABILITY" and not self.event_definition_id:
            raise PredictionAuditError("EVENT_PROBABILITY artifact requires event_definition_id")
        if self.artifact_type == "NOT_AVAILABLE" and (self.value is not None or self.raw_score is not None):
            raise PredictionAuditError("NOT_AVAILABLE artifact must not carry value/raw_score")
        for n in ("value", "raw_score", "quantile_level", "lower_value", "upper_value", "nominal_coverage"):
            v = getattr(self, n)
            if v is not None and not isinstance(v, (int, float)):
                raise PredictionAuditError(f"{n} must be numeric or None")
        object.__setattr__(self, "source_snapshot_ids", _canon_ids(self.source_snapshot_ids))

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
    sample_origin: str = "UNKNOWN"
    label_window_id: str = ""
    label_window_start: datetime | None = None
    label_window_end: datetime | None = None
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
    forecast_artifact_digest: str = ""
    status: str = "PENDING"
    supersedes_id: str = ""
    prediction_id: str = ""       # derived, excluded from payload
    created_at: datetime | None = None  # runtime metadata, excluded from payload

    def __post_init__(self):
        if self.status not in PREDICTION_STATUSES:
            raise PredictionAuditError(f"unknown prediction status: {self.status!r}")
        if self.sample_origin not in PREDICTION_SAMPLE_ORIGINS:
            raise PredictionAuditError(f"unknown sample_origin: {self.sample_origin!r}")
        _require_aware("forecast_origin", self.forecast_origin)
        _require_aware("feature_cutoff_timestamp", self.feature_cutoff_timestamp)
        for n in ("label_window_start", "label_window_end"):
            value = getattr(self, n)
            if value is not None:
                _require_aware(n, value)
        if (self.label_window_start is None) != (self.label_window_end is None):
            raise PredictionAuditError("label_window_start/end must be both set or both absent")
        if self.label_window_start is not None and self.label_window_end is not None:
            if self.label_window_start < self.forecast_origin:
                raise PredictionAuditError("label_window_start < forecast_origin")
            if self.label_window_end < self.label_window_start:
                raise PredictionAuditError("label_window_end < label_window_start")
            if not self.label_window_id:
                raise PredictionAuditError("label_window_id required when label window is sealed")
        object.__setattr__(self, "source_snapshot_ids", _canon_ids(self.source_snapshot_ids))

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
    forecast_artifact_id: str = ""   # optional binding to a forecast artifact
    outcome_id: str = ""             # derived, excluded from payload
    created_at: datetime | None = None  # runtime metadata, excluded from payload

    def __post_init__(self):
        if self.outcome_kind not in OUTCOME_KINDS:
            raise PredictionAuditError(f"unknown outcome_kind: {self.outcome_kind!r}")
        for n in ("event_timestamp", "available_at"):
            _require_aware(n, getattr(self, n))
        object.__setattr__(self, "source_snapshot_ids", _canon_ids(self.source_snapshot_ids))

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


def forecast_artifact_payload(record: ForecastArtifactRecord) -> dict:
    d = asdict(record)
    d.pop("forecast_artifact_id", None)
    d.pop("prediction_id", None)   # FK, excluded so identity is not circular with the prediction id
    d.pop("created_at", None)
    return d


def is_public_probability(artifact: ForecastArtifactRecord) -> bool:
    """Audit metadata never authorizes publication.

    2I.1 has no fitted evidence resolver. Publication must use the typed
    Price/Probability Map eligibility gate, not caller-declared status/IDs.
    """
    return False


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


def make_forecast_artifact(prediction_id: str = "", **kwargs) -> ForecastArtifactRecord:
    rec = ForecastArtifactRecord(prediction_id=prediction_id, **kwargs)
    return replace(rec, forecast_artifact_id=forecast_artifact_identity(forecast_artifact_payload(rec)))


def make_prediction(lineage: list[FactorLineageRecord] | None = None,
                    forecast_artifacts: list[ForecastArtifactRecord] | None = None,
                    **kwargs) -> PredictionRecord:
    """Build a prediction whose identity binds factor lineage + forecast artifact digests."""
    lineage = list(lineage or [])
    artifacts = list(forecast_artifacts or [])
    rec = PredictionRecord(**kwargs)
    if lineage:
        rec = replace(rec, factor_lineage_digest=factor_lineage_digest(lineage))
    if artifacts:
        rec = replace(rec, forecast_artifact_digest=forecast_artifact_digest(artifacts))
    return replace(rec, prediction_id=prediction_identity(prediction_payload(rec)))


def make_outcome(**kwargs) -> OutcomeRecord:
    rec = OutcomeRecord(**kwargs)
    return replace(rec, outcome_id=outcome_identity(outcome_payload(rec)))


# ── storage ──
def default_audit_db_path() -> Path:
    from market_ai_hub.config.runtime_paths import data_root
    return data_root() / "audit" / "prediction_audit.duckdb"


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

    def __init__(self, path: str | Path | None = None, *, read_only: bool = False) -> None:
        self.path = str(path) if path is not None else str(default_audit_db_path())
        self.read_only = read_only
        if read_only:
            if not Path(self.path).is_file():
                raise FileNotFoundError(self.path)
            return
        if self.path != ":memory:":
            Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _conn(self):
        import duckdb
        return duckdb.connect(self.path, read_only=self.read_only)

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
                CREATE TABLE IF NOT EXISTS forecast_artifacts (
                    forecast_artifact_id VARCHAR PRIMARY KEY, prediction_id VARCHAR NOT NULL,
                    artifact_type VARCHAR, calibration_domain VARCHAR,
                    calibration_status_at_origin VARCHAR, label_type VARCHAR,
                    generated_at TIMESTAMP,
                    payload_json VARCHAR NOT NULL, created_at TIMESTAMP NOT NULL
                )""")
            con.execute("""
                CREATE TABLE IF NOT EXISTS outcomes (
                    outcome_id VARCHAR PRIMARY KEY, prediction_id VARCHAR NOT NULL,
                    label_type VARCHAR, outcome_kind VARCHAR, available_at TIMESTAMP,
                    forecast_artifact_id VARCHAR,
                    payload_json VARCHAR NOT NULL, created_at TIMESTAMP NOT NULL
                )""")

    # ── validation helpers ──
    @staticmethod
    def _validate_prediction(record: PredictionRecord, lineage: list[FactorLineageRecord],
                             artifacts: list[ForecastArtifactRecord]) -> None:
        cutoff, origin = record.feature_cutoff_timestamp, record.forecast_origin
        if cutoff is not None and origin is not None and cutoff > origin:
            raise TemporalOrderError(f"{BLOCKED_TEMPORAL_ORDER}: feature_cutoff > forecast_origin")
        hit = _scan_for_outcome_keys(prediction_payload(record))
        if hit:
            raise OutcomeInPredictionError(f"{BLOCKED_OUTCOME_IN_PREDICTION}: {hit}")
        reps = [r.representation_id for r in lineage]
        if len(reps) != len(set(reps)):
            raise PredictionAuditError("duplicate representation_id in lineage set")
        for r in lineage:
            if cutoff is not None and r.available_at is not None and r.available_at > cutoff:
                raise FutureFactorError(
                    f"{BLOCKED_FUTURE_FACTOR}: {r.representation_id} available_at > feature_cutoff")
        if lineage and record.factor_lineage_digest != factor_lineage_digest(lineage):
            raise PredictionAuditError("factor_lineage_digest does not match provided lineage")
        if artifacts and record.forecast_artifact_digest != forecast_artifact_digest(artifacts):
            raise PredictionAuditError("forecast_artifact_digest does not match provided artifacts")
        for a in artifacts:
            if a.prediction_id != record.prediction_id:
                raise ArtifactBindingError(
                    f"{BLOCKED_ARTIFACT_PREDICTION_MISMATCH}: artifact {a.forecast_artifact_id}")
            if a.generated_at is None or origin is None or a.generated_at > origin:
                raise ArtifactTemporalError(
                    f"{BLOCKED_ARTIFACT_TEMPORAL}: {a.forecast_artifact_id} generated_at > forecast_origin")

    # ── transaction steps (separate so atomic rollback is testable) ──
    def _insert_prediction_row(self, con, record: PredictionRecord, payload_json: str, created: datetime) -> None:
        con.execute(
            "INSERT INTO predictions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [record.prediction_id, record.target_family, record.instrument, record.horizon,
             _utc_naive(record.forecast_origin), _utc_naive(record.feature_cutoff_timestamp),
             record.build_id, record.state_snapshot_id, record.sequence_id,
             record.status, record.supersedes_id, payload_json, _utc_naive(created)])

    def _insert_lineage_rows(self, con, prediction_id: str,
                             lineage: list[FactorLineageRecord]) -> None:
        for r in lineage:
            con.execute("INSERT INTO factor_lineage VALUES (?,?,?,?,?)",
                        [prediction_id, r.lineage_id, r.representation_id, r.availability_status,
                         canonical_json(lineage_payload(r))])

    def _insert_artifact_rows(self, con, prediction_id: str,
                              artifacts: list[ForecastArtifactRecord],
                              created: datetime | None = None) -> None:
        created = created or datetime.now(timezone.utc)
        for a in artifacts:
            con.execute("INSERT INTO forecast_artifacts VALUES (?,?,?,?,?,?,?,?,?)",
                        [a.forecast_artifact_id, prediction_id, a.artifact_type,
                         a.calibration_domain, a.calibration_status_at_origin, a.label_type,
                         _utc_naive(a.generated_at), canonical_json(forecast_artifact_payload(a)),
                         _utc_naive(a.created_at or created)])

    # ── append ──
    def append_prediction_bundle(self, prediction: PredictionRecord,
                                 lineage: list[FactorLineageRecord] | None = None,
                                 forecast_artifacts: list[ForecastArtifactRecord] | None = None) -> str:
        """Validate everything first, then write prediction + lineage + artifacts in ONE transaction."""
        lineage = list(lineage or [])
        artifacts = list(forecast_artifacts or [])
        self._validate_prediction(prediction, lineage, artifacts)

        payload = prediction_payload(prediction)
        payload_json = canonical_json(payload)
        pid = prediction.prediction_id or prediction_identity(payload)
        if prediction.prediction_id and prediction.prediction_id != prediction_identity(payload):
            raise IdCollisionError(f"{BLOCKED_ID_COLLISION}: prediction_id does not match payload")
        record = prediction if prediction.prediction_id else replace(prediction, prediction_id=pid)

        for a in artifacts:
            if a.forecast_artifact_id and a.forecast_artifact_id != forecast_artifact_identity(
                    forecast_artifact_payload(a)):
                raise IdCollisionError(
                    f"{BLOCKED_ID_COLLISION}: forecast_artifact_id {a.forecast_artifact_id}")

        con = self._conn()
        try:
            con.execute("BEGIN TRANSACTION")
            existing = con.execute("SELECT payload_json FROM predictions WHERE prediction_id = ?",
                                   [pid]).fetchone()
            if existing is not None:
                if existing[0] == payload_json:
                    con.execute("COMMIT")
                    return APPEND_IDEMPOTENT
                raise IdCollisionError(
                    f"{BLOCKED_ID_COLLISION}: prediction_id {pid} exists with different payload")
            for a in artifacts:
                row = con.execute(
                    "SELECT prediction_id, payload_json FROM forecast_artifacts "
                    "WHERE forecast_artifact_id = ?",
                    [a.forecast_artifact_id]).fetchone()
                if row is not None:
                    existing_prediction_id, existing_payload = row
                    if existing_payload != canonical_json(forecast_artifact_payload(a)):
                        raise IdCollisionError(
                            f"{BLOCKED_ID_COLLISION}: forecast_artifact_id {a.forecast_artifact_id}")
                    if existing_prediction_id != pid:
                        raise ArtifactBindingError(
                            f"{BLOCKED_ARTIFACT_PREDICTION_MISMATCH}: "
                            f"forecast_artifact_id {a.forecast_artifact_id} is already bound to "
                            f"{existing_prediction_id}")
            now = datetime.now(timezone.utc)
            self._insert_prediction_row(con, record, payload_json, now)
            self._insert_lineage_rows(con, pid, lineage)
            self._insert_artifact_rows(con, pid, artifacts, now)
            con.execute("COMMIT")
        except Exception:
            try:
                con.execute("ROLLBACK")
            except Exception:
                pass
            raise
        finally:
            con.close()
        return APPEND_INSERTED

    def append_prediction(self, record: PredictionRecord,
                          lineage: list[FactorLineageRecord] | None = None) -> str:
        """2H.1-compatible path (no forecast artifacts). Artifacts require the bundle."""
        if record.forecast_artifact_digest:
            raise ArtifactBindingError(
                "use append_prediction_bundle() when forecast artifacts exist")
        return self.append_prediction_bundle(record, lineage, [])

    def append_outcome(self, record: OutcomeRecord) -> str:
        pred = self.get_prediction(record.prediction_id)
        if pred is None:
            raise UnknownPredictionError(f"{BLOCKED_UNKNOWN_PREDICTION}: {record.prediction_id}")
        if record.forecast_artifact_id:
            art = self.get_forecast_artifact(record.forecast_artifact_id)
            if art is None:
                raise ArtifactNotFoundError(
                    f"{BLOCKED_ARTIFACT_NOT_FOUND}: {record.forecast_artifact_id}")
            if art.prediction_id != record.prediction_id:
                raise ArtifactBindingError(
                    f"{BLOCKED_ARTIFACT_PREDICTION_MISMATCH}: {record.forecast_artifact_id}")
            if (record.outcome_kind not in _ARTIFACT_OUTCOME_KINDS.get(art.artifact_type, set())
                    or record.label_type != art.label_type):
                raise ArtifactOutcomeMismatchError(
                    f"{BLOCKED_ARTIFACT_OUTCOME_MISMATCH}: {art.artifact_type}/"
                    f"{art.label_type} vs {record.outcome_kind}/{record.label_type}")
        if (record.available_at is not None and pred.forecast_origin is not None
                and record.available_at < pred.forecast_origin):
            raise OutcomeTemporalError(
                f"{BLOCKED_OUTCOME_TEMPORAL}: available_at < forecast_origin")

        if pred.label_window_end is not None:
            if record.available_at is None or record.available_at < pred.label_window_end:
                raise OutcomeMaturityError(
                    f"{BLOCKED_OUTCOME_IMMATURE}: available_at < label_window_end")
            if record.target_period != pred.label_window_id:
                raise OutcomeScopeError(
                    f"{BLOCKED_OUTCOME_SCOPE}: target_period {record.target_period!r} != "
                    f"label_window_id {pred.label_window_id!r}")

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
            con.execute("INSERT INTO outcomes VALUES (?,?,?,?,?,?,?,?)",
                        [oid, record.prediction_id, record.label_type, record.outcome_kind,
                         _utc_naive(record.available_at), record.forecast_artifact_id,
                         payload_json, _utc_naive(created)])
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

    def get_forecast_artifacts(self, prediction_id: str) -> list[ForecastArtifactRecord]:
        with self._conn() as con:
            rows = con.execute(
                "SELECT forecast_artifact_id, prediction_id, payload_json, created_at FROM forecast_artifacts "
                "WHERE prediction_id = ? ORDER BY forecast_artifact_id", [prediction_id]).fetchall()
        out = []
        for aid, pid, payload_json, created in rows:
            d = _restore(json.loads(payload_json))
            d["created_at"] = created.replace(tzinfo=timezone.utc) if created is not None else None
            out.append(ForecastArtifactRecord(**d, forecast_artifact_id=aid, prediction_id=pid))
        return out

    def get_forecast_artifact(self, forecast_artifact_id: str) -> ForecastArtifactRecord | None:
        with self._conn() as con:
            row = con.execute(
                "SELECT prediction_id, payload_json, created_at FROM forecast_artifacts "
                "WHERE forecast_artifact_id = ?", [forecast_artifact_id]).fetchone()
        if row is None:
            return None
        pid, payload_json, created = row
        d = _restore(json.loads(payload_json))
        d["created_at"] = created.replace(tzinfo=timezone.utc) if created is not None else None
        return ForecastArtifactRecord(**d, forecast_artifact_id=forecast_artifact_id, prediction_id=pid)

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
            payload = json.loads(row[0])
            for (payload_json,) in con.execute(
                    "SELECT payload_json FROM factor_lineage WHERE prediction_id = ?",
                    [prediction_id]).fetchall():
                if lineage_identity(json.loads(payload_json)) != (
                        "v2h_lin_" + _hash("lineage", json.loads(payload_json))):
                    return False
            artifact_ids = []
            for aid, payload_json in con.execute(
                    "SELECT forecast_artifact_id, payload_json FROM forecast_artifacts "
                    "WHERE prediction_id = ?", [prediction_id]).fetchall():
                if forecast_artifact_identity(json.loads(payload_json)) != aid:
                    return False
                artifact_ids.append(aid)
            if payload.get("forecast_artifact_digest") != _digest_of_ids("v2h_artdig_", artifact_ids):
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
        asof, calibration_evaluation, calibration_fitting, catalyst_response, evaluation_governance,
        extension_exhaustion, factor_representation, forward_cycle, gap_session, labels,
        sequential_update, session_truth, state_machine, tick_detail_source,
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
        "calibration_evaluation": calibration_evaluation.V2_CALIBRATION_EVALUATION_SCHEMA_VERSION,
        "evaluation_governance": evaluation_governance.W3_EVALUATION_GOVERNANCE_SCHEMA_VERSION,
        "forward_cycle": forward_cycle.W3_FORWARD_CYCLE_SCHEMA_VERSION,
        "tick_detail_source": tick_detail_source.W3_TICK_DETAIL_SOURCE_SCHEMA_VERSION,
    }
