"""W3.2 — precommitted forward prediction / maturity / settlement cycle.

RESEARCH ONLY. This module connects one minimal direct-market forward cycle to the
existing V2-H 2H.3 audit store and W3.1 governed evaluator.

It intentionally does not:
- backdate forecasts;
- treat historical replay as forward evidence;
- aggregate broker TICK into daily bars;
- fit/calibrate probabilities;
- trade or call broker/account APIs.

The first supported cycle is OSAKA_MICRO / JNU, 1 OSE derivatives trading session,
LAST_PRICE_NAIVE, terminal contract close. A prediction is accepted only in the
post-close / pre-night-session precommit window and only from contract-specific,
point-in-time-safe, source-snapshotted daily input.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time, timezone
from math import isfinite
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from market_ai_hub.research.v2 import evaluation_governance as EG
from market_ai_hub.research.v2 import prediction_audit as PA
from market_ai_hub.services.build_info import build_fingerprint
from market_ai_hub.services.calendar import (
    is_ose_derivatives_session,
    next_ose_derivatives_session,
)

W3_FORWARD_CYCLE_SCHEMA_VERSION = "W3.2"

TARGET_FAMILY = "OSAKA_MICRO"
INSTRUMENT = "JNU"
REPRESENTATION_ID = "OSE_MICRO_FUTURES"
ECONOMIC_FACTOR_ID = "JP_EQUITY"
VENUE_ID = "OSE_DERIVATIVES"
CALENDAR_ID = "OSE_DERIVATIVES"
HORIZON = "1d"
MODEL_NAME = "last_price_naive"
MODEL_VERSION = "w3.2-last-price-naive-1"
LABEL_TYPE = "TERMINAL_PRICE_1D"
ARTIFACT_TYPE = "POINT"
OUTCOME_KIND = "TERMINAL"
SOURCE_FREQUENCY = "DAILY"
FORWARD_DAILY_FEATURE_NAME = "terminal_close"
FORWARD_DAILY_FEATURE_VERSION = "w3.2-contract-daily-close-1"

STATUS_PRECOMMITTED = "PRECOMMITTED"
STATUS_ALREADY_PRECOMMITTED = "ALREADY_PRECOMMITTED"
STATUS_SETTLED = "SETTLED"
STATUS_ALREADY_SETTLED = "ALREADY_SETTLED"
STATUS_INPUT_NOT_ELIGIBLE = "INPUT_NOT_ELIGIBLE"
STATUS_OUTCOME_NOT_ELIGIBLE = "OUTCOME_NOT_ELIGIBLE"
STATUS_NOT_MATURE = "NOT_MATURE"
STATUS_NOT_FOUND = "NOT_FOUND"
STATUS_BLOCKED = "BLOCKED"

_JST = ZoneInfo("Asia/Tokyo")
_OSE_DAY_CLOSE = time(15, 45)
_OSE_NIGHT_OPEN = time(17, 0)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _utc(dt: datetime) -> datetime:
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return dt.astimezone(timezone.utc)


def _parse_date(value: str | date | datetime) -> date:
    return pd.Timestamp(value).date()


def _ose_close_utc(trading_date: str | date | datetime) -> datetime:
    d = _parse_date(trading_date)
    return datetime.combine(d, _OSE_DAY_CLOSE, tzinfo=_JST).astimezone(timezone.utc)


def _ose_night_open_utc(session_start_date: str | date | datetime) -> datetime:
    d = _parse_date(session_start_date)
    return datetime.combine(d, _OSE_NIGHT_OPEN, tzinfo=_JST).astimezone(timezone.utc)


@dataclass(frozen=True)
class OsakaForwardInput:
    """A fully observed previous-session close known before forecast origin."""

    trading_date: str
    close: float
    session_close_timestamp: datetime
    available_at: datetime
    source_snapshot_ids: list[str] = field(default_factory=list)
    provider: str = ""
    source_type: str = "DAILY_BAR_CLOSE"
    data_grade: str = ""
    quality_status: str = "VERIFIED"
    availability_status: str = "AVAILABLE"
    point_in_time_safe: bool = False
    contract_code: str = ""
    contract_month: str = ""
    roll_status: str = "UNKNOWN"
    series_semantics: str = "UNKNOWN"
    source_frequency: str = SOURCE_FREQUENCY

    def __post_init__(self) -> None:
        _utc(self.session_close_timestamp)
        _utc(self.available_at)
        if not isfinite(float(self.close)) or float(self.close) <= 0:
            raise ValueError("close must be finite and positive")
        object.__setattr__(
            self, "source_snapshot_ids",
            sorted({str(x) for x in self.source_snapshot_ids if str(x)}),
        )

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class OsakaForwardOutcome:
    """Observed terminal close for the sealed target trading session."""

    trading_date: str
    close: float
    session_close_timestamp: datetime
    available_at: datetime
    source_snapshot_ids: list[str] = field(default_factory=list)
    provider: str = ""
    source_type: str = "DAILY_BAR_CLOSE"
    data_grade: str = ""
    quality_status: str = "VERIFIED"
    availability_status: str = "AVAILABLE"
    point_in_time_safe: bool = False
    contract_code: str = ""
    contract_month: str = ""
    roll_status: str = "UNKNOWN"
    series_semantics: str = "UNKNOWN"

    def __post_init__(self) -> None:
        _utc(self.session_close_timestamp)
        _utc(self.available_at)
        if not isfinite(float(self.close)) or float(self.close) <= 0:
            raise ValueError("close must be finite and positive")
        object.__setattr__(
            self, "source_snapshot_ids",
            sorted({str(x) for x in self.source_snapshot_ids if str(x)}),
        )

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ForwardCycleResult:
    status: str
    reason: str = ""
    prediction_id: str = ""
    forecast_artifact_id: str = ""
    outcome_id: str = ""
    input_trading_date: str = ""
    target_trading_date: str = ""
    forecast_origin: datetime | None = None
    label_window_start: datetime | None = None
    label_window_end: datetime | None = None
    values_exposed: bool = False

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


def ose_next_full_session_window(
    input_trading_date: str | date | datetime,
) -> tuple[str, datetime, datetime]:
    """Return target trading date + full OSE target window.

    For OSE, the next trading day's full exchange-day window begins with the
    night session at 17:00 JST on the completed input trading date, and ends
    with the target day close at 15:45 JST.
    """
    source_date = _parse_date(input_trading_date)
    if not is_ose_derivatives_session(source_date):
        raise ValueError(f"input_trading_date is not an OSE derivatives session: {source_date}")
    target = next_ose_derivatives_session(source_date)
    if not target:
        raise ValueError(f"no next OSE derivatives session after {source_date}")
    start = _ose_night_open_utc(source_date)
    end = _ose_close_utc(target)
    if end <= start:
        raise ValueError("invalid OSE full-session window")
    return target, start, end


def _input_blockers(snapshot: OsakaForwardInput, now: datetime) -> list[str]:
    now = _utc(now)
    blockers: list[str] = []
    try:
        source_date = _parse_date(snapshot.trading_date)
        expected_close = _ose_close_utc(source_date)
        target, window_start, _ = ose_next_full_session_window(source_date)
    except Exception as exc:
        return [f"CALENDAR_INVALID:{type(exc).__name__}"]

    if snapshot.availability_status != "AVAILABLE":
        blockers.append("NOT_AVAILABLE")
    if not snapshot.point_in_time_safe:
        blockers.append("POINT_IN_TIME_UNSAFE")
    if not snapshot.source_snapshot_ids:
        blockers.append("SOURCE_SNAPSHOT_IDS_REQUIRED")
    if snapshot.source_frequency.upper() not in ("DAILY", "1D"):
        blockers.append("SOURCE_FREQUENCY_NOT_DAILY")
    if snapshot.series_semantics != "CONTRACT":
        blockers.append("SERIES_NOT_CONTRACT")
    if snapshot.roll_status != "NONE":
        blockers.append("ROLL_STATUS_NOT_NONE")
    if not snapshot.contract_code:
        blockers.append("CONTRACT_CODE_REQUIRED")
    if not snapshot.contract_month:
        blockers.append("CONTRACT_MONTH_REQUIRED")
    if not snapshot.provider:
        blockers.append("PROVIDER_REQUIRED")
    if not snapshot.data_grade:
        blockers.append("DATA_GRADE_REQUIRED")
    if _utc(snapshot.session_close_timestamp) != expected_close:
        blockers.append("SESSION_CLOSE_TIMESTAMP_MISMATCH")
    if _utc(snapshot.available_at) < expected_close:
        blockers.append("AVAILABLE_BEFORE_SESSION_CLOSE")
    if _utc(snapshot.available_at) > now:
        blockers.append("AVAILABLE_AFTER_FORECAST_ORIGIN")
    if now < expected_close:
        blockers.append("SOURCE_SESSION_NOT_CLOSED")
    if now >= window_start:
        blockers.append("PRECOMMIT_WINDOW_CLOSED")
    if target <= snapshot.trading_date:
        blockers.append("TARGET_NOT_AFTER_INPUT_SESSION")
    return blockers


def _scope_match(pred: PA.PredictionRecord, target_trading_date: str) -> bool:
    return (
        pred.target_family == TARGET_FAMILY
        and pred.instrument == INSTRUMENT
        and pred.horizon == HORIZON
        and pred.model == MODEL_NAME
        and pred.model_version == MODEL_VERSION
        and pred.sample_origin == "FORWARD_PRECOMMITTED"
        and pred.label_window_id == target_trading_date
    )


def _find_scope_predictions(db: PA.PredictionAuditDB, target_trading_date: str) -> list[PA.PredictionRecord]:
    out: list[PA.PredictionRecord] = []
    for pid in db.list_prediction_ids():
        pred = db.get_prediction(pid)
        if pred is not None and _scope_match(pred, target_trading_date):
            out.append(pred)
    return sorted(out, key=lambda p: (p.forecast_origin or datetime.min.replace(tzinfo=timezone.utc), p.prediction_id))


def precommit_osaka_last_price(
    snapshot: OsakaForwardInput,
    *,
    db: PA.PredictionAuditDB | None = None,
) -> ForwardCycleResult:
    """Precommit one 1-session OSAKA_MICRO last-price baseline using wall-clock now."""
    db = db or PA.PredictionAuditDB()
    now = _now_utc()
    blockers = _input_blockers(snapshot, now)
    try:
        target, window_start, window_end = ose_next_full_session_window(snapshot.trading_date)
    except Exception as exc:
        return ForwardCycleResult(
            status=STATUS_INPUT_NOT_ELIGIBLE,
            reason=f"CALENDAR_INVALID:{type(exc).__name__}",
            input_trading_date=snapshot.trading_date,
            forecast_origin=now,
        )
    if blockers:
        return ForwardCycleResult(
            status=STATUS_INPUT_NOT_ELIGIBLE,
            reason=";".join(sorted(set(blockers))),
            input_trading_date=snapshot.trading_date,
            target_trading_date=target,
            forecast_origin=now,
            label_window_start=window_start,
            label_window_end=window_end,
        )

    existing = _find_scope_predictions(db, target)
    if existing:
        pred = existing[0]
        arts = db.get_forecast_artifacts(pred.prediction_id)
        return ForwardCycleResult(
            status=STATUS_ALREADY_PRECOMMITTED,
            reason="scope/window already has a precommitted prediction",
            prediction_id=pred.prediction_id,
            forecast_artifact_id=arts[0].forecast_artifact_id if len(arts) == 1 else "",
            input_trading_date=snapshot.trading_date,
            target_trading_date=target,
            forecast_origin=pred.forecast_origin,
            label_window_start=pred.label_window_start,
            label_window_end=pred.label_window_end,
        )

    lineage = PA.make_lineage(
        economic_factor_id=ECONOMIC_FACTOR_ID,
        representation_id=REPRESENTATION_ID,
        instrument_type="FUTURE",
        representation_relation="DIRECT",
        temporal_role="PREVIOUS_SESSION_REFERENCE",
        resolved_role="PREVIOUS_SESSION_REFERENCE",
        venue_id=VENUE_ID,
        calendar_id=CALENDAR_ID,
        session_status="CLOSED",
        trading_date=snapshot.trading_date,
        event_timestamp=snapshot.session_close_timestamp,
        available_at=snapshot.available_at,
        provider_timestamp=None,
        received_at=snapshot.available_at,
        timestamp_precision="BAR_CLOSE_TIMESTAMP",
        staleness_status="FRESH_AT_FORECAST_ORIGIN",
        availability_status=snapshot.availability_status,
        quality_status=snapshot.quality_status,
        provider=snapshot.provider,
        source_type=snapshot.source_type,
        source_frequency=SOURCE_FREQUENCY,
        data_grade=snapshot.data_grade,
        point_in_time_safe=True,
        contract_code=snapshot.contract_code,
        contract_month=snapshot.contract_month,
        roll_status=snapshot.roll_status,
        series_semantics=snapshot.series_semantics,
        source_snapshot_ids=snapshot.source_snapshot_ids,
    )
    template = PA.make_forecast_artifact(
        prediction_id="",
        artifact_type=ARTIFACT_TYPE,
        calibration_domain="PRICE",
        label_type=LABEL_TYPE,
        value=float(snapshot.close),
        units="index_points",
        status="OK",
        calibration_status_at_origin="NOT_APPLICABLE",
        generated_at=now,
        source_snapshot_ids=snapshot.source_snapshot_ids,
    )
    schemas = PA.v2_schema_versions()
    pred = PA.make_prediction(
        [lineage],
        [template],
        target_family=TARGET_FAMILY,
        instrument=INSTRUMENT,
        instrument_role="DIRECT",
        calendar_id=CALENDAR_ID,
        frequency="DAILY",
        horizon=HORIZON,
        sample_origin="FORWARD_PRECOMMITTED",
        label_window_id=target,
        label_window_start=window_start,
        label_window_end=window_end,
        forecast_origin=now,
        feature_cutoff_timestamp=snapshot.available_at,
        build_id=build_fingerprint()["build_id"],
        model=MODEL_NAME,
        model_version=MODEL_VERSION,
        v2_schema_versions=schemas,
        sequence_id=f"{MODEL_NAME}|{target}|{snapshot.contract_code}",
        source_snapshot_ids=snapshot.source_snapshot_ids,
    )
    artifact = PA.ForecastArtifactRecord(
        **{
            **template.model_dump(),
            "prediction_id": pred.prediction_id,
        }
    )
    db.append_prediction_bundle(pred, [lineage], [artifact])
    return ForwardCycleResult(
        status=STATUS_PRECOMMITTED,
        prediction_id=pred.prediction_id,
        forecast_artifact_id=artifact.forecast_artifact_id,
        input_trading_date=snapshot.trading_date,
        target_trading_date=target,
        forecast_origin=now,
        label_window_start=window_start,
        label_window_end=window_end,
    )


def _outcome_blockers(
    pred: PA.PredictionRecord,
    lineage: list[PA.FactorLineageRecord],
    snapshot: OsakaForwardOutcome,
    now: datetime,
) -> list[str]:
    now = _utc(now)
    blockers: list[str] = []
    if pred.sample_origin != "FORWARD_PRECOMMITTED":
        blockers.append("NOT_FORWARD_PRECOMMITTED")
    if pred.label_window_end is None or pred.label_window_start is None or not pred.label_window_id:
        blockers.append("SEALED_LABEL_WINDOW_REQUIRED")
        return blockers
    if snapshot.trading_date != pred.label_window_id:
        blockers.append("TARGET_TRADING_DATE_MISMATCH")
    if snapshot.availability_status != "AVAILABLE":
        blockers.append("NOT_AVAILABLE")
    if not snapshot.point_in_time_safe:
        blockers.append("POINT_IN_TIME_UNSAFE")
    if not snapshot.source_snapshot_ids:
        blockers.append("SOURCE_SNAPSHOT_IDS_REQUIRED")
    if snapshot.series_semantics != "CONTRACT":
        blockers.append("SERIES_NOT_CONTRACT")
    if snapshot.roll_status != "NONE":
        blockers.append("ROLL_STATUS_NOT_NONE")
    if not snapshot.contract_code or not snapshot.contract_month:
        blockers.append("CONTRACT_IDENTITY_REQUIRED")
    if not snapshot.provider or not snapshot.data_grade:
        blockers.append("SOURCE_PROVENANCE_REQUIRED")
    expected_end = _ose_close_utc(pred.label_window_id)
    if _utc(snapshot.session_close_timestamp) != expected_end:
        blockers.append("SESSION_CLOSE_TIMESTAMP_MISMATCH")
    if _utc(snapshot.available_at) < expected_end:
        blockers.append("OUTCOME_AVAILABLE_BEFORE_CLOSE")
    if _utc(snapshot.available_at) > now:
        blockers.append("OUTCOME_NOT_YET_AVAILABLE")
    if now < _utc(pred.label_window_end):
        blockers.append("HORIZON_NOT_MATURE")
    contract_lineage = [x for x in lineage if x.representation_id == REPRESENTATION_ID]
    if len(contract_lineage) != 1:
        blockers.append("PREDICTION_LINEAGE_SCOPE_INVALID")
    else:
        lin = contract_lineage[0]
        if lin.contract_code != snapshot.contract_code or lin.contract_month != snapshot.contract_month:
            blockers.append("OUTCOME_CONTRACT_MISMATCH")
        if lin.series_semantics != "CONTRACT" or lin.roll_status != "NONE":
            blockers.append("PREDICTION_CONTRACT_PROVENANCE_INVALID")
    return blockers


def settle_osaka_terminal_close(
    prediction_id: str,
    snapshot: OsakaForwardOutcome,
    *,
    db: PA.PredictionAuditDB | None = None,
) -> ForwardCycleResult:
    """Append a terminal close only after the sealed horizon is mature."""
    db = db or PA.PredictionAuditDB()
    pred = db.get_prediction(prediction_id)
    if pred is None:
        return ForwardCycleResult(status=STATUS_NOT_FOUND, reason="prediction not found", prediction_id=prediction_id)

    if db.get_outcomes(prediction_id):
        out = db.get_outcomes(prediction_id)[0]
        return ForwardCycleResult(
            status=STATUS_ALREADY_SETTLED,
            reason="prediction already has an outcome",
            prediction_id=prediction_id,
            outcome_id=out.outcome_id,
            target_trading_date=pred.label_window_id,
            forecast_origin=pred.forecast_origin,
            label_window_start=pred.label_window_start,
            label_window_end=pred.label_window_end,
        )

    artifacts = db.get_forecast_artifacts(prediction_id)
    if len(artifacts) != 1 or artifacts[0].artifact_type != ARTIFACT_TYPE or artifacts[0].label_type != LABEL_TYPE:
        return ForwardCycleResult(
            status=STATUS_BLOCKED,
            reason="prediction does not have exactly one W3.2 terminal POINT artifact",
            prediction_id=prediction_id,
        )

    now = _now_utc()
    blockers = _outcome_blockers(pred, db.get_lineage(prediction_id), snapshot, now)
    if blockers:
        status = STATUS_NOT_MATURE if "HORIZON_NOT_MATURE" in blockers else STATUS_OUTCOME_NOT_ELIGIBLE
        return ForwardCycleResult(
            status=status,
            reason=";".join(sorted(set(blockers))),
            prediction_id=prediction_id,
            forecast_artifact_id=artifacts[0].forecast_artifact_id,
            target_trading_date=pred.label_window_id,
            forecast_origin=pred.forecast_origin,
            label_window_start=pred.label_window_start,
            label_window_end=pred.label_window_end,
        )

    outcome = PA.make_outcome(
        prediction_id=prediction_id,
        label_type=LABEL_TYPE,
        outcome_kind=OUTCOME_KIND,
        target_period=pred.label_window_id,
        actual_value=float(snapshot.close),
        event_timestamp=snapshot.session_close_timestamp,
        available_at=snapshot.available_at,
        label_schema_version=W3_FORWARD_CYCLE_SCHEMA_VERSION,
        source_snapshot_ids=snapshot.source_snapshot_ids,
        notes="W3.2 verified contract terminal close",
        forecast_artifact_id=artifacts[0].forecast_artifact_id,
    )
    db.append_outcome(outcome)
    return ForwardCycleResult(
        status=STATUS_SETTLED,
        prediction_id=prediction_id,
        forecast_artifact_id=artifacts[0].forecast_artifact_id,
        outcome_id=outcome.outcome_id,
        target_trading_date=pred.label_window_id,
        forecast_origin=pred.forecast_origin,
        label_window_start=pred.label_window_start,
        label_window_end=pred.label_window_end,
    )


def build_forward_evaluation(
    *,
    evaluation_as_of: datetime,
    window_start: datetime,
    window_end: datetime,
    db: PA.PredictionAuditDB | None = None,
) -> tuple[EG.GovernedEvaluationManifest, Any, dict[str, Any]]:
    """Build/evaluate only this W3.2 forward scope; never calibration fitting."""
    db = db or PA.PredictionAuditDB(read_only=True)
    prediction_ids: list[str] = []
    for pid in db.list_prediction_ids():
        pred = db.get_prediction(pid)
        if pred is None:
            continue
        if (
            pred.target_family == TARGET_FAMILY
            and pred.instrument == INSTRUMENT
            and pred.horizon == HORIZON
            and pred.model == MODEL_NAME
            and pred.model_version == MODEL_VERSION
            and pred.sample_origin == "FORWARD_PRECOMMITTED"
        ):
            prediction_ids.append(pid)
    manifest = EG.build_governed_evaluation_dataset(
        db,
        prediction_ids=prediction_ids,
        evaluation_as_of=evaluation_as_of,
        target_family=TARGET_FAMILY,
        instrument=INSTRUMENT,
        horizon=HORIZON,
        model=MODEL_NAME,
        model_version=MODEL_VERSION,
        artifact_type=ARTIFACT_TYPE,
        partition_role="FORWARD",
        window_start=window_start,
        window_end=window_end,
        label_type=LABEL_TYPE,
        sample_origin="FORWARD_PRECOMMITTED",
    )
    result = EG.evaluate_governed_manifest(db, manifest)
    readiness = EG.governance_readiness(manifest)
    readiness.update({
        "forward_cycle_schema_version": W3_FORWARD_CYCLE_SCHEMA_VERSION,
        "model": MODEL_NAME,
        "model_version": MODEL_VERSION,
        "target_family": TARGET_FAMILY,
        "horizon": HORIZON,
        "PREDICTIVE_EVIDENCE": "NOT_ESTABLISHED",
        "TRADING_EDGE": "NOT_ESTABLISHED",
    })
    return manifest, result, readiness


def osaka_forward_input_from_feature_store(
    *,
    as_of: datetime,
    contract_code: str,
    store: Any | None = None,
) -> tuple[OsakaForwardInput | None, dict[str, Any]]:
    """Read one eligible DAILY contract-close candidate from the canonical Feature Store.

    The adapter is read-only and never creates/migrates a Feature Store. It reuses
    W2's model-input gate, then requires the exact latest lineage snapshot so that
    trading date, available_at, contract month, roll and source IDs are not inferred.

    Current broker TICK observations therefore return INCOMPATIBLE_FREQUENCY rather
    than being silently resampled into a daily bar.
    """
    from market_ai_hub.feature_store.model_input import build_model_input
    from market_ai_hub.feature_store.store import FeatureStore

    cutoff = _utc(as_of)
    fs = store or FeatureStore()
    bundle = build_model_input(
        REPRESENTATION_ID,
        as_of=cutoff,
        contract_code=str(contract_code or "").strip(),
        requested_frequency=SOURCE_FREQUENCY,
        min_points=1,
        feature_name=FORWARD_DAILY_FEATURE_NAME,
        feature_version=FORWARD_DAILY_FEATURE_VERSION,
        store=fs,
    )
    public = bundle.public_status()
    public.update({
        "forward_cycle_schema_version": W3_FORWARD_CYCLE_SCHEMA_VERSION,
        "forward_input_status": "NOT_READY",
        "values_exposed": False,
    })
    if bundle.status != "READY" or bundle.series is None or not bundle.lineage_ids:
        return None, public

    latest_lineage_id = str(bundle.lineage_ids[-1])
    rows = fs.latest_observations(
        as_of=cutoff,
        representation_ids=[REPRESENTATION_ID],
        limit=max(100, bundle.row_count + 20),
    )
    row = next((
        item for item in rows
        if str(item.get("lineage_id") or "") == latest_lineage_id
        and str(item.get("contract_code") or "") == bundle.contract_code
    ), None)
    if row is None:
        public.update({
            "status": "LINEAGE_NOT_FOUND",
            "reason": "latest model-input lineage snapshot not found",
        })
        return None, public

    event_raw = row.get("event_timestamp")
    available_raw = row.get("available_at")
    if not event_raw or not available_raw:
        public.update({
            "status": "PROVENANCE_INCOMPLETE",
            "reason": "event_timestamp/available_at required",
        })
        return None, public

    snapshot = OsakaForwardInput(
        trading_date=str(row.get("trading_date") or ""),
        close=float(row.get("value")),
        session_close_timestamp=pd.Timestamp(event_raw).to_pydatetime(),
        available_at=pd.Timestamp(available_raw).to_pydatetime(),
        source_snapshot_ids=list(row.get("source_snapshot_ids") or []),
        provider=str(row.get("provider") or ""),
        source_type=str(row.get("source_type") or "DAILY_BAR_CLOSE"),
        data_grade=str(row.get("data_grade") or ""),
        quality_status=str(row.get("quality_status") or "UNKNOWN"),
        availability_status=str(row.get("availability_status") or "UNKNOWN"),
        point_in_time_safe=bool(row.get("point_in_time_safe")),
        contract_code=str(row.get("contract_code") or ""),
        contract_month=str(row.get("contract_month") or ""),
        roll_status=str(row.get("roll_status") or "UNKNOWN"),
        series_semantics=str(row.get("series_semantics") or "UNKNOWN"),
        source_frequency=str(row.get("source_frequency") or ""),
    )
    public.update({
        "forward_input_status": "CANDIDATE",
        "trading_date": snapshot.trading_date,
        "lineage_id": latest_lineage_id,
        "source_snapshot_ids": list(snapshot.source_snapshot_ids),
    })
    return snapshot, public


def precommit_osaka_from_feature_store(
    *,
    contract_code: str,
    db: PA.PredictionAuditDB | None = None,
    store: Any | None = None,
) -> ForwardCycleResult:
    """Operational read-from-Feature-Store precommit. No eligible input => no write."""
    now = _now_utc()
    snapshot, status = osaka_forward_input_from_feature_store(
        as_of=now,
        contract_code=contract_code,
        store=store,
    )
    if snapshot is None:
        return ForwardCycleResult(
            status=STATUS_INPUT_NOT_ELIGIBLE,
            reason=f"{status.get('status', 'NOT_READY')}:{status.get('reason', '')}".rstrip(":"),
            forecast_origin=now,
        )
    return precommit_osaka_last_price(snapshot, db=db)


def osaka_forward_outcome_from_feature_store(
    prediction_id: str,
    *,
    as_of: datetime,
    db: PA.PredictionAuditDB | None = None,
    store: Any | None = None,
) -> tuple[OsakaForwardOutcome | None, dict[str, Any]]:
    """Read the exact target-session terminal close for a W3.2 prediction."""
    audit = db or PA.PredictionAuditDB(read_only=True)
    pred = audit.get_prediction(prediction_id)
    if pred is None:
        return None, {
            "status": STATUS_NOT_FOUND,
            "reason": "prediction not found",
            "forward_outcome_status": "NOT_READY",
            "values_exposed": False,
        }
    lineage = [x for x in audit.get_lineage(prediction_id) if x.representation_id == REPRESENTATION_ID]
    if len(lineage) != 1 or not lineage[0].contract_code:
        return None, {
            "status": STATUS_BLOCKED,
            "reason": "prediction contract lineage unavailable",
            "forward_outcome_status": "NOT_READY",
            "values_exposed": False,
        }
    candidate, status = osaka_forward_input_from_feature_store(
        as_of=as_of,
        contract_code=lineage[0].contract_code,
        store=store,
    )
    status = dict(status)
    status["forward_outcome_status"] = "NOT_READY"
    if candidate is None:
        return None, status
    if candidate.trading_date != pred.label_window_id:
        status.update({
            "status": "TARGET_OUTCOME_NOT_AVAILABLE",
            "reason": (
                f"latest eligible daily close is {candidate.trading_date!r}; "
                f"target is {pred.label_window_id!r}"
            ),
        })
        return None, status
    outcome = OsakaForwardOutcome(
        trading_date=candidate.trading_date,
        close=candidate.close,
        session_close_timestamp=candidate.session_close_timestamp,
        available_at=candidate.available_at,
        source_snapshot_ids=candidate.source_snapshot_ids,
        provider=candidate.provider,
        source_type=candidate.source_type,
        data_grade=candidate.data_grade,
        quality_status=candidate.quality_status,
        availability_status=candidate.availability_status,
        point_in_time_safe=candidate.point_in_time_safe,
        contract_code=candidate.contract_code,
        contract_month=candidate.contract_month,
        roll_status=candidate.roll_status,
        series_semantics=candidate.series_semantics,
    )
    status["forward_outcome_status"] = "CANDIDATE"
    return outcome, status


def settle_osaka_from_feature_store(
    prediction_id: str,
    *,
    db: PA.PredictionAuditDB | None = None,
    store: Any | None = None,
) -> ForwardCycleResult:
    """Operational settlement from Feature Store. No eligible target close => no write."""
    audit = db or PA.PredictionAuditDB()
    now = _now_utc()
    snapshot, status = osaka_forward_outcome_from_feature_store(
        prediction_id,
        as_of=now,
        db=audit,
        store=store,
    )
    if snapshot is None:
        return ForwardCycleResult(
            status=STATUS_OUTCOME_NOT_ELIGIBLE,
            reason=f"{status.get('status', 'NOT_READY')}:{status.get('reason', '')}".rstrip(":"),
            prediction_id=prediction_id,
        )
    return settle_osaka_terminal_close(prediction_id, snapshot, db=audit)


def legacy_osaka_daily_source_readiness(path: str | Path | None = None) -> dict[str, Any]:
    """Metadata-only check of the old continuous daily parquet.

    This function never converts the legacy file into forward evidence. It exists
    to make today's blocker explicit and machine-readable.
    """
    from market_ai_hub.config.runtime_paths import data_root

    p = Path(path) if path is not None else (
        data_root() / "normalized" / "ose_micro" / "ose_micro_daily_bar_v1.parquet"
    )
    if not p.is_file():
        return {
            "status": "NOT_AVAILABLE",
            "reason": "legacy Osaka daily parquet not found",
            "path": str(p),
            "forward_eligible": False,
        }
    frame = pd.read_parquet(p)
    cols = {str(x) for x in frame.columns}
    latest = ""
    if "trading_date" in cols and len(frame):
        latest = str(pd.to_datetime(frame["trading_date"]).max().date())
    blockers = []
    if "available_at" not in cols:
        blockers.append("AVAILABLE_AT_MISSING")
    if "source_snapshot_ids" not in cols:
        blockers.append("SOURCE_SNAPSHOT_IDS_MISSING")
    if "contract_code" not in cols:
        blockers.append("CONTRACT_CODE_MISSING")
    if "contract_month" not in cols:
        blockers.append("CONTRACT_MONTH_MISSING")
    if "roll_status" not in cols:
        blockers.append("ROLL_PROVENANCE_MISSING")
    return {
        "status": "BLOCKED_FORWARD_INPUT" if blockers else "CANDIDATE_ONLY",
        "reason": ";".join(blockers),
        "path": str(p),
        "rows": int(len(frame)),
        "latest_trading_date": latest,
        "forward_eligible": False,
        "values_exposed": False,
    }
