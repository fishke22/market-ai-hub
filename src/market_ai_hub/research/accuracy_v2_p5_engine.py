"""Accuracy v2 P5 real-forward publication monitor.

P5 extends the existing append-only PredictionAuditDB instead of creating a parallel
ledger. It freezes point/interval/quantile artifacts at origin and only appends later
official outcomes. It never promotes models, calibrates probabilities, trades, or
touches broker/recorder state.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
import math
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

from market_ai_hub.config.runtime_paths import data_root
from market_ai_hub.integrations.yuanta.resolver import ose_last_trading_date
from market_ai_hub.research.accuracy_v2_p1 import jpx_report_publication_for_session
from market_ai_hub.research.accuracy_v2_p2_engine import build_p2_samples
from market_ai_hub.research.accuracy_v2_p4_engine import analyze_no_new_forward_outcome
from market_ai_hub.research.accuracy_v2_p5 import P5Protocol, load_p5_protocol
from market_ai_hub.research.future_data_acquisition import collect_public_sources
from market_ai_hub.research.v2 import prediction_audit as PA
from market_ai_hub.services.build_info import build_fingerprint
from market_ai_hub.services.calendar import is_ose_derivatives_session, next_ose_derivatives_session
from market_ai_hub.services.jnu_direct import (
    load_current_micro_settlement_receipts,
    load_direct_micro_settlements,
)

P5_ENGINE_SCHEMA_VERSION = "AV2P5E.1"
TARGET_FAMILY = "OSAKA_MICRO"
INSTRUMENT = "JNU"
CALENDAR_ID = "OSE_DERIVATIVES"
REPRESENTATION_ID = "OSE_MICRO_FUTURES"
ECONOMIC_FACTOR_ID = "JP_EQUITY"
VENUE_ID = "OSE_DERIVATIVES"
MODEL_NAME = "accuracy_v2_p4_baseline"
MODEL_VERSION = "accuracy-v2-p5-publication-v1"
HORIZON = "NEXT_PUBLISHED_OBSERVATION"
LABEL_TYPE = "PUBLISHED_SETTLEMENT_PRICE"
SAMPLE_ORIGIN = "FORWARD_PRECOMMITTED"
JST = ZoneInfo("Asia/Tokyo")

STATUS_PRECOMMITTED = "PRECOMMITTED"
STATUS_ALREADY_PRECOMMITTED = "ALREADY_PRECOMMITTED"
STATUS_SETTLED = "SETTLED"
STATUS_ALREADY_SETTLED = "ALREADY_SETTLED"
STATUS_WAITING = "WAITING_FOR_ORIGIN"
STATUS_BEFORE_START = "BEFORE_FIRST_ELIGIBLE_ORIGIN"
STATUS_MISSED = "MISSED_CANONICAL_ORIGIN"
STATUS_DATA_NOT_READY = "DATA_NOT_READY"
STATUS_ABSTAIN = "ABSTAIN"
STATUS_BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class P5CycleResult:
    status: str
    reason: str = ""
    prediction_id: str = ""
    target_session_date: str = ""
    reference_session_date: str = ""
    exact_contract: str = ""
    nominal_origin: datetime | None = None
    actual_origin: datetime | None = None
    label_available_at: datetime | None = None
    artifact_count: int = 0
    outcome_count: int = 0
    canonical: bool = False
    values_exposed: bool = False

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("timezone-aware datetime required")
    return value.astimezone(timezone.utc)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _jst_close(session_date: str | date) -> datetime:
    d = pd.Timestamp(session_date).date()
    return datetime.combine(d, time(15, 45), tzinfo=JST).astimezone(timezone.utc)


def _source_snapshot_id(source_hash: str) -> str:
    value = str(source_hash or "").strip()
    if not value:
        raise ValueError("source_hash required")
    return "jpx-settlement:" + value


def _contract_code(month: str) -> str:
    value = str(month or "")
    if len(value) != 6 or not value.isdigit():
        raise ValueError("exact YYYYMM contract month required")
    return "JNU" + value[2:]


def _first_eligible_date(protocol: P5Protocol) -> date:
    return pd.Timestamp(protocol.raw["origin"]["first_eligible_publication_date"]).date()


def _nominal_origin(reference_session_date: str, protocol: P5Protocol) -> datetime:
    return (
        jpx_report_publication_for_session(reference_session_date)
        + timedelta(minutes=5)
    ).astimezone(timezone.utc)


def _target_window(reference_session_date: str) -> tuple[str, datetime, datetime]:
    target = next_ose_derivatives_session(reference_session_date)
    if not target:
        raise ValueError("next OSE session unavailable")
    publication = jpx_report_publication_for_session(target).astimezone(timezone.utc)
    return target, publication, publication + timedelta(seconds=1)


def _reference_receipt(
    *,
    contract_month: str,
    reference_date: str,
    receipts: pd.DataFrame,
) -> dict[str, Any] | None:
    if receipts.empty:
        return None
    frame = receipts[
        receipts["contract_month"].astype(str).eq(str(contract_month))
        & receipts["date"].astype(str).eq(str(reference_date))
    ].copy()
    if frame.empty:
        return None
    values = sorted(set(float(x) for x in frame["settlement"].tolist()))
    if len(values) != 1:
        raise ValueError("REFERENCE_REVISION_CONFLICT")
    frame = frame.sort_values(["_received_at", "source_hash"])
    row = frame.iloc[0]
    return {
        "date": str(row["date"]),
        "contract_month": str(row["contract_month"]),
        "settlement": float(row["settlement"]),
        "received_at": pd.Timestamp(row["_received_at"]).to_pydatetime().astimezone(timezone.utc),
        "source_hash": str(row["source_hash"]),
        "source_url": str(row.get("source_url") or ""),
        "source_path": str(row.get("_source_path") or ""),
    }


def _latest_reference(*, receipts: pd.DataFrame, contract_month: str) -> dict[str, Any] | None:
    if receipts.empty:
        return None
    frame = receipts[receipts["contract_month"].astype(str).eq(str(contract_month))].copy()
    if frame.empty:
        return None
    latest_date = str(frame["date"].astype(str).max())
    return _reference_receipt(
        contract_month=contract_month,
        reference_date=latest_date,
        receipts=frame,
    )


def _select_contract_month(receipts: pd.DataFrame) -> str:
    if receipts.empty:
        return ""
    latest_date = str(receipts["date"].astype(str).max())
    latest = receipts[receipts["date"].astype(str).eq(latest_date)]
    months = sorted(
        m for m in latest["contract_month"].astype(str).unique()
        if len(m) == 6 and m.isdigit()
    )
    target = next_ose_derivatives_session(latest_date)
    if not target:
        return ""
    target_date = pd.Timestamp(target).date()
    for month in months:
        expiry = ose_last_trading_date(int(month[:4]), int(month[4:]))
        if target_date <= expiry:
            return month
    return ""


def _p5_scope(pred: PA.PredictionRecord) -> bool:
    return (
        pred.target_family == TARGET_FAMILY
        and pred.instrument == INSTRUMENT
        and pred.horizon == HORIZON
        and pred.model == MODEL_NAME
        and pred.model_version == MODEL_VERSION
        and pred.sample_origin == SAMPLE_ORIGIN
    )


def _prediction_contract(db: PA.PredictionAuditDB, prediction_id: str) -> tuple[str, str]:
    lineage = [x for x in db.get_lineage(prediction_id) if x.representation_id == REPRESENTATION_ID]
    if len(lineage) != 1:
        return "", ""
    return lineage[0].contract_code, lineage[0].contract_month


def _find_existing(
    db: PA.PredictionAuditDB,
    *,
    target_session: str,
    contract_code: str,
) -> PA.PredictionRecord | None:
    matches: list[PA.PredictionRecord] = []
    for pid in db.list_prediction_ids():
        pred = db.get_prediction(pid)
        if pred is None or not _p5_scope(pred) or pred.label_window_id != target_session:
            continue
        code, _ = _prediction_contract(db, pid)
        if code == contract_code:
            matches.append(pred)
    if not matches:
        return None
    return sorted(matches, key=lambda x: (x.forecast_origin, x.prediction_id))[0]


def _build_artifacts(
    robust: dict[str, Any],
    *,
    generated_at: datetime,
    snapshot_ids: list[str],
) -> list[PA.ForecastArtifactRecord]:
    reference = float((robust.get("point_reference") or {}).get("price"))
    if not math.isfinite(reference) or reference <= 0:
        raise ValueError("P5 point reference invalid")
    artifacts = [
        PA.make_forecast_artifact(
            prediction_id="",
            artifact_type="POINT",
            calibration_domain="PRICE",
            label_type=LABEL_TYPE,
            value=reference,
            units="index_points",
            status="OK",
            calibration_status_at_origin="NOT_APPLICABLE",
            generated_at=generated_at,
            source_snapshot_ids=snapshot_ids,
        )
    ]
    interval = robust.get("empirical_interval") or {}
    if (
        interval.get("status") == "DEVELOPMENT_FIT_UNVALIDATED_FORWARD"
        and interval.get("lower_price") is not None
        and interval.get("upper_price") is not None
    ):
        lower = float(interval["lower_price"])
        upper = float(interval["upper_price"])
        nominal = float(interval.get("nominal_coverage") or 0.90)
        if math.isfinite(lower) and math.isfinite(upper) and lower <= upper:
            artifacts.append(
                PA.make_forecast_artifact(
                    prediction_id="",
                    artifact_type="INTERVAL",
                    calibration_domain="PRICE",
                    label_type=LABEL_TYPE,
                    lower_value=lower,
                    upper_value=upper,
                    nominal_coverage=nominal,
                    units="index_points",
                    status="OK",
                    calibration_status_at_origin="UNCALIBRATED",
                    generated_at=generated_at,
                    source_snapshot_ids=snapshot_ids,
                )
            )
    quantile = robust.get("lightgbm_quantile_challenger") or {}
    prices = quantile.get("price_quantiles") or {}
    raw = [prices.get("q10"), prices.get("q50"), prices.get("q90")]
    if quantile.get("status") == "CHALLENGER_UNVALIDATED" and all(v is not None for v in raw):
        q = [float(v) for v in raw]
        if all(math.isfinite(v) for v in q) and q[0] <= q[1] <= q[2]:
            for level, value in zip((0.10, 0.50, 0.90), q):
                artifacts.append(
                    PA.make_forecast_artifact(
                        prediction_id="",
                        artifact_type="QUANTILE",
                        calibration_domain="PRICE",
                        label_type=LABEL_TYPE,
                        value=value,
                        quantile_level=level,
                        units="index_points",
                        status="OK",
                        calibration_status_at_origin="UNCALIBRATED",
                        generated_at=generated_at,
                        source_snapshot_ids=snapshot_ids,
                    )
                )
    return artifacts


def preview_p5_origin(
    *,
    now: datetime | None = None,
    protocol: P5Protocol | None = None,
    receipts: pd.DataFrame | None = None,
    contract_month: str = "",
) -> dict[str, Any]:
    p = protocol or load_p5_protocol()
    as_of = _aware(now or _now_utc())
    frame = load_current_micro_settlement_receipts(contract_month) if receipts is None else receipts.copy()
    if frame.empty:
        return {"status": STATUS_DATA_NOT_READY, "reason": "NO_RECEIPT_TIMESTAMPED_SETTLEMENT"}
    if not contract_month:
        contract_month = _select_contract_month(frame)
        if not contract_month:
            return {"status": STATUS_DATA_NOT_READY, "reason": "NO_UNEXPIRED_EXACT_CONTRACT"}
    reference = _latest_reference(receipts=frame, contract_month=contract_month)
    if reference is None:
        return {"status": STATUS_DATA_NOT_READY, "reason": "NO_EXACT_REFERENCE_RECEIPT"}
    reference_date = reference["date"]
    nominal = _nominal_origin(reference_date, p)
    target, _, label_end = _target_window(reference_date)
    base = {
        "reference_session_date": reference_date,
        "target_session_date": target,
        "contract_month": contract_month,
        "exact_contract": _contract_code(contract_month),
        "reference_received_at": reference["received_at"].isoformat(),
        "nominal_origin": nominal.isoformat(),
        "label_available_at": label_end.isoformat(),
        "values_exposed": False,
    }
    if nominal.astimezone(JST).date() < _first_eligible_date(p):
        return {**base, "status": STATUS_BEFORE_START}
    if as_of < nominal:
        return {**base, "status": STATUS_WAITING}
    lateness = (as_of - nominal).total_seconds() / 60.0
    if lateness > float(p.raw["origin"]["canonical_max_lateness_minutes"]):
        return {**base, "status": STATUS_MISSED, "lateness_minutes": lateness}
    if reference["received_at"] > as_of:
        return {**base, "status": STATUS_DATA_NOT_READY, "reason": "REFERENCE_RECEIVED_AFTER_ORIGIN"}
    age = (as_of - reference["received_at"]).total_seconds() / 60.0
    if age > float(p.raw["downgrade"]["current_reference_max_age_minutes"]):
        return {**base, "status": STATUS_ABSTAIN, "reason": "STALE_REFERENCE", "reference_age_minutes": age}
    return {
        **base,
        "status": "ELIGIBLE",
        "reference_age_minutes": age,
        "lateness_minutes": lateness,
    }


def _preview_result(preview: dict[str, Any], as_of: datetime, fallback_code: str = "") -> P5CycleResult:
    return P5CycleResult(
        status=str(preview.get("status")),
        reason=str(preview.get("reason") or ""),
        target_session_date=str(preview.get("target_session_date") or ""),
        reference_session_date=str(preview.get("reference_session_date") or ""),
        exact_contract=str(preview.get("exact_contract") or fallback_code),
        nominal_origin=(
            pd.Timestamp(preview["nominal_origin"]).to_pydatetime()
            if preview.get("nominal_origin") else None
        ),
        actual_origin=as_of,
        label_available_at=(
            pd.Timestamp(preview["label_available_at"]).to_pydatetime()
            if preview.get("label_available_at") else None
        ),
        canonical=False,
    )


def precommit_p5_forward(
    *,
    now: datetime | None = None,
    db: PA.PredictionAuditDB | None = None,
    protocol: P5Protocol | None = None,
    current_series: pd.Series | None = None,
    current_meta: dict[str, Any] | None = None,
    receipts: pd.DataFrame | None = None,
    robust_analysis: dict[str, Any] | None = None,
) -> P5CycleResult:
    p = protocol or load_p5_protocol()
    as_of = _aware(now or _now_utc())
    audit = db or PA.PredictionAuditDB()
    if current_series is None or current_meta is None:
        frame = load_current_micro_settlement_receipts("") if receipts is None else receipts.copy()
        preview = preview_p5_origin(now=as_of, protocol=p, receipts=frame)
        if preview.get("status") != "ELIGIBLE":
            return _preview_result(preview, as_of)
        contract_month = str(preview["contract_month"])
        series, meta = load_direct_micro_settlements(contract_month)
    else:
        series, meta = current_series.copy(), dict(current_meta)
        contract_month = str(meta.get("contract_month") or "")
        frame = (
            load_current_micro_settlement_receipts(contract_month)
            if receipts is None else receipts.copy()
        )
        preview = preview_p5_origin(
            now=as_of,
            protocol=p,
            receipts=frame,
            contract_month=contract_month,
        )
        if preview.get("status") != "ELIGIBLE":
            return _preview_result(preview, as_of, str(meta.get("quote_code") or ""))
    if meta.get("status") != "OK":
        return P5CycleResult(
            status=STATUS_DATA_NOT_READY,
            reason=str(meta.get("status") or "NO_HISTORY"),
        )
    reference = _reference_receipt(
        contract_month=contract_month,
        reference_date=str(preview["reference_session_date"]),
        receipts=frame,
    )
    if reference is None:
        return P5CycleResult(status=STATUS_DATA_NOT_READY, reason="REFERENCE_RECEIPT_DISAPPEARED")
    contract_code = str(preview["exact_contract"])
    expiry = ose_last_trading_date(int(contract_month[:4]), int(contract_month[4:]))
    if pd.Timestamp(preview["target_session_date"]).date() > expiry:
        return P5CycleResult(
            status=STATUS_ABSTAIN,
            reason="TARGET_AFTER_CONTRACT_EXPIRY",
            target_session_date=str(preview["target_session_date"]),
            exact_contract=contract_code,
        )
    existing = _find_existing(
        audit,
        target_session=str(preview["target_session_date"]),
        contract_code=contract_code,
    )
    if existing is not None:
        return P5CycleResult(
            status=STATUS_ALREADY_PRECOMMITTED,
            prediction_id=existing.prediction_id,
            target_session_date=existing.label_window_id,
            reference_session_date=str(preview["reference_session_date"]),
            exact_contract=contract_code,
            nominal_origin=pd.Timestamp(preview["nominal_origin"]).to_pydatetime(),
            actual_origin=existing.forecast_origin,
            label_available_at=existing.label_window_end,
            artifact_count=len(audit.get_forecast_artifacts(existing.prediction_id)),
            canonical=True,
        )
    robust = robust_analysis or analyze_no_new_forward_outcome(
        current_series=series,
        current_meta=meta,
    )
    if robust.get("status") != "OK":
        return P5CycleResult(
            status=STATUS_DATA_NOT_READY,
            reason="P4_ANALYSIS:" + str(robust.get("status")),
            target_session_date=str(preview["target_session_date"]),
            reference_session_date=str(preview["reference_session_date"]),
            exact_contract=contract_code,
        )
    snapshot_ids = [_source_snapshot_id(reference["source_hash"])]
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
        trading_date=reference["date"],
        event_timestamp=_jst_close(reference["date"]),
        available_at=reference["received_at"],
        provider_timestamp=None,
        received_at=reference["received_at"],
        timestamp_precision="OFFICIAL_SETTLEMENT_OBSERVATION",
        staleness_status="FRESH_AT_FORECAST_ORIGIN",
        availability_status="AVAILABLE",
        quality_status="OFFICIAL_RECEIPT_CAPTURED",
        provider="JPX",
        source_type="JPX_OFFICIAL_SETTLEMENT_CSV",
        source_frequency="DAILY",
        data_grade="OFFICIAL_DAILY",
        point_in_time_safe=True,
        contract_code=contract_code,
        contract_month=contract_month,
        roll_status="NONE",
        series_semantics="CONTRACT",
        source_snapshot_ids=snapshot_ids,
    )
    artifacts = _build_artifacts(robust, generated_at=as_of, snapshot_ids=snapshot_ids)
    label_end = pd.Timestamp(preview["label_available_at"]).to_pydatetime()
    label_start = label_end - timedelta(seconds=1)
    pred = PA.make_prediction(
        [lineage],
        artifacts,
        target_family=TARGET_FAMILY,
        instrument=INSTRUMENT,
        instrument_role="DIRECT",
        calendar_id=CALENDAR_ID,
        frequency="DAILY_PUBLICATION",
        horizon=HORIZON,
        sample_origin=SAMPLE_ORIGIN,
        label_window_id=str(preview["target_session_date"]),
        label_window_start=label_start,
        label_window_end=label_end,
        forecast_origin=as_of,
        feature_cutoff_timestamp=reference["received_at"],
        build_id=build_fingerprint()["build_id"],
        model=MODEL_NAME,
        model_version=MODEL_VERSION,
        v2_schema_versions=PA.v2_schema_versions(),
        state_snapshot_id="p5_protocol:" + p.hash,
        sequence_id="P5|CANONICAL|%s|%s|%s" % (
            preview["target_session_date"], contract_code, reference["date"]
        ),
        source_snapshot_ids=snapshot_ids,
    )
    bound_artifacts = [
        PA.ForecastArtifactRecord(**{**a.model_dump(), "prediction_id": pred.prediction_id})
        for a in artifacts
    ]
    audit.append_prediction_bundle(pred, [lineage], bound_artifacts)
    return P5CycleResult(
        status=STATUS_PRECOMMITTED,
        prediction_id=pred.prediction_id,
        target_session_date=pred.label_window_id,
        reference_session_date=reference["date"],
        exact_contract=contract_code,
        nominal_origin=pd.Timestamp(preview["nominal_origin"]).to_pydatetime(),
        actual_origin=as_of,
        label_available_at=label_end,
        artifact_count=len(bound_artifacts),
        canonical=True,
    )


def settle_p5_pending(
    *,
    now: datetime | None = None,
    db: PA.PredictionAuditDB | None = None,
    receipts: pd.DataFrame | None = None,
) -> list[P5CycleResult]:
    as_of = _aware(now or _now_utc())
    audit = db or PA.PredictionAuditDB()
    frame = load_current_micro_settlement_receipts("") if receipts is None else receipts.copy()
    results: list[P5CycleResult] = []
    for pid in audit.list_prediction_ids():
        pred = audit.get_prediction(pid)
        if pred is None or not _p5_scope(pred):
            continue
        artifacts = audit.get_forecast_artifacts(pid)
        if not artifacts:
            results.append(P5CycleResult(status=STATUS_BLOCKED, reason="PREDICTION_HAS_NO_ARTIFACTS", prediction_id=pid))
            continue
        contract_code, contract_month = _prediction_contract(audit, pid)
        target = pred.label_window_id
        try:
            target_row = _reference_receipt(
                contract_month=contract_month,
                reference_date=target,
                receipts=frame,
            )
        except ValueError:
            results.append(P5CycleResult(
                status=STATUS_BLOCKED,
                reason="OUTCOME_REVISION_CONFLICT",
                prediction_id=pid,
                target_session_date=target,
                exact_contract=contract_code,
            ))
            continue
        if target_row is None or target_row["received_at"] > as_of:
            results.append(P5CycleResult(
                status=STATUS_WAITING,
                reason="TARGET_SETTLEMENT_NOT_RECEIVED",
                prediction_id=pid,
                target_session_date=target,
                exact_contract=contract_code,
            ))
            continue
        if pred.label_window_end is None or target_row["received_at"] < pred.label_window_end:
            results.append(P5CycleResult(
                status=STATUS_WAITING,
                reason="TARGET_RECEIPT_BEFORE_LABEL_AVAILABLE",
                prediction_id=pid,
                target_session_date=target,
                exact_contract=contract_code,
            ))
            continue
        snapshot_ids = [_source_snapshot_id(target_row["source_hash"])]
        existing = audit.get_outcomes(pid)
        existing_by_art = {o.forecast_artifact_id: o for o in existing if o.forecast_artifact_id}
        conflict = False
        inserted = 0
        for art in artifacts:
            prior = existing_by_art.get(art.forecast_artifact_id)
            if prior is not None:
                if prior.actual_value is not None and not math.isclose(
                    float(prior.actual_value), float(target_row["settlement"]),
                    rel_tol=0.0, abs_tol=1e-12,
                ):
                    conflict = True
                continue
            outcome = PA.make_outcome(
                prediction_id=pid,
                label_type=art.label_type,
                outcome_kind="TERMINAL",
                target_period=target,
                actual_value=float(target_row["settlement"]),
                event_timestamp=_jst_close(target),
                available_at=target_row["received_at"],
                label_schema_version="AV2P5.1",
                source_snapshot_ids=snapshot_ids,
                notes="P5 official JPX published settlement receipt",
                forecast_artifact_id=art.forecast_artifact_id,
            )
            audit.append_outcome(outcome)
            inserted += 1
        total = len(audit.get_outcomes(pid))
        results.append(P5CycleResult(
            status=STATUS_BLOCKED if conflict else (STATUS_SETTLED if inserted else STATUS_ALREADY_SETTLED),
            reason="OUTCOME_REVISION_CONFLICT_PRESERVE_FIRST" if conflict else "",
            prediction_id=pid,
            target_session_date=target,
            exact_contract=contract_code,
            outcome_count=total,
            canonical=True,
        ))
    return results


def _pinball(y: float, q: float, tau: float) -> float:
    e = y - q
    return float(max(tau * e, (tau - 1.0) * e))


def _development_baseline_mae() -> float | None:
    try:
        samples = build_p2_samples()
    except Exception:
        return None
    values = [
        abs(float(s.target_return))
        for s in samples
        if s.partition == "DEVELOPMENT" and math.isfinite(float(s.target_return))
    ]
    return float(np.mean(values)) if values else None


def _expected_origins(as_of: datetime, protocol: P5Protocol) -> list[str]:
    as_of = _aware(as_of)
    start = _first_eligible_date(protocol)
    scan_start = start - timedelta(days=10)
    scan_end = as_of.astimezone(JST).date()
    origins: set[str] = set()
    for day in pd.date_range(scan_start, scan_end, freq="D"):
        source_date = day.date()
        if not is_ose_derivatives_session(source_date):
            continue
        try:
            nominal = _nominal_origin(source_date.isoformat(), protocol)
        except Exception:
            continue
        if nominal.astimezone(JST).date() < start or nominal > as_of:
            continue
        origins.add(nominal.isoformat())
    return sorted(origins)


def p5_forward_evidence_summary(
    *,
    now: datetime | None = None,
    db: PA.PredictionAuditDB | None = None,
    protocol: P5Protocol | None = None,
) -> dict[str, Any]:
    p = protocol or load_p5_protocol()
    as_of = _aware(now or _now_utc())
    if db is not None:
        audit: PA.PredictionAuditDB | None = db
    else:
        audit_path = PA.default_audit_db_path()
        audit = PA.PredictionAuditDB(audit_path, read_only=True) if audit_path.exists() else None
    predictions = (
        [
            pred for pid in audit.list_prediction_ids()
            if (pred := audit.get_prediction(pid)) is not None and _p5_scope(pred)
        ]
        if audit is not None else []
    )
    predictions.sort(key=lambda x: (x.forecast_origin, x.prediction_id))
    expected = _expected_origins(as_of, p)
    origin_coverage = float(len(predictions) / len(expected)) if expected else None

    point_errors: list[float] = []
    interval_rows: list[dict[str, float]] = []
    quantile_rows: list[dict[str, float]] = []
    settled_predictions = 0
    for pred in predictions:
        artifacts = audit.get_forecast_artifacts(pred.prediction_id)
        outcomes = audit.get_outcomes(pred.prediction_id)
        bound = {
            o.forecast_artifact_id: o for o in outcomes
            if o.forecast_artifact_id and o.actual_value is not None
        }
        point = next((a for a in artifacts if a.artifact_type == "POINT"), None)
        if point is None or point.forecast_artifact_id not in bound:
            continue
        actual = float(bound[point.forecast_artifact_id].actual_value)
        reference = float(point.value)
        if not (math.isfinite(actual) and math.isfinite(reference) and reference > 0):
            continue
        settled_predictions += 1
        actual_return = actual / reference - 1.0
        point_errors.append(abs(actual_return))
        interval = next((a for a in artifacts if a.artifact_type == "INTERVAL"), None)
        if interval is not None and interval.forecast_artifact_id in bound:
            lower = float(interval.lower_value)
            upper = float(interval.upper_value)
            nominal = float(interval.nominal_coverage)
            covered = float(lower <= actual <= upper)
            width_return = (upper - lower) / reference
            alpha = 1.0 - nominal
            score = width_return
            actual_rel = actual / reference
            lower_rel, upper_rel = lower / reference, upper / reference
            if actual_rel < lower_rel:
                score += (2.0 / alpha) * (lower_rel - actual_rel)
            elif actual_rel > upper_rel:
                score += (2.0 / alpha) * (actual_rel - upper_rel)
            interval_rows.append({"covered": covered, "width_return": width_return, "score": score})
        qs = sorted(
            [a for a in artifacts if a.artifact_type == "QUANTILE"],
            key=lambda a: float(a.quantile_level or -1),
        )
        if len(qs) == 3 and all(q.forecast_artifact_id in bound for q in qs):
            levels = [float(q.quantile_level) for q in qs]
            q_returns = [float(q.value) / reference - 1.0 for q in qs]
            quantile_rows.append({
                "q10_loss": _pinball(actual_return, q_returns[0], levels[0]),
                "q50_loss": _pinball(actual_return, q_returns[1], levels[1]),
                "q90_loss": _pinball(actual_return, q_returns[2], levels[2]),
                "q50_abs_error": abs(actual_return - q_returns[1]),
                "point_abs_error": abs(actual_return),
                "covered": float(q_returns[0] <= actual_return <= q_returns[2]),
                "crossing": float(not (q_returns[0] <= q_returns[1] <= q_returns[2])),
            })

    downgrade: list[str] = []
    dcfg = p.raw["downgrade"]
    origin_cfg = dcfg["origin_coverage"]
    if len(expected) >= int(origin_cfg["minimum_expected_origins_before_check"]):
        if origin_coverage is None or origin_coverage < float(origin_cfg["minimum_canonical_origin_coverage"]):
            downgrade.append(str(origin_cfg["failure_action"]))
    interval_cfg = dcfg["interval"]
    if len(interval_rows) >= int(interval_cfg["minimum_settled_before_check"]):
        rows = interval_rows[-int(interval_cfg["rolling_window_origins"]):]
        if float(np.mean([x["covered"] for x in rows])) < float(interval_cfg["minimum_acceptable_coverage"]):
            downgrade.append(str(interval_cfg["failure_action"]))
    point_cfg = dcfg["point_error"]
    dev_mae = (
        _development_baseline_mae()
        if len(point_errors) >= int(point_cfg["minimum_settled_before_check"])
        else None
    )
    if len(point_errors) >= int(point_cfg["minimum_settled_before_check"]) and dev_mae is not None:
        rows = point_errors[-int(point_cfg["rolling_window_origins"]):]
        if float(np.mean(rows)) > dev_mae * float(point_cfg["compare_to_development_mae_multiplier"]):
            downgrade.append(str(point_cfg["failure_action"]))

    evidence_state = (
        "COLLECTING_FORWARD_EVIDENCE"
        if settled_predictions < int(p.raw["forward_evaluation"]["minimum_settled_canonical_origins"])
        else "FORWARD_EVALUATION_READY_NO_AUTOMATIC_PROMOTION"
    )
    interval_metrics = {
        "sample_count": len(interval_rows),
        "empirical_coverage": float(np.mean([x["covered"] for x in interval_rows])) if interval_rows else None,
        "mean_width_return": float(np.mean([x["width_return"] for x in interval_rows])) if interval_rows else None,
        "mean_interval_score": float(np.mean([x["score"] for x in interval_rows])) if interval_rows else None,
    }
    quantile_metrics = {
        "sample_count": len(quantile_rows),
        "pinball_q10": float(np.mean([x["q10_loss"] for x in quantile_rows])) if quantile_rows else None,
        "pinball_q50": float(np.mean([x["q50_loss"] for x in quantile_rows])) if quantile_rows else None,
        "pinball_q90": float(np.mean([x["q90_loss"] for x in quantile_rows])) if quantile_rows else None,
        "q10_q90_coverage": float(np.mean([x["covered"] for x in quantile_rows])) if quantile_rows else None,
        "quantile_crossing_rate": float(np.mean([x["crossing"] for x in quantile_rows])) if quantile_rows else None,
        "q50_mae_return": float(np.mean([x["q50_abs_error"] for x in quantile_rows])) if quantile_rows else None,
        "same_origin_point_mae_return": float(np.mean([x["point_abs_error"] for x in quantile_rows])) if quantile_rows else None,
    }
    quantile_metrics["q50_minus_point_mae_return"] = (
        quantile_metrics["q50_mae_return"] - quantile_metrics["same_origin_point_mae_return"]
        if quantile_rows else None
    )
    return {
        "schema_version": P5_ENGINE_SCHEMA_VERSION,
        "protocol_id": p.protocol_id,
        "protocol_hash": p.hash,
        "as_of": as_of.isoformat(),
        "expected_canonical_origins": len(expected),
        "canonical_prediction_count": len(predictions),
        "canonical_origin_coverage": origin_coverage,
        "settled_canonical_origin_count": settled_predictions,
        "point_mae_return": float(np.mean(point_errors)) if point_errors else None,
        "development_baseline_mae_return": dev_mae,
        "interval": interval_metrics,
        "quantile": quantile_metrics,
        "downgrade_reasons": sorted(set(downgrade)),
        "downgrade_state": "BASELINE_ONLY_DEGRADED" if downgrade else "NORMAL_BASELINE_MONITOR",
        "evidence_state": evidence_state,
        "PREDICTIVE_GAIN": False,
        "CALIBRATED": False,
        "TRADING_EDGE": False,
        "automatic_model_promotion": False,
        "strong_direction_allowed": False,
    }


def _state_path(protocol: P5Protocol) -> Path:
    return data_root() / Path(str(protocol.raw["collector"]["state_file"]))


def _read_state(protocol: P5Protocol) -> dict[str, Any]:
    import json

    path = _state_path(protocol)
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def _next_attempt(as_of: datetime, protocol: P5Protocol) -> tuple[bool, int, str]:
    local_date = _aware(as_of).astimezone(ZoneInfo("Asia/Taipei")).date().isoformat()
    previous = _read_state(protocol)
    count = (
        int(previous.get("attempt_count", 0) or 0)
        if previous.get("local_date") == local_date
        else 0
    )
    maximum = int(protocol.raw["collector"]["max_attempts_per_local_date"])
    if count >= maximum:
        return False, count, local_date
    return True, count + 1, local_date


def _write_state(payload: dict[str, Any], protocol: P5Protocol) -> Path:
    import json

    path = _state_path(protocol)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str, indent=2),
        encoding="utf-8",
    )
    tmp.replace(path)
    return path


def run_p5_cycle(
    *,
    now: datetime | None = None,
    db: PA.PredictionAuditDB | None = None,
    collect: bool = True,
    protocol: P5Protocol | None = None,
) -> dict[str, Any]:
    p = protocol or load_p5_protocol()
    as_of = _aware(now or _now_utc())
    allowed, attempt_count, local_date = _next_attempt(as_of, p)
    if not allowed:
        payload = {
            "schema_version": "AV2P5RUN.1",
            "as_of": as_of.isoformat(),
            "local_date": local_date,
            "attempt_count": attempt_count,
            "status": "ATTEMPT_LIMIT",
            "collection": {"status": "SKIPPED_ATTEMPT_LIMIT"},
            "settlements": [],
            "precommit": P5CycleResult(status=STATUS_BLOCKED, reason="MAX_ATTEMPTS_PER_LOCAL_DATE").model_dump(),
            "evidence": p5_forward_evidence_summary(now=as_of, db=db, protocol=p),
            "broker_used": False,
            "credentials_used": False,
            "recorder_touched": False,
            "order_action": False,
        }
        payload["state_file"] = str(_write_state(payload, p))
        return payload
    collection = collect_public_sources() if collect else {
        "status": "SKIPPED",
        "broker_used": False,
        "credentials_used": False,
        "recorder_touched": False,
        "order_action": False,
    }
    audit = db or PA.PredictionAuditDB()
    settled = settle_p5_pending(now=as_of, db=audit)

    from market_ai_hub.services.data_continuity import jnu_data_continuity_status
    continuity = jnu_data_continuity_status(now=as_of)
    if continuity.get("context_only"):
        precommit = P5CycleResult(
            status=STATUS_DATA_NOT_READY,
            reason="DATA_CONTINUITY_MODE:" + str(
                continuity.get("reason") or "EXACT_TARGET_NOT_READY"
            ),
        )
    else:
        precommit = precommit_p5_forward(now=as_of, db=audit, protocol=p)

    evidence = p5_forward_evidence_summary(now=as_of, db=audit, protocol=p)
    payload = {
        "schema_version": "AV2P5RUN.1",
        "as_of": as_of.isoformat(),
        "local_date": local_date,
        "attempt_count": attempt_count,
        "collection": collection,
        "data_continuity": continuity,
        "settlements": [x.model_dump() for x in settled],
        "precommit": precommit.model_dump(),
        "evidence": evidence,
        "broker_used": False,
        "credentials_used": False,
        "recorder_touched": False,
        "order_action": False,
    }
    payload["state_file"] = str(_write_state(payload, p))
    return payload
