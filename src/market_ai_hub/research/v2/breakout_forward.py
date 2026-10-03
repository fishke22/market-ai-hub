"""W3.4 — preregistered pattern hypothesis: new-high + volume expansion → positive continuation.

RESEARCH ONLY / HYPOTHESIS_ONLY. The frozen protocol is
``research/phase3/JNU_NH_VOL_BREAKOUT_PREREGISTRATION_v1.yaml`` (protocol id
``JNU-NH-VOL-BREAKOUT-1``); a change to any parameter/definition/policy requires a new
protocol file with an incremented version. This module enforces the frozen rule, it does
not document it as an aspiration.

Governance mirrors the W3.2 forward cycle:
- trigger inputs are official, already-collected, past-only records (JPX settlement CSV /
  daily-report settlement history + JPX open-interest per-contract volume);
- predictions are written as ``FORWARD_PRECOMMITTED`` audit rows with one frozen,
  explicitly UNCALIBRATED ``EVENT_PROBABILITY`` artifact per horizon (value 0.5 = a
  stance constant, never a fitted probability);
- outcomes are binary TERMINAL labels (strictly-greater-than, tie = failure, mirroring
  W3.2-EP1) written only after the target session's official settlement is collected and
  the sealed label window has fully elapsed;
- nothing here promotes, calibrates, combines models, or produces trading advice.

The event can only be registered by the nightly JPX sync (first run at which both the
event-day settlement and the event-day volume are collected); a missed origin is recorded
and never reconstructed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from market_ai_hub.research.v2 import prediction_audit as PA
from market_ai_hub.services.build_info import build_fingerprint
from market_ai_hub.services.calendar import next_ose_derivatives_sessions

W34_SCHEMA_VERSION = "W3.4"
PRODUCER_SCHEMA_VERSION = "W3.4-EP1"
PROTOCOL_ID_FROZEN = "JNU-NH-VOL-BREAKOUT-1"
PROTOCOL_VERSION_FROZEN = 1

TARGET_FAMILY = "OSAKA_MICRO"
INSTRUMENT = "JNU"
REPRESENTATION_ID = "OSE_MICRO_FUTURES"
ECONOMIC_FACTOR_ID = "JP_EQUITY"
VENUE_ID = "OSE_DERIVATIVES"
CALENDAR_ID = "OSE_DERIVATIVES"
MICRO_PRODUCT = "Nikkei 225 Micro Futures"

MODEL_NAME = "nh_vol_breakout_positive_continuation"
MODEL_VERSION = "w3.4-ep1-hypothesis-1"
HORIZONS = ("5d", "20d")
EVENT_DEFINITION_IDS = {"5d": "NH_VOL_BREAKOUT_POSITIVE_5D", "20d": "NH_VOL_BREAKOUT_POSITIVE_20D"}
LABEL_TYPES = {"5d": "TERMINAL_POSITIVE_5D", "20d": "TERMINAL_POSITIVE_20D"}
EVENT_ARTIFACT_TYPE = "EVENT_PROBABILITY"
EVENT_CALIBRATION_DOMAIN = "PRICE_DISTRIBUTION"
EVENT_PROBABILITY_TYPE = "TERMINAL"
FROZEN_STANCE_VALUE = 0.5
DISTRIBUTION_ID = "frozen_constant_stance"
DISTRIBUTION_VERSION = "w3.4-ep1-1"

STATUS_PRECOMMITTED = "PRECOMMITTED"
STATUS_ALREADY_PRECOMMITTED = "ALREADY_PRECOMMITTED"
STATUS_NO_FIRE = "NO_FIRE"
STATUS_MISSED_ORIGIN = "MISSED_ORIGIN"

_JST = ZoneInfo("Asia/Tokyo")
_OSE_DAY_CLOSE = time(15, 45)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def load_breakout_protocol(path: Path | None = None) -> dict[str, Any]:
    """Load and validate the frozen preregistration document."""
    import yaml
    p = path or (_repo_root() / "research" / "phase3" / "JNU_NH_VOL_BREAKOUT_PREREGISTRATION_v1.yaml")
    protocol: dict[str, Any] = yaml.safe_load(p.read_text(encoding="utf-8"))
    if protocol.get("protocol_id") != PROTOCOL_ID_FROZEN:
        raise ValueError(f"unexpected protocol_id: {protocol.get('protocol_id')!r}")
    if int(protocol.get("protocol_version", -1)) != PROTOCOL_VERSION_FROZEN:
        raise ValueError(f"unexpected protocol_version: {protocol.get('protocol_version')!r}")
    frozen = frozen_params(protocol)
    if float(frozen["frozen_value"]) != FROZEN_STANCE_VALUE:
        raise ValueError("protocol frozen_value must equal the module stance constant")
    horizons = protocol["definition"]["horizons"]
    if sorted(h["horizon_code"] for h in horizons) != sorted(HORIZONS):
        raise ValueError("protocol horizons must be exactly the module HORIZONS")
    return protocol


def frozen_params(protocol: dict[str, Any] | None = None) -> dict[str, Any]:
    p = protocol or load_breakout_protocol()
    d = p["definition"]
    return {
        "lookback_sessions": int(d["event"]["new_high_lookback_sessions"]),
        "volume_mean_sessions": int(d["event"]["volume_mean_sessions"]),
        "volume_multiple": float(d["event"]["volume_multiple"]),
        "lateness_cap_days": int(d["origin"]["lateness_cap_days"]),
        "frozen_value": float(d["forecast"]["frozen_value"]),
        "protocol_id": str(p["protocol_id"]),
    }


# ── data lake loaders（past-only official records）─────────────────────────

def _data_root() -> Path:
    from market_ai_hub.automation.data_lake import default_data_root
    return default_data_root()


def _date_norm(value: Any) -> str:
    return str(value)[:8].replace("-", "")


def load_settlement_history(contract_month: str) -> pd.DataFrame:
    """columns: date(YYYYMMDD), settlement(float), source('rb'|'daily'), source_hash(str)."""
    rows: list[dict[str, Any]] = []
    rb_base = _data_root() / "raw" / "jpx" / "settlement" / "OSE" / "all"
    if rb_base.exists():
        for p in rb_base.rglob("rb*.parquet"):
            df = pd.read_parquet(p)
            df = df[df["product"] == MICRO_PRODUCT]
            df = df[df["contract"].astype(str) == str(contract_month)]
            for _, r in df.iterrows():
                rows.append({
                    "date": _date_norm(r["date"]),
                    "settlement": float(r["settlement_price"]),
                    "source": "rb",
                    "source_hash": str(r.get("source_hash") or ""),
                })
    daily_base = _data_root() / "raw" / "jpx" / "ose_daily" / "OSE" / "Nikkei 225 Micro"
    if daily_base.exists():
        for p in daily_base.rglob("micro_settlement_*.parquet"):
            df = pd.read_parquet(p)
            df = df[df["contract_month"].astype(str) == str(contract_month)]
            for _, r in df.iterrows():
                if pd.isna(r.get("settlement")):
                    continue
                rows.append({
                    "date": _date_norm(r["date"]),
                    "settlement": float(r["settlement"]),
                    "source": "daily",
                    "source_hash": str(r.get("source_hash") or ""),
                })
    if not rows:
        return pd.DataFrame(columns=["date", "settlement", "source", "source_hash"])
    df = pd.DataFrame(rows)
    df["prio"] = df["source"].map({"rb": 0, "daily": 1})
    df = df.sort_values(["date", "prio"]).drop_duplicates("date", keep="first")
    return df[["date", "settlement", "source", "source_hash"]].sort_values("date").reset_index(drop=True)


def load_volume_history(contract_month: str) -> pd.DataFrame:
    """columns: date(YYYYMMDD), volume(float), source_url(str)."""
    rows: list[dict[str, Any]] = []
    base = _data_root() / "raw" / "jpx" / "open_interest" / "OSE" / "all"
    if base.exists():
        for p in base.rglob("open_interest_*.parquet"):
            df = pd.read_parquet(p)
            if "product" not in df.columns:
                continue
            df = df[df["product"].astype(str) == MICRO_PRODUCT]
            df = df[df["contract_month"].astype(str) == str(contract_month)]
            for _, r in df.iterrows():
                if pd.isna(r.get("volume")):
                    continue
                rows.append({
                    "date": _date_norm(r["date"]),
                    "volume": float(r["volume"]),
                    "source_url": str(r.get("source_url") or ""),
                })
    if not rows:
        return pd.DataFrame(columns=["date", "volume", "source_url"])
    df = pd.DataFrame(rows)
    df = df.drop_duplicates("date", keep="first")
    return df.sort_values("date").reset_index(drop=True)


# ── trigger（frozen W3.4 event condition）───────────────────────────────────

TRIGGER_FIRED = "FIRED"
TRIGGER_NO_EVENT_DAY = "EVENT_DAY_SETTLEMENT_NOT_AVAILABLE"
TRIGGER_WARMUP_SETTLEMENT = "WARMUP_INSUFFICIENT_SETTLEMENT"
TRIGGER_WARMUP_VOLUME = "WARMUP_INSUFFICIENT_VOLUME"
TRIGGER_VOLUME_MISSING = "VOLUME_MISSING_EVENT_DAY"
TRIGGER_NOT_NEW_HIGH = "NOT_NEW_HIGH"
TRIGGER_VOLUME_NOT_EXPANDED = "NOT_VOLUME_EXPANSION"


@dataclass(frozen=True)
class BreakoutTrigger:
    fired: bool
    reason: str = ""
    event_date: str = ""
    event_settlement: float = 0.0
    event_volume: float = 0.0
    volume_baseline: float = 0.0
    prior_high: float = 0.0
    source_snapshot_ids: tuple[str, ...] = field(default_factory=tuple)

    def model_dump(self) -> dict[str, Any]:
        return {
            "fired": self.fired,
            "reason": self.reason,
            "event_date": self.event_date,
            "event_settlement": self.event_settlement,
            "event_volume": self.event_volume,
            "volume_baseline": self.volume_baseline,
            "prior_high": self.prior_high,
        }


def evaluate_trigger(
    settlements: pd.DataFrame,
    volumes: pd.DataFrame,
    *,
    event_date: str,
    params: dict[str, Any],
) -> BreakoutTrigger:
    """Frozen event condition. All inputs must be dates <= event_date (past-only)."""
    s = settlements[settlements["date"] <= event_date].sort_values("date").reset_index(drop=True)
    event_row = s[s["date"] == event_date]
    if event_row.empty:
        return BreakoutTrigger(fired=False, reason=TRIGGER_NO_EVENT_DAY, event_date=event_date)
    lookback = int(params["lookback_sessions"])
    vol_win = int(params["volume_mean_sessions"])
    mult = float(params["volume_multiple"])

    prior = s[s["date"] < event_date]
    if len(prior) < lookback:
        return BreakoutTrigger(fired=False, reason=TRIGGER_WARMUP_SETTLEMENT,
                               event_date=event_date,
                               event_settlement=float(event_row.iloc[0]["settlement"]))
    window = prior.tail(lookback)
    prior_high = float(window["settlement"].max())
    event_settlement = float(event_row.iloc[0]["settlement"])
    if not (event_settlement > prior_high):
        return BreakoutTrigger(fired=False, reason=TRIGGER_NOT_NEW_HIGH,
                               event_date=event_date, event_settlement=event_settlement,
                               prior_high=prior_high)

    v = volumes[volumes["date"] <= event_date].sort_values("date").reset_index(drop=True)
    v_event = v[v["date"] == event_date]
    v_prior = v[v["date"] < event_date]
    if len(v_prior) < vol_win:
        return BreakoutTrigger(fired=False, reason=TRIGGER_WARMUP_VOLUME,
                               event_date=event_date, event_settlement=event_settlement,
                               prior_high=prior_high)
    if v_event.empty:
        return BreakoutTrigger(fired=False, reason=TRIGGER_VOLUME_MISSING,
                               event_date=event_date, event_settlement=event_settlement,
                               prior_high=prior_high)
    baseline = float(v_prior.tail(vol_win)["volume"].mean())
    event_volume = float(v_event.iloc[0]["volume"])
    if not (event_volume > 0 and event_volume > mult * baseline):
        return BreakoutTrigger(fired=False, reason=TRIGGER_VOLUME_NOT_EXPANDED,
                               event_date=event_date, event_settlement=event_settlement,
                               event_volume=event_volume, volume_baseline=baseline,
                               prior_high=prior_high)
    hashes = [str(h) for h in event_row["source_hash"].tolist() if str(h)]
    ids: list[str] = hashes or [f"rb_settlement:{event_date}"]
    ids.append(f"open_interest:{event_date}")
    return BreakoutTrigger(
        fired=True, reason=TRIGGER_FIRED, event_date=event_date,
        event_settlement=event_settlement, event_volume=event_volume,
        volume_baseline=baseline, prior_high=prior_high,
        source_snapshot_ids=tuple(sorted(set(ids))),
    )


# ── precommit / settle / summary ────────────────────────────────────────────

def _target_session_plan(event_date: str, sessions: int) -> tuple[str, datetime]:
    d = pd.Timestamp(f"{event_date[:4]}-{event_date[4:6]}-{event_date[6:8]}").date()
    targets = next_ose_derivatives_sessions(d, int(sessions))
    if not targets:
        raise ValueError(f"cannot project {sessions} sessions after {event_date}")
    target = pd.Timestamp(str(targets[-1])).strftime("%Y%m%d")  # 正規化 YYYYMMDD
    end = datetime.combine(pd.Timestamp(target).date(), _OSE_DAY_CLOSE, tzinfo=_JST)
    return target, end.astimezone(timezone.utc)


def _scope_predictions(
    db: PA.PredictionAuditDB,
    *,
    horizon: str,
    label_window_id: str,
    contract_code: str,
    contract_month: str,
) -> list[PA.PredictionRecord]:
    out: list[PA.PredictionRecord] = []
    for pid in db.list_prediction_ids():
        pred = db.get_prediction(pid)
        if pred is None or db.is_voided(pid):
            continue
        if not (pred.target_family == TARGET_FAMILY and pred.instrument == INSTRUMENT
                and pred.model == MODEL_NAME and pred.model_version == MODEL_VERSION
                and pred.horizon == horizon and pred.sample_origin == "FORWARD_PRECOMMITTED"
                and pred.label_window_id == label_window_id):
            continue
        lin = [x for x in db.get_lineage(pid) if x.representation_id == REPRESENTATION_ID]
        if len(lin) == 1 and lin[0].contract_code == contract_code \
                and lin[0].contract_month == contract_month:
            out.append(pred)
    return out


def precommit_breakout(
    trigger: BreakoutTrigger,
    *,
    horizon: str,
    contract_code: str,
    contract_month: str,
    db: PA.PredictionAuditDB | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    if horizon not in HORIZONS:
        raise ValueError(f"horizon must be one of {HORIZONS}")
    db = db or PA.PredictionAuditDB()
    now = now or _now_utc()
    label_id, window_end = _target_session_plan(trigger.event_date, int(horizon[:-1]))
    existing = _scope_predictions(
        db, horizon=horizon, label_window_id=label_id,
        contract_code=contract_code, contract_month=contract_month,
    )
    if existing:
        return {
            "status": STATUS_ALREADY_PRECOMMITTED,
            "prediction_id": existing[0].prediction_id,
            "horizon": horizon,
            "target_trading_date": label_id,
        }
    event_ts = datetime.combine(
        pd.Timestamp(f"{trigger.event_date[:4]}-{trigger.event_date[4:6]}-{trigger.event_date[6:8]}").date(),
        _OSE_DAY_CLOSE, tzinfo=_JST,
    ).astimezone(timezone.utc)
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
        trading_date=trigger.event_date,
        event_timestamp=event_ts,
        available_at=now,
        provider_timestamp=None,
        received_at=now,
        timestamp_precision="SESSION_DATE_ONLY",
        staleness_status="FRESH_AT_FORECAST_ORIGIN",
        availability_status="AVAILABLE",
        quality_status="RUNTIME_VERIFIED_OFFICIAL",
        provider="JPX_OSE",
        source_type="OFFICIAL_SETTLEMENT",
        source_frequency="DAILY",
        data_grade="OFFICIAL_DAILY",
        point_in_time_safe=True,
        contract_code=contract_code,
        contract_month=contract_month,
        roll_status="NONE",
        series_semantics="CONTRACT",
        source_snapshot_ids=list(trigger.source_snapshot_ids),
    )
    template = PA.make_forecast_artifact(
        prediction_id="",
        artifact_type=EVENT_ARTIFACT_TYPE,
        calibration_domain=EVENT_CALIBRATION_DOMAIN,
        probability_type=EVENT_PROBABILITY_TYPE,
        event_definition_id=EVENT_DEFINITION_IDS[horizon],
        event_threshold_value=float(trigger.event_settlement),
        label_type=LABEL_TYPES[horizon],
        value=float(FROZEN_STANCE_VALUE),
        raw_score=None,
        units="probability_stance",
        status="OK",
        calibration_status_at_origin="UNCALIBRATED",
        distribution_id=DISTRIBUTION_ID,
        distribution_version=DISTRIBUTION_VERSION,
        generated_at=now,
        source_snapshot_ids=list(trigger.source_snapshot_ids),
    )
    schemas = PA.v2_schema_versions()
    schemas["event_probability_producer"] = PRODUCER_SCHEMA_VERSION
    schemas["breakout_protocol_id"] = PROTOCOL_ID_FROZEN
    pred = PA.make_prediction(
        [lineage], [template],
        target_family=TARGET_FAMILY,
        instrument=INSTRUMENT,
        instrument_role="DIRECT",
        calendar_id=CALENDAR_ID,
        frequency="DAILY",
        horizon=horizon,
        sample_origin="FORWARD_PRECOMMITTED",
        label_window_id=label_id,
        label_window_start=now,
        label_window_end=window_end,
        forecast_origin=now,
        feature_cutoff_timestamp=now,
        build_id=build_fingerprint()["build_id"],
        model=MODEL_NAME,
        model_version=MODEL_VERSION,
        v2_schema_versions=schemas,
        sequence_id=f"{MODEL_NAME}|{horizon}|{trigger.event_date}|{contract_code}",
        source_snapshot_ids=list(trigger.source_snapshot_ids),
    )
    artifact = PA.ForecastArtifactRecord(**{**template.model_dump(), "prediction_id": pred.prediction_id})
    db.append_prediction_bundle(pred, [lineage], [artifact])
    return {
        "status": STATUS_PRECOMMITTED,
        "prediction_id": pred.prediction_id,
        "forecast_artifact_id": artifact.forecast_artifact_id,
        "horizon": horizon,
        "target_trading_date": label_id,
    }


def settle_breakout(*, db: PA.PredictionAuditDB | None = None,
                    now: datetime | None = None) -> list[dict[str, Any]]:
    db = db or PA.PredictionAuditDB()
    now = now or _now_utc()
    results: list[dict[str, Any]] = []
    for pid in db.list_prediction_ids():
        pred = db.get_prediction(pid)
        if pred is None or db.is_voided(pid):
            continue
        if not (pred.model == MODEL_NAME and pred.model_version == MODEL_VERSION
                and pred.sample_origin == "FORWARD_PRECOMMITTED"
                and pred.horizon in HORIZONS):
            continue
        lin = [x for x in db.get_lineage(pid) if x.representation_id == REPRESENTATION_ID]
        if len(lin) != 1:
            results.append({"status": "BLOCKED", "prediction_id": pid,
                            "reason": "lineage scope invalid"})
            continue
        art = [a for a in db.get_forecast_artifacts(pid)
               if a.artifact_type == EVENT_ARTIFACT_TYPE
               and a.event_definition_id == EVENT_DEFINITION_IDS[pred.horizon]
               and a.label_type == LABEL_TYPES[pred.horizon]]
        if len(art) != 1 or art[0].event_threshold_value is None:
            results.append({"status": "BLOCKED", "prediction_id": pid,
                            "reason": "event artifact missing or ambiguous"})
            continue
        if db.get_outcomes(pid):
            results.append({"status": "ALREADY_SETTLED", "prediction_id": pid})
            continue
        if pred.label_window_end is None or now < pred.label_window_end:
            results.append({"status": "NOT_MATURE", "prediction_id": pid})
            continue
        hist = load_settlement_history(lin[0].contract_month)
        row = hist[hist["date"] == str(pred.label_window_id)]
        if row.empty:
            results.append({"status": "OUTCOME_NOT_ELIGIBLE", "prediction_id": pid,
                            "reason": "TARGET_SETTLEMENT_NOT_AVAILABLE"})
            continue
        target_settlement = float(row.iloc[0]["settlement"])
        actual = 1.0 if target_settlement > float(art[0].event_threshold_value) else 0.0
        outcome = PA.make_outcome(
            prediction_id=pid,
            label_type=art[0].label_type,
            outcome_kind="TERMINAL",
            target_period=str(pred.label_window_id),
            actual_value=actual,
            event_timestamp=pred.label_window_end,
            available_at=now,
            label_schema_version=PRODUCER_SCHEMA_VERSION,
            source_snapshot_ids=[f"rb_settlement:{pred.label_window_id}"],
            notes=(f"target settlement {target_settlement} vs threshold "
                   f"{float(art[0].event_threshold_value)}"),
            forecast_artifact_id=art[0].forecast_artifact_id,
        )
        db.append_outcome(outcome)
        results.append({"status": "SETTLED", "prediction_id": pid, "actual": int(actual),
                        "horizon": pred.horizon,
                        "target_settlement": target_settlement})
    return results


def w34_evidence_summary(db: PA.PredictionAuditDB | None = None) -> dict[str, Any]:
    db = db or PA.PredictionAuditDB()
    per: dict[str, dict[str, Any]] = {}
    for h in HORIZONS:
        per[h] = {"registered": 0, "settled": 0, "hits": 0, "hit_rate": None}
    for pid in db.list_prediction_ids():
        pred = db.get_prediction(pid)
        if pred is None or db.is_voided(pid):
            continue
        if not (pred.model == MODEL_NAME and pred.model_version == MODEL_VERSION
                and pred.sample_origin == "FORWARD_PRECOMMITTED"
                and pred.horizon in HORIZONS):
            continue
        per[pred.horizon]["registered"] += 1
        outs = [
            o for o in db.get_outcomes(pid)
            if o.outcome_kind == "TERMINAL" and o.actual_value in (0, 0.0, 1, 1.0)
        ]
        if len(outs) == 1 and outs[0].label_type == LABEL_TYPES[pred.horizon]:
            per[pred.horizon]["settled"] += 1
            if float(outs[0].actual_value) == 1.0:
                per[pred.horizon]["hits"] += 1
    for h in HORIZONS:
        n = per[h]["settled"]
        per[h]["hit_rate"] = (per[h]["hits"] / n) if n else None
    return {
        "schema": W34_SCHEMA_VERSION,
        "protocol_id": PROTOCOL_ID_FROZEN,
        "status": "UNPROVEN",
        "promotion": "FORBIDDEN",
        "discussion_threshold_settled_origins": 20,
        "horizons": per,
        "values_exposed": False,
    }


# ── nightly-sync orchestrator ───────────────────────────────────────────────

def run_breakout_cycle(contract_code: str, *, db: PA.PredictionAuditDB | None = None) -> dict[str, Any]:
    """Settle matured predictions first, then evaluate the frozen trigger and precommit.

    The event date is the latest collected official settlement date; lateness beyond the
    frozen cap records MISSED_ORIGIN and registers nothing (no retroactive registration).
    """
    db = db or PA.PredictionAuditDB()
    now = _now_utc()
    protocol = load_breakout_protocol()
    params = frozen_params(protocol)
    if not re.fullmatch(r"JNU\d{4}", str(contract_code).upper()):
        raise ValueError("EXPECTED_EXACT_JNU_CONTRACT")
    contract_month = f"20{contract_code[3:5]}{contract_code[5:7]}"

    settled = settle_breakout(db=db, now=now)
    settlements = load_settlement_history(contract_month)
    volumes = load_volume_history(contract_month)
    latest = str(settlements["date"].max()) if not settlements.empty else ""

    trigger: BreakoutTrigger | None = None
    precommits: list[dict[str, Any]] = []
    reason = ""
    if not latest:
        reason = "NO_SETTLEMENT_DATA"
    else:
        event_d = pd.Timestamp(f"{latest[:4]}-{latest[4:6]}-{latest[6:8]}").date()
        lateness = (datetime.now(_JST).date() - event_d).days
        if lateness > int(params["lateness_cap_days"]):
            reason = f"{STATUS_MISSED_ORIGIN};lateness_days={lateness}"
    if not reason:
        trigger = evaluate_trigger(settlements, volumes, event_date=latest, params=params)
        if not trigger.fired:
            reason = trigger.reason
    if trigger is not None and trigger.fired:
        for h in HORIZONS:
            precommits.append(precommit_breakout(
                trigger, horizon=h, contract_code=contract_code,
                contract_month=contract_month, db=db, now=now,
            ))
    return {
        "schema": W34_SCHEMA_VERSION,
        "protocol_id": PROTOCOL_ID_FROZEN,
        "contract_code": contract_code,
        "contract_month": contract_month,
        "status": "FIRED" if (trigger and trigger.fired) else STATUS_NO_FIRE,
        "reason": reason,
        "lateness_cap_days": int(params["lateness_cap_days"]),
        "trigger": trigger.model_dump() if trigger else None,
        "settlements": settled,
        "precommits": precommits,
        "values_exposed": False,
    }