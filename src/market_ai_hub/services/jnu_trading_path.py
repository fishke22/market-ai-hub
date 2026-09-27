"""Read-only JNU trading-path decision support.

This module is deliberately separate from Accuracy v2 settlement forecasting.
It consumes only true OSE Nikkei 225 Micro quote observations and produces
descriptive session/market-structure context. It never places orders and never
promotes descriptive structure into predictive gain or calibrated probability.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
import math
import re
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import duckdb
import numpy as np
import pandas as pd

from market_ai_hub.config.runtime_paths import data_root
from market_ai_hub.integrations.yuanta.resolver import YuantaInstrumentResolver
from market_ai_hub.research.v2.session_truth import resolve_venue_session
from market_ai_hub.services.jnu_direct import load_direct_micro_settlements


SCHEMA_VERSION = "JNU.TRADING_PATH.1"
PRODUCT = "TRADING_PATH_DECISION_SUPPORT"
EVIDENCE_LEVEL = "DESCRIPTIVE_DECISION_SUPPORT_ONLY"
TICK_POINTS = 5.0
BAR_FREQUENCY = "5min"
MIN_STRUCTURE_TRADES = 30
MIN_STRUCTURE_BARS = 6
JST = ZoneInfo("Asia/Tokyo")
_QUOTE_RE = re.compile(r"^JNU(PM)?(?P<yymm>\d{4})$")


def _aware_utc(value: datetime | None) -> datetime:
    out = value or datetime.now(timezone.utc)
    if out.tzinfo is None or out.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return out.astimezone(timezone.utc)


def _contract_month(code: str) -> str:
    m = _QUOTE_RE.fullmatch(str(code or "").upper())
    if not m:
        return ""
    yymm = m.group("yymm")
    return f"20{yymm[:2]}{yymm[2:]}"


def _base_quote_code(code: str) -> str:
    text = str(code or "").upper()
    m = _QUOTE_RE.fullmatch(text)
    if not m:
        return ""
    return f"JNU{m.group('yymm')}"


def _session_variant(code: str) -> str:
    text = str(code or "").upper()
    if not _QUOTE_RE.fullmatch(text):
        return "UNKNOWN"
    return "NIGHT" if text.startswith("JNUPM") else "DAY"


def _parse_source_tod(value: Any) -> time | None:
    text = str(value or "").strip()
    if not text or text.lower() in {"nan", "none", "nat"}:
        return None
    for fmt in ("%H:%M:%S.%f", "%H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            continue
    return None


def _event_timestamp(received_at: Any, source_tod: Any) -> tuple[pd.Timestamp | None, str]:
    recv = pd.to_datetime(received_at, utc=True, errors="coerce")
    if pd.isna(recv):
        return None, "INVALID"
    tod = _parse_source_tod(source_tod)
    if tod is None:
        return recv, "LOCAL_RECEIVE_TIME_ONLY"
    local_recv = recv.tz_convert(JST)
    local_event = datetime.combine(local_recv.date(), tod, tzinfo=JST)
    event = pd.Timestamp(local_event).tz_convert("UTC")
    # Source time-of-day is authoritative for the clock but has no date. Only
    # accept receive-date reconstruction when callback and reconstructed event
    # are temporally close enough to be plausible.
    if abs((recv - event).total_seconds()) > 15 * 60:
        return recv, "LOCAL_RECEIVE_TIME_ONLY_SOURCE_TOD_DATE_AMBIGUOUS"
    return event, "SOURCE_TIME_OF_DAY_INFERRED_DATE_FROM_RECEIVE"


def _quote_dirs(lookback_days: int = 3) -> list[Path]:
    root = data_root() / "live" / "yuanta" / "parquet"
    if not root.exists():
        return []
    dirs = sorted([p for p in root.iterdir() if p.is_dir()])
    return dirs[-max(1, int(lookback_days)) :]


def load_jnu_trade_rows(*, lookback_days: int = 7) -> pd.DataFrame:
    """Load the newest archive day containing positive-price true JNU Micro trades.

    Search newest-to-oldest and stop on the first usable date. This avoids
    scanning/merging multiple sessions while still surviving a latest date
    directory that contains only non-JNU factors.
    """
    dirs = _quote_dirs(lookback_days)
    if not dirs:
        return pd.DataFrame()
    for directory in reversed(dirs):
        glob = str((directory / "*.parquet").as_posix()).replace("'", "''")
        query = f"""
            SELECT
                received_at,
                provider,
                callback_type,
                TRY_CAST(market_no AS INTEGER) AS market_no,
                CAST(instrument_code AS VARCHAR) AS instrument_code,
                TRY_CAST(deal AS DOUBLE) AS deal,
                TRY_CAST(vol AS DOUBLE) AS vol,
                CAST(source_time_of_day AS VARCHAR) AS source_time_of_day,
                CAST(timestamp_quality AS VARCHAR) AS timestamp_quality
            FROM read_parquet('{glob}', union_by_name=true)
            WHERE TRY_CAST(market_no AS INTEGER) = 207
              AND upper(CAST(instrument_code AS VARCHAR)) LIKE 'JNU%'
              AND TRY_CAST(deal AS DOUBLE) > 0
        """
        try:
            frame = duckdb.connect(":memory:").execute(query).df()
        except Exception:
            continue
        normalized = _normalize_trade_rows(frame)
        if not normalized.empty:
            return normalized
    return pd.DataFrame()


def _normalize_trade_rows(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()
    work = frame.copy()
    required = {"received_at", "instrument_code", "deal"}
    if not required.issubset(work.columns):
        return pd.DataFrame()
    work["instrument_code"] = work["instrument_code"].astype(str).str.upper()
    work = work[work["instrument_code"].map(lambda x: bool(_QUOTE_RE.fullmatch(x)))]
    work["price"] = pd.to_numeric(work["deal"], errors="coerce")
    work["volume"] = pd.to_numeric(work.get("vol"), errors="coerce")
    work = work[np.isfinite(work["price"]) & (work["price"] > 0)]
    if work.empty:
        return work
    events = [
        _event_timestamp(r, s)
        for r, s in zip(
            work["received_at"],
            work.get("source_time_of_day", pd.Series([None] * len(work))),
        )
    ]
    work["event_timestamp"] = [x[0] for x in events]
    work["event_time_provenance"] = [x[1] for x in events]
    work = work[work["event_timestamp"].notna()]
    work["contract_month"] = work["instrument_code"].map(_contract_month)
    work["base_quote_code"] = work["instrument_code"].map(_base_quote_code)
    work["session_variant"] = work["instrument_code"].map(_session_variant)
    work["session_start_date"] = [
        _session_start_date(ts, session).isoformat()
        for ts, session in zip(work["event_timestamp"], work["session_variant"])
    ]
    work["received_at"] = pd.to_datetime(work["received_at"], utc=True, errors="coerce")
    work = work.sort_values(["event_timestamp", "received_at"])
    # Repeated watchlist callbacks can replay the same deal state. Deduplicate
    # the same source clock/price/volume within one quote identity.
    dedup_cols = ["instrument_code", "event_timestamp", "price"]
    if "volume" in work.columns:
        dedup_cols.append("volume")
    work = work.drop_duplicates(dedup_cols, keep="last")
    return work.reset_index(drop=True)


def _expected_bounds(session: str, session_start_date) -> tuple[datetime, datetime]:
    if session == "DAY":
        start = datetime.combine(session_start_date, time(8, 45), tzinfo=JST)
        end = datetime.combine(session_start_date, time(15, 45), tzinfo=JST)
    else:
        start = datetime.combine(session_start_date, time(17, 0), tzinfo=JST)
        end = datetime.combine(session_start_date + timedelta(days=1), time(6, 0), tzinfo=JST)
    return start, end


def _session_start_date(ts: pd.Timestamp, session: str):
    local = ts.tz_convert(JST)
    if session == "NIGHT" and local.time() <= time(6, 0):
        return local.date() - timedelta(days=1)
    return local.date()


def _latest_session_rows(frame: pd.DataFrame, session: str) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()
    g = frame[frame["session_variant"].eq(session)].copy()
    if g.empty:
        return g
    latest_key = max(str(x) for x in g["session_start_date"].dropna().unique())
    return g[g["session_start_date"].astype(str).eq(latest_key)].copy()


def _session_snapshot(frame: pd.DataFrame, session: str) -> dict[str, Any]:
    g = _latest_session_rows(frame, session)
    if g.empty:
        return {
            "status": "NOT_AVAILABLE",
            "session": session,
            "latest_price": None,
            "verified_close_price": None,
            "coverage_complete": False,
        }
    g = g.sort_values("event_timestamp")
    latest = g.iloc[-1]
    first = g.iloc[0]
    start_date = _session_start_date(latest["event_timestamp"], session)
    expected_start, expected_end = _expected_bounds(session, start_date)
    first_local = first["event_timestamp"].tz_convert(JST)
    last_local = latest["event_timestamp"].tz_convert(JST)
    close_lag_seconds = (last_local.to_pydatetime() - expected_end).total_seconds()
    start_lag_seconds = (first_local.to_pydatetime() - expected_start).total_seconds()
    # Reuse the existing close-boundary evidence contract: the verified OSE
    # closing-auction print may land at the boundary or at most one second after.
    # A pre-close observation is never upgraded into an official close.
    close_verified = 0.0 <= close_lag_seconds <= 1.0
    open_boundary_observed = 0.0 <= start_lag_seconds <= 60.0
    coverage_complete = bool(open_boundary_observed and close_verified)
    return {
        "status": "AVAILABLE",
        "session": session,
        "quote_code": str(latest["instrument_code"]),
        "contract_month": str(latest["contract_month"]),
        "session_start_date": start_date.isoformat(),
        "first_event_at": first["event_timestamp"].isoformat(),
        "last_event_at": latest["event_timestamp"].isoformat(),
        "latest_price": float(latest["price"]),
        "latest_received_at": latest["received_at"].isoformat(),
        "timestamp_quality": str(latest.get("event_time_provenance") or ""),
        "open_boundary_observed": bool(open_boundary_observed),
        "close_lag_seconds": float(close_lag_seconds),
        "price_observation_count": int(len(g)),
        "expected_session_open": expected_start.astimezone(timezone.utc).isoformat(),
        "expected_session_close": expected_end.astimezone(timezone.utc).isoformat(),
        "coverage_complete": bool(coverage_complete),
        "verified_close_price": float(latest["price"]) if close_verified else None,
        "verified_close": bool(close_verified),
        "close_semantics": (
            "VERIFIED_SESSION_BOUNDARY_PRINT"
            if close_verified
            else "LAST_OBSERVED_SESSION_PRICE_NOT_SESSION_CLOSE"
        ),
    }


def _bars(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()
    g = frame.copy().sort_values("event_timestamp").set_index("event_timestamp")
    g["volume"] = pd.to_numeric(g["volume"], errors="coerce").fillna(0.0).clip(lower=0.0)
    bars = g.resample(BAR_FREQUENCY).agg(
        open=("price", "first"),
        high=("price", "max"),
        low=("price", "min"),
        close=("price", "last"),
        volume=("volume", "sum"),
        trades=("price", "count"),
    )
    return bars.dropna(subset=["open", "high", "low", "close"])


def _price_activity_profile(frame: pd.DataFrame) -> dict[str, Any]:
    """Observation-count profile; deliberately not called volume profile."""
    if frame is None or frame.empty or len(frame) < MIN_STRUCTURE_TRADES:
        return {
            "status": "PRICE_PROFILE_NOT_AVAILABLE",
            "reason": "INSUFFICIENT_TRUE_MICRO_PRICE_OBSERVATIONS",
            "observation_count": int(len(frame)) if frame is not None else 0,
        }
    g = frame.copy()
    g["price_bin"] = (g["price"] / TICK_POINTS).round() * TICK_POINTS
    profile = (
        g.groupby("price_bin", as_index=False)
        .size()
        .rename(columns={"size": "observations"})
        .sort_values("observations", ascending=False)
    )
    total = int(profile["observations"].sum())
    most_observed = float(profile.iloc[0]["price_bin"])
    chosen: list[float] = []
    running = 0
    for _, row in profile.iterrows():
        chosen.append(float(row["price_bin"]))
        running += int(row["observations"])
        if total and running / total >= 0.70:
            break
    return {
        "status": "AVAILABLE_DESCRIPTIVE_ONLY",
        "profile_semantics": "PRICE_OBSERVATION_ACTIVITY_NOT_VOLUME",
        "most_observed_price_bin": most_observed,
        "activity_area_low": float(min(chosen)),
        "activity_area_high": float(max(chosen)),
        "activity_area_method": "HIGHEST_OBSERVATION_PRICE_BINS_UNTIL_70_PERCENT",
        "observation_count": total,
        "price_bin_points": TICK_POINTS,
        "not_volume_profile": True,
        "not_support_resistance": True,
        "not_probability": True,
    }


def _volume_profile(frame: pd.DataFrame) -> dict[str, Any]:
    """Fail closed until durable true StockTick DealPrice/DealVol is persisted."""
    return {
        "status": "VOLUME_PROFILE_NOT_AVAILABLE",
        "reason": "VERIFIED_TRADE_TICK_DEALVOL_NOT_PRESENT_IN_CURRENT_DURABLE_ARCHIVE",
        "required_source": "SubscribeStockTick TRADE_TICK DealPrice + DealVol",
        "watchlist_vol_not_accepted_as_trade_volume": True,
        "not_support_resistance": True,
        "not_probability": True,
    }


def _structure(frame: pd.DataFrame) -> dict[str, Any]:
    bars = _bars(frame)
    if len(frame) < MIN_STRUCTURE_TRADES or len(bars) < MIN_STRUCTURE_BARS:
        return {
            "status": "INSUFFICIENT_DATA",
            "rule": "DESCRIPTIVE_STRUCTURE_V1_NOT_PREDICTIVE",
            "price_observation_count": int(len(frame)),
            "bar_count": int(len(bars)),
            "bar_frequency": BAR_FREQUENCY,
            "bar_semantics": "OBSERVED_PRICE_SNAPSHOT_BAR_NOT_EXCHANGE_OHLC",
            "price_profile": _price_activity_profile(frame),
            "volume_profile": _volume_profile(frame),
        }
    first = float(bars.iloc[0]["open"])
    last = float(bars.iloc[-1]["close"])
    hi = float(bars["high"].max())
    lo = float(bars["low"].min())
    rng = hi - lo
    net = last - first
    pos = (last - lo) / rng if rng > 0 else 0.5
    if rng <= 0:
        state = "BOX_CANDIDATE"
    elif net >= 0.50 * rng and pos >= 0.75:
        state = "UP_TREND_CANDIDATE"
    elif net <= -0.50 * rng and pos <= 0.25:
        state = "DOWN_TREND_CANDIDATE"
    elif abs(net) <= 0.25 * rng and 0.25 <= pos <= 0.75:
        state = "BOX_CANDIDATE"
    else:
        state = "MIXED"
    return {
        "status": "AVAILABLE_DESCRIPTIVE_ONLY",
        "rule": "DESCRIPTIVE_STRUCTURE_V1_NOT_PREDICTIVE",
        "structure_state": state,
        "session_open": first,
        "latest_close": last,
        "observed_high": hi,
        "observed_low": lo,
        "observed_range_points": rng,
        "net_change_points": net,
        "last_location_in_range": pos,
        "price_observation_count": int(len(frame)),
        "bar_count": int(len(bars)),
        "bar_frequency": BAR_FREQUENCY,
        "bar_semantics": "OBSERVED_PRICE_SNAPSHOT_BAR_NOT_EXCHANGE_OHLC",
        "price_profile": _price_activity_profile(frame),
        "volume_profile": _volume_profile(frame),
        "support_resistance_generated": False,
        "predictive_claim": False,
    }


def evaluate_acceptance_from_trades(
    frame: pd.DataFrame,
    *,
    level: float | None,
    direction: str = "AUTO",
) -> dict[str, Any]:
    """Evaluate touch/break/acceptance for one explicitly supplied level."""
    if level is None or not math.isfinite(float(level)):
        return {
            "status": "LEVEL_REQUIRED",
            "touch": None,
            "break": None,
            "acceptance": None,
            "false_breakout": None,
            "not_probability": True,
        }
    bars = _bars(frame)
    if len(frame) < MIN_STRUCTURE_TRADES or len(bars) < MIN_STRUCTURE_BARS:
        return {
            "status": "INSUFFICIENT_DATA",
            "level": float(level),
            "bar_count": int(len(bars)),
            "price_observation_count": int(len(frame)),
            "touch": None,
            "break": None,
            "acceptance": None,
            "false_breakout": None,
            "not_probability": True,
        }
    level = float(level)
    d = str(direction or "AUTO").upper()
    if d not in {"AUTO", "UP", "DOWN"}:
        raise ValueError("direction must be AUTO, UP or DOWN")
    if d == "AUTO":
        d = "UP" if float(bars.iloc[-1]["close"]) >= level else "DOWN"

    touch_mask = (bars["low"] <= level) & (bars["high"] >= level)
    touched = bool(touch_mask.any())
    if d == "UP":
        beyond = bars["high"] > level
        close_beyond = bars["close"] > level
        returned = bars["close"] <= level
        retest = (bars["low"] <= level) & (bars["close"] > level)
    else:
        beyond = bars["low"] < level
        close_beyond = bars["close"] < level
        returned = bars["close"] >= level
        retest = (bars["high"] >= level) & (bars["close"] < level)

    broken = bool(beyond.any())
    consecutive = close_beyond.astype(int).rolling(2).sum().fillna(0)
    accepted = bool((consecutive >= 2).any())
    first_break_pos = int(np.argmax(beyond.to_numpy())) if broken else -1
    retest_held = bool(retest.iloc[first_break_pos + 1 :].any()) if broken else False
    false_breakout = bool(broken and not accepted and returned.iloc[first_break_pos + 1 :].any())
    return {
        "status": "EVALUATED_DESCRIPTIVE_ONLY",
        "level": level,
        "level_source": "EXPLICIT_INPUT_REQUIRED",
        "direction": d,
        "touch": touched,
        "break": broken,
        "acceptance": accepted,
        "acceptance_rule": "TWO_CONSECUTIVE_5MIN_CLOSES_BEYOND_LEVEL",
        "retest_held": retest_held,
        "false_breakout": false_breakout,
        "touch_is_not_break": True,
        "break_is_not_acceptance": True,
        "bar_count": int(len(bars)),
        "price_observation_count": int(len(frame)),
        "bar_semantics": "OBSERVED_PRICE_SNAPSHOT_BAR_NOT_EXCHANGE_OHLC",
        "not_probability": True,
        "predictive_claim": False,
    }


def _current_quote_status(now: datetime) -> dict[str, Any]:
    status_path = data_root() / "live" / "yuanta" / "status.json"
    latest_path = data_root() / "live" / "yuanta" / "latest.json"
    out = {
        "status_file_exists": status_path.exists(),
        "latest_file_exists": latest_path.exists(),
        "live_now_verified": False,
        "provider_status": "UNKNOWN",
        "health_reasons": [],
    }
    if not status_path.exists():
        return out
    try:
        import json
        raw = json.loads(status_path.read_text(encoding="utf-8"))
    except Exception:
        return out
    out.update(
        provider_status=str(raw.get("status") or "UNKNOWN"),
        health_reasons=list(raw.get("health_reasons") or []),
        connection_status=str(raw.get("connection_status") or ""),
        jnu_microstructure_live_verified=bool(raw.get("jnu_microstructure_live_verified")),
        last_quote_at=raw.get("last_quote_at") or None,
        runtime_build_id=raw.get("runtime_build_id"),
    )
    # A running recorder without a recent exact callback is not "live now".
    out["live_now_verified"] = bool(
        raw.get("status") == "HEALTHY"
        and raw.get("last_quote_at")
        and raw.get("jnu_microstructure_live_verified")
    )
    return out


def build_jnu_trading_path_context(
    *,
    level: float | None = None,
    direction: str = "AUTO",
    now: datetime | None = None,
    trade_rows: pd.DataFrame | None = None,
) -> dict[str, Any]:
    as_of = _aware_utc(now)
    rows = _normalize_trade_rows(trade_rows) if trade_rows is not None else load_jnu_trade_rows()
    settlement_series, settlement = load_direct_micro_settlements()
    settlement_ok = settlement.get("status") == "OK" and not settlement_series.empty

    resolver = YuantaInstrumentResolver().resolve(
        "OSE_NIKKEI225_MICRO_FUTURES",
        as_of.astimezone(JST).date(),
    )
    decision_code = str(resolver.spark_code or "").upper() if resolver.verified else ""
    decision_month = _contract_month(decision_code)
    resolver_status = "VERIFIED_FUNCTION_LIST" if decision_code else "UNAVAILABLE"

    if rows.empty:
        decision_rows = rows
    elif decision_month:
        decision_rows = rows[rows["contract_month"].eq(decision_month)].copy()
    else:
        decision_rows = pd.DataFrame()

    day = _session_snapshot(decision_rows, "DAY")
    night = _session_snapshot(decision_rows, "NIGHT")
    available_sessions = [x for x in (day, night) if x.get("status") == "AVAILABLE"]
    latest_session = max(
        available_sessions,
        key=lambda x: pd.Timestamp(x["last_event_at"]),
        default=None,
    )
    latest_price = latest_session.get("latest_price") if latest_session else None

    settlement_month = str(settlement.get("contract_month") or "") if settlement_ok else ""
    same_contract = bool(settlement_month and decision_month and settlement_month == decision_month)
    settlement_gap = None
    if same_contract and latest_price is not None:
        settlement_gap = float(latest_price) - float(settlement["latest_settlement"])

    # Use only the most recently observed session for current structure to avoid
    # blending day and night price paths.
    latest_variant = latest_session.get("session") if latest_session else ""
    structure_rows = (
        _latest_session_rows(decision_rows, latest_variant)
        if latest_variant
        else pd.DataFrame()
    )
    structure = _structure(structure_rows)
    acceptance = evaluate_acceptance_from_trades(
        structure_rows,
        level=level,
        direction=direction,
    )

    try:
        from market_ai_hub.packet.builder import _event_snapshot
        event_framework = _event_snapshot(top_n=5)
    except Exception:
        event_framework = []
    dated_events = [
        dict(event)
        for event in event_framework
        if isinstance(event, dict) and event.get("scheduled_at")
    ]
    dated_event_status = (
        "DATED_EVENTS_AVAILABLE"
        if dated_events
        else "PROVIDER_FRAMEWORK_ONLY_NO_DATED_EVENTS"
    )

    venue = resolve_venue_session("OSE_DERIVATIVES", as_of)
    quote_runtime = _current_quote_status(as_of)

    if not decision_code:
        status = "NO_VERIFIED_DECISION_CONTRACT"
    elif decision_rows.empty:
        status = "NO_RECORDED_EXACT_MICRO_SESSION_DATA"
    else:
        status = "OK"

    return {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "product": PRODUCT,
        "evidence_level": EVIDENCE_LEVEL,
        "generated_at": as_of.isoformat(),
        "settlement_forecast": {
            "product": "SETTLEMENT_FORECAST",
            "target": "NEXT_PUBLISHED_SETTLEMENT_OBSERVATION",
            "contract_month": settlement_month or None,
            "quote_code": settlement.get("quote_code") if settlement_ok else None,
            "reference_settlement": (
                float(settlement["latest_settlement"]) if settlement_ok else None
            ),
            "reference_date": settlement.get("latest_date") if settlement_ok else None,
        },
        "decision_contract": {
            "resolver_status": resolver_status,
            "quote_code": decision_code or None,
            "contract_month": decision_month or None,
            "provider": "YUANTA_SPARK",
            "market_no": 207,
            "true_micro_only": True,
        },
        "contract_alignment": {
            "same_contract_month": same_contract,
            "status": "SAME_CONTRACT" if same_contract else "CONTRACT_MISMATCH",
            "cross_contract_arithmetic_allowed": same_contract,
            "settlement_to_session_gap_points": settlement_gap,
            "note": (
                "gap is only computed for the same JNU contract month"
                if same_contract
                else "settlement and session quote contract months differ; gap/basis is blocked"
            ),
        },
        "current_venue_session": venue.model_dump() if hasattr(venue, "model_dump") else vars(venue),
        "quote_runtime": quote_runtime,
        "price_semantics": {
            "TARGET_REFERENCE_SETTLEMENT": (
                float(settlement["latest_settlement"]) if settlement_ok else None
            ),
            "TARGET_LATEST_LIVE_OR_SESSION_PRICE": latest_price,
            "TARGET_LATEST_PRICE_LIVE_NOW_VERIFIED": bool(quote_runtime.get("live_now_verified")),
            "TARGET_PREVIOUS_DAY_CLOSE": day.get("verified_close_price"),
            "TARGET_PREVIOUS_NIGHT_CLOSE": night.get("verified_close_price"),
            "night_close_available": bool(night.get("verified_close")),
            "latest_night_observation_is_close": bool(night.get("verified_close")),
        },
        "day_session": day,
        "night_session": night,
        "market_structure": structure,
        "acceptance": acceptance,
        "event_context": {
            "provider_calendar_framework": event_framework,
            "dated_events": dated_events,
            "dated_event_status": dated_event_status,
            "dated_event_data_ready": bool(dated_events),
            "role": "CONTEXT_RISK_ABSTENTION_ONLY",
            "news_context_status": "LIVE_NEWS_FUSION_DEFERRED_P6",
            "news_sentiment_probability_allowed": False,
        },
        "decision_support": {
            "strong_direction_allowed": False,
            "calibrated_probability_available": False,
            "trading_edge_established": False,
            "support_resistance_auto_generated": False,
            "conditional_scenarios_allowed": True,
            "abstain_when_session_coverage_incomplete": True,
        },
        "hard_boundaries": {
            "proxy_can_replace_micro": False,
            "cross_contract_gap_allowed": same_contract,
            "orders_allowed": False,
            "account_access_allowed": False,
            "broker_mutation_allowed": False,
        },
    }


def jnu_trading_path_user_summary(result: dict[str, Any]) -> dict[str, Any]:
    """Plain-language view that keeps settlement and trading path separate."""
    settlement = result.get("settlement_forecast") or {}
    decision = result.get("decision_contract") or {}
    align = result.get("contract_alignment") or {}
    price = result.get("price_semantics") or {}
    structure = result.get("market_structure") or {}
    night = result.get("night_session") or {}
    latest = price.get("TARGET_LATEST_LIVE_OR_SESSION_PRICE")

    if latest is None:
        latest_text = "目前沒有可用的真實 JNU Micro session 成交價"
    else:
        latest_text = f"{float(latest):,.0f} 點（{decision.get('quote_code') or 'JNU'}，歷史/最新可用 session observation）"

    night_close = price.get("TARGET_PREVIOUS_NIGHT_CLOSE")
    return {
        "產品分層": {
            "官方清算價預測": "預測下一筆官方 published settlement observation",
            "交易路徑支援": "描述真正 JNU Micro 的日夜盤狀態；不是清算價模型，也不是交易機率",
        },
        "清算價基準": (
            f"{settlement.get('reference_date')} {settlement.get('quote_code')} "
            f"{float(settlement.get('reference_settlement')):,.0f} 點"
            if settlement.get("reference_settlement") is not None
            else "目前不可用"
        ),
        "交易決策合約": decision.get("quote_code") or "目前無法從已驗證 FunctionList 解析",
        "最新JNU實際session價格": latest_text,
        "即時狀態": (
            "目前有新鮮 exact-Micro callback"
            if price.get("TARGET_LATEST_PRICE_LIVE_NOW_VERIFIED")
            else "目前沒有經驗證的新鮮即時 callback；顯示值只能作歷史 session context"
        ),
        "前一夜收盤": (
            f"{float(night_close):,.0f} 點"
            if night_close is not None
            else "未取得符合 06:00 JST 收盤邊界的 exact-Micro observation，不能把最後一筆夜盤資料冒充收盤價"
        ),
        "合約對齊": (
            "清算價與 session 價格是同一限月，可計算同限月差異"
            if align.get("same_contract_month")
            else "清算價與目前 session quote 限月不同，禁止直接相減或解讀成 gap"
        ),
        "市場結構": {
            "狀態": structure.get("structure_state") or structure.get("status"),
            "觀測區間": (
                f"{float(structure['observed_low']):,.0f} ～ {float(structure['observed_high']):,.0f} 點"
                if structure.get("observed_low") is not None and structure.get("observed_high") is not None
                else "資料不足"
            ),
            "Price Profile": structure.get("price_profile"),
            "Volume Profile": structure.get("volume_profile"),
            "證據限制": "描述性規則，不是方向概率；Price Activity 不等於成交量，Volume Profile 在未有 verified DealVol 前保持 unavailable。",
        },
        "Acceptance": result.get("acceptance"),
        "事件／新聞": {
            "官方事件": (
                "已有具日期的官方事件資料，可作 context / risk / abstention"
                if (result.get("event_context") or {}).get("dated_event_data_ready")
                else "目前只有官方 provider/calendar framework，尚無 materialized dated event rows；不假裝已有事件日曆資料"
            ),
            "即時新聞融合": "目前延後到 P6；不把 LLM sentiment 當上漲機率",
        },
        "目前可採用的研究方式": (
            "分開閱讀 settlement forecast 與 trading-path context；只有同限月、完整來源與足夠 session coverage "
            "才做相應比較。資料不足時保持 abstain。"
        ),
        "PREDICTIVE_GAIN": False,
        "CALIBRATED": False,
        "TRADING_EDGE": False,
    }
