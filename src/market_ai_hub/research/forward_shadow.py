"""Phase 2V-D — Forward Shadow (research forecast tracking, NOT trading).

Creates immutable VAR(1) + baseline forecasts into the Prediction Registry,
and settles them with actuals (append-only). No PnL, no position, no order.

Forecasts are RESEARCH_FORECAST_ONLY / NON_EXECUTABLE_FORECAST_EDGE.
"""
from __future__ import annotations

import json
import hashlib
from datetime import datetime, timezone, timedelta

import numpy as np
import pandas as pd

from market_ai_hub.config.settings import project_root
from market_ai_hub.research.registry import PredictionRegistry
from market_ai_hub.research.schemas import OutcomeRecord, PredictionRecord
from market_ai_hub.services.build_info import build_fingerprint

COHORT_VAR = "VAR_V1_FORWARD"
COHORT_LAST = "LAST_VALUE_FORWARD"
COHORT_ZERO = "ZERO_RETURN_FORWARD"
HORIZONS = [1, 3, 5]

BARS_PATH = project_root() / "data" / "normalized" / "ose_micro" / "ose_micro_daily_bar_v1.parquet"
ACTIVATION_PATH = project_root() / "research/phase2/manifests/FORWARD_SHADOW_ACTIVATION.yaml"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def load_bars() -> pd.DataFrame:
    if not BARS_PATH.exists():
        raise FileNotFoundError(f"Micro bars not found: {BARS_PATH}")
    df = pd.read_parquet(BARS_PATH).sort_values("trading_date")
    return df


def var_forecast_price(closes: pd.Series, horizon: int) -> float:
    """VAR(1) AR(1) on close-to-close returns; returns forecast price for next `horizon` bars."""
    ret = closes.pct_change().dropna()
    if len(ret) < 3:
        return float(closes.iloc[-1])
    x = ret.shift(1).dropna().values
    y = ret.iloc[1:].values
    b = float(np.corrcoef(x, y)[0, 1]) if len(x) > 2 else 0.0
    a = float(y.mean() - b * x.mean())
    last = float(closes.iloc[-1])
    r = float(ret.iloc[-1])
    pred = last
    for _ in range(horizon):
        r = a + b * r
        pred *= (1 + r)
    return pred


def create_daily_forecasts() -> dict:
    """Generate VAR + baselines forecasts for the next trading day(s), append to registry."""
    bars = load_bars()
    closes = bars.set_index("trading_date")["close"].astype(float)
    origin_date = closes.index[-1]
    origin_price = float(closes.iloc[-1])
    cutoff = pd.Timestamp(origin_date).to_pydatetime().replace(tzinfo=timezone.utc)
    fp = build_fingerprint()
    reg = PredictionRegistry()

    # data freshness gate: skip if last bar is stale (> 7 calendar days before now)
    age_days = (_now_utc() - cutoff).total_seconds() / 86400
    if age_days > 7:
        return {
            "origin": str(origin_date.date()),
            "created": [],
            "status": "FORECAST_SKIPPED_DATA_QUALITY",
            "reason": f"target source stale: last bar {origin_date.date()}, {age_days:.0f} days old",
        }

    created = []
    for h in HORIZONS:
        # VAR forecast
        var_price = var_forecast_price(closes, h)
        var_ret = (var_price - origin_price) / origin_price if origin_price else 0.0
        var_dir = "up" if var_ret > 0 else ("down" if var_ret < 0 else "flat")

        # baselines (same origin)
        last_price = origin_price
        last_ret = 0.0
        zero_price = origin_price
        zero_ret = 0.0

        for cohort, price, ret, direction in [
            (COHORT_VAR, var_price, var_ret, var_dir),
            (COHORT_LAST, last_price, last_ret, "flat"),
            (COHORT_ZERO, zero_price, zero_ret, "flat"),
        ]:
            fid = f"fs_{cohort}_{origin_date.strftime('%Y%m%d')}_h{h}"
            rec = PredictionRecord(
                forecast_id=fid,
                created_at=_now_utc(),
                information_cutoff=cutoff,
                market="OSE",
                target="OSE_NIKKEI225_MICRO_CONTINUOUS_BAR",
                instrument="Nikkei 225 Micro (225LABO continuous)",
                horizon=f"{h}d",
                forecast_origin=cutoff,
                forecast_target_dates=[(pd.Timestamp(origin_date) + pd.Timedelta(days=h)).strftime("%Y-%m-%d")],
                exchange_calendar="OSE_APPROX",
                model_name=cohort,
                model_task="PRICE_FORECAST",
                model_revision="VAR_V1_FORWARD" if cohort == COHORT_VAR else "baseline",
                model_build_id=fp["build_id"],
                training_cutoff=cutoff,
                dataset_version="ose_micro_daily_bar_v1",
                feature_version="v1",
                point_forecast=price,
                origin_price=origin_price,
                direction=direction,
                engineering_status="PASS",
                predictive_validation_status="FORWARD_SHADOW",
                regime_as_known_at_prediction_time="UNKNOWN",
                data_quality_state="RESEARCH_FORECAST_ONLY",
            )
            try:
                reg.register(rec)
                created.append(fid)
            except ValueError:
                # already registered (idempotent re-run)
                pass

    return {"origin": str(origin_date.date()), "created": created}


def settle_pending() -> dict:
    """Settle pending forecasts whose target bar is now available (append-only)."""
    bars = load_bars()
    closes = bars.set_index("trading_date")["close"].astype(float)
    reg = PredictionRegistry()
    pending = reg.list_predictions(settled=False, limit=10000)

    settled = []
    for p in pending:
        fid = p["forecast_id"]
        origin = p.get("forecast_origin")
        if origin is None or pd.isna(pd.Timestamp(origin)):
            continue  # old prediction without origin timestamp, not forward-shadow
        # parse horizon integer
        h_str = p.get("horizon", "1d").replace("d", "")
        try:
            h = int(h_str)
        except ValueError:
            continue
        # find origin index and target (normalize origin to date to handle tz round-trip)
        origin_dt = pd.Timestamp(origin).normalize()
        if origin_dt not in closes.index:
            continue
        idx = closes.index.get_loc(origin_dt)
        target_idx = idx + h
        if target_idx >= len(closes):
            continue  # target bar not yet available
        actual = float(closes.iloc[target_idx])
        actual_ts = pd.Timestamp(closes.index[target_idx]).to_pydatetime().replace(tzinfo=timezone.utc)
        origin_price = float(p.get("origin_price") or 0.0)
        pred = float(p.get("point_forecast") or 0.0)
        err = actual - pred
        abs_err = abs(err)
        sq_err = err * err
        # direction: compare sign of forecast return vs actual return
        pred_ret = (pred - origin_price) / origin_price if origin_price else 0.0
        act_ret = (actual - origin_price) / origin_price if origin_price else 0.0
        dir_result = "correct" if (pred_ret >= 0) == (act_ret >= 0) else "incorrect"
        outcome = OutcomeRecord(
            forecast_id=fid, actual=actual, actual_timestamp=actual_ts,
            absolute_error=abs_err, squared_error=sq_err, direction_result=dir_result,
        )
        try:
            reg.settle(outcome)
            settled.append(fid)
        except ValueError:
            pass  # already settled

    return {"settled": settled}


def build_status() -> dict:
    """Aggregate forward shadow status/metrics into research/phase2/status/FORWARD_SHADOW_STATUS.json."""
    import yaml

    reg = PredictionRegistry()
    preds = reg.list_predictions(limit=100000)
    act = _load_activation()

    settled = [p for p in preds if p.get("settled")]
    pending = [p for p in preds if not p.get("settled")]

    def _cohort_metrics(cohort):
        rows = [p for p in settled if p.get("model_name") == cohort]
        return _metrics(rows)

    # coverage / forward-origin tracking
    bars = load_bars()
    latest_market_date = str(pd.Timestamp(bars["trading_date"].max()).date()) if len(bars) else None
    data_age_days = None
    if latest_market_date:
        data_age_days = round((_now_utc() - pd.Timestamp(latest_market_date).to_pydatetime().replace(tzinfo=timezone.utc)).total_seconds() / 86400, 1)
    activation_ts = act.get("activated_at", "")
    # forward forecasts = created after activation (origin >= activation date)
    forward_created = 0
    for p in preds:
        created = p.get("created_at")
        if created is not None and activation_ts:
            c = pd.Timestamp(created)
            a = pd.Timestamp(activation_ts)
            if c.tzinfo is not None:
                c = c.tz_localize(None)
            if a.tzinfo is not None:
                a = a.tz_localize(None)
            if c >= a:
                forward_created += 1

    status = {
        "activation": activation_ts,
        "days_active": 0,
        "latest_market_date": latest_market_date,
        "data_age_days": data_age_days,
        "next_target_date": None,
        "forecasts_created": len(preds),
        "pending": len(pending),
        "settled": len(settled),
        "skipped": 0,
        "forward_origins_expected": 0,
        "forward_origins_created": forward_created,
        "forward_origins_missed": 0,
        "models": {
            "VAR_V1_FORWARD": _cohort_metrics(COHORT_VAR),
            "LAST_VALUE_FORWARD": _cohort_metrics(COHORT_LAST),
            "ZERO_RETURN_FORWARD": _cohort_metrics(COHORT_ZERO),
        },
        "label": "RESEARCH_FORECAST_ONLY / NON_EXECUTABLE_FORECAST_EDGE",
        "generated_at": _now_utc().isoformat(),
    }
    out = project_root() / "research/phase2/status/FORWARD_SHADOW_STATUS.json"
    out.write_text(json.dumps(status, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    return status


def _metrics(rows):
    if not rows:
        return {"n": 0, "label": "TOO_EARLY"}
    n = len(rows)
    errs = [r.get("absolute_error") for r in rows if r.get("absolute_error") is not None]
    dirs = [r.get("direction_result") for r in rows if r.get("direction_result")]
    mae = float(np.mean(errs)) if errs else None
    dir_acc = float(np.mean([1 if d == "correct" else 0 for d in dirs])) if dirs else None
    label = _small_n_label(n)
    return {"n": n, "mae": mae, "direction_accuracy": dir_acc, "label": label}


def _small_n_label(n):
    if n < 20: return "TOO_EARLY"
    if n < 40: return "EARLY_FORWARD"
    if n < 80: return "PRELIMINARY_FORWARD"
    if n < 150: return "MODERATE_FORWARD"
    return "SUBSTANTIAL_FORWARD"


def _load_activation():
    import yaml
    if ACTIVATION_PATH.exists():
        return yaml.safe_load(ACTIVATION_PATH.read_text(encoding="utf-8")) or {}
    return {}


def init_activation() -> dict:
    """Create activation marker (once). Forward evidence only counts after this timestamp."""
    import yaml
    fp = build_fingerprint()
    act = {
        "activated_at": _now_utc().isoformat(),
        "build_id": fp["build_id"],
        "protocol_version": 1,
        "cohort": COHORT_VAR,
        "model_version": "VAR_V1_FORWARD",
        "note": "Forward evidence only counts for forecasts created AFTER activated_at. Historical dates are REPLAY, never FORWARD.",
    }
    ACTIVATION_PATH.write_text(yaml.safe_dump(act, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return act
