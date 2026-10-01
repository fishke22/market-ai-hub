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
from market_ai_hub.services.jnu_session_materializer import (
    bars_frame as materialized_bars_frame,
    load_materialized_sessions,
    select_session as select_materialized_session,
    settlement_excursion as materialized_settlement_excursion,
)


SCHEMA_VERSION = "JNU.TRADING_PATH.1"
PRODUCT = "TRADING_PATH_DECISION_SUPPORT"
EVIDENCE_LEVEL = "DESCRIPTIVE_DECISION_SUPPORT_ONLY"
TICK_POINTS = 5.0
BAR_FREQUENCY = "5min"
MIN_STRUCTURE_TRADES = 30
MIN_STRUCTURE_BARS = 6
MAX_RECENT_PARQUET_FILES_PER_DAY = 300
LIVE_QUOTE_MAX_AGE_SECONDS = 60.0
JST = ZoneInfo("Asia/Tokyo")


def _materialized_root() -> Path:
    return data_root() / "live" / "yuanta"
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


def _recent_parquet_files(
    directory: Path,
    *,
    max_files: int = MAX_RECENT_PARQUET_FILES_PER_DAY,
) -> list[str]:
    """Return a bounded newest suffix without opening every Parquet file."""
    if max_files < 1 or not directory.exists():
        return []
    files = sorted(directory.glob("*.parquet"), key=lambda p: p.name)
    return [str(p) for p in files[-max_files:]]


def load_jnu_trade_rows(*, lookback_days: int = 7) -> pd.DataFrame:
    """Load a bounded recent window of true JNU Micro quote observations.

    Recorder WAL part names are append-sequence ordered.  Opening every tiny
    Parquet part in a busy day made the live trading-path MCP call time out, so
    only the newest bounded suffix of each archive day is opened.
    """
    dirs = _quote_dirs(lookback_days)
    if not dirs:
        return pd.DataFrame()
    for directory in reversed(dirs):
        files = _recent_parquet_files(directory)
        if not files:
            continue
        query = """
            SELECT
                received_at,
                provider,
                callback_type,
                TRY_CAST(market_no AS INTEGER) AS market_no,
                CAST(instrument_code AS VARCHAR) AS instrument_code,
                TRY_CAST(deal AS DOUBLE) AS deal,
                TRY_CAST(vol AS DOUBLE) AS vol,
                TRY_CAST(DealPrice AS DOUBLE) AS tick_deal_price,
                TRY_CAST(DealVol AS DOUBLE) AS tick_deal_vol,
                CAST(SerialNo AS VARCHAR) AS serial_no,
                CAST(source_time_of_day AS VARCHAR) AS source_time_of_day,
                CAST(timestamp_quality AS VARCHAR) AS timestamp_quality
            FROM read_parquet(?, union_by_name=true)
            WHERE TRY_CAST(market_no AS INTEGER) = 207
              AND upper(CAST(instrument_code AS VARCHAR)) LIKE 'JNU%'
              AND COALESCE(TRY_CAST(DealPrice AS DOUBLE), TRY_CAST(deal AS DOUBLE)) > 0
        """
        try:
            frame = duckdb.connect(":memory:").execute(query, [files]).df()
        except Exception:
            fallback_query = """
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
                FROM read_parquet(?, union_by_name=true)
                WHERE TRY_CAST(market_no AS INTEGER) = 207
                  AND upper(CAST(instrument_code AS VARCHAR)) LIKE 'JNU%'
                  AND TRY_CAST(deal AS DOUBLE) > 0
            """
            try:
                frame = duckdb.connect(":memory:").execute(fallback_query, [files]).df()
            except Exception:
                continue
        normalized = _normalize_trade_rows(frame)
        if not normalized.empty:
            normalized.attrs["archive_files_scanned"] = len(files)
            normalized.attrs["archive_scan_bounded"] = True
            normalized.attrs["archive_day"] = directory.name
            return normalized
    return pd.DataFrame()


def _normalize_trade_rows(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()
    work = frame.copy()
    required = {"received_at", "instrument_code"}
    if not required.issubset(work.columns):
        return pd.DataFrame()
    work["instrument_code"] = work["instrument_code"].astype(str).str.upper()
    work = work[work["instrument_code"].map(lambda x: bool(_QUOTE_RE.fullmatch(x)))]
    watch_price = (
        pd.to_numeric(work["deal"], errors="coerce")
        if "deal" in work.columns else pd.Series(np.nan, index=work.index)
    )
    tick_price = (
        pd.to_numeric(work["tick_deal_price"], errors="coerce")
        if "tick_deal_price" in work.columns else
        pd.to_numeric(work["DealPrice"], errors="coerce")
        if "DealPrice" in work.columns else pd.Series(np.nan, index=work.index)
    )
    callback_type = work.get(
        "callback_type", pd.Series("", index=work.index, dtype=object)
    ).astype(str)
    work["callback_type"] = callback_type
    tick_row = callback_type.eq("SubscribeStockTick") & np.isfinite(tick_price) & (tick_price > 0)
    work["price"] = watch_price
    work.loc[tick_row, "price"] = tick_price.loc[tick_row]

    watch_volume = (
        pd.to_numeric(work["vol"], errors="coerce")
        if "vol" in work.columns else pd.Series(np.nan, index=work.index)
    )
    tick_volume = (
        pd.to_numeric(work["tick_deal_vol"], errors="coerce")
        if "tick_deal_vol" in work.columns else
        pd.to_numeric(work["DealVol"], errors="coerce")
        if "DealVol" in work.columns else pd.Series(np.nan, index=work.index)
    )
    work["volume"] = watch_volume
    work.loc[tick_row, "volume"] = tick_volume.loc[tick_row]
    work["verified_trade_tick"] = (
        tick_row & np.isfinite(tick_volume) & (tick_volume >= 0)
    )
    if "serial_no" not in work.columns and "SerialNo" in work.columns:
        work["serial_no"] = work["SerialNo"]
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
    dedup_cols = ["instrument_code", "callback_type", "event_timestamp", "price"]
    if "volume" in work.columns:
        dedup_cols.append("volume")
    if "serial_no" in work.columns:
        dedup_cols.append("serial_no")
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


def _verified_trade_ticks(frame: pd.DataFrame) -> pd.DataFrame:
    if frame is None or frame.empty or "verified_trade_tick" not in frame.columns:
        return pd.DataFrame()
    return frame[frame["verified_trade_tick"].fillna(False).astype(bool)].copy()


def _preferred_structure_rows(frame: pd.DataFrame) -> pd.DataFrame:
    ticks = _verified_trade_ticks(frame)
    if len(ticks) >= MIN_STRUCTURE_TRADES and len(_bars(ticks)) >= MIN_STRUCTURE_BARS:
        return ticks
    return frame.copy() if frame is not None else pd.DataFrame()


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
    """Build descriptive profile only from verified StockTick DealPrice/DealVol."""
    ticks = _verified_trade_ticks(frame)
    ticks["volume"] = pd.to_numeric(ticks.get("volume"), errors="coerce")
    ticks = ticks[np.isfinite(ticks["volume"]) & (ticks["volume"] > 0)]
    if len(ticks) < MIN_STRUCTURE_TRADES:
        return {
            "status": "VOLUME_PROFILE_NOT_AVAILABLE",
            "reason": "INSUFFICIENT_VERIFIED_TRADE_TICK_DEALVOL",
            "required_source": "SubscribeStockTick TRADE_TICK DealPrice + DealVol",
            "verified_trade_tick_count": int(len(ticks)),
            "watchlist_vol_not_accepted_as_trade_volume": True,
            "not_support_resistance": True,
            "not_probability": True,
        }
    ticks["price_bin"] = (ticks["price"] / TICK_POINTS).round() * TICK_POINTS
    profile = (
        ticks.groupby("price_bin", as_index=False)
        .agg(volume=("volume", "sum"), trades=("price", "count"))
        .sort_values("volume", ascending=False)
    )
    total_volume = float(profile["volume"].sum())
    chosen: list[float] = []
    running = 0.0
    for _, row in profile.iterrows():
        chosen.append(float(row["price_bin"]))
        running += float(row["volume"])
        if total_volume and running / total_volume >= 0.70:
            break
    vwap = float((ticks["price"] * ticks["volume"]).sum() / ticks["volume"].sum())
    return {
        "status": "AVAILABLE_VERIFIED_TRADE_TICK",
        "profile_semantics": "SUBSCRIBESTOCKTICK_DEALPRICE_DEALVOL",
        "highest_volume_price_bin": float(profile.iloc[0]["price_bin"]),
        "value_area_low": float(min(chosen)),
        "value_area_high": float(max(chosen)),
        "value_area_method": "HIGHEST_VOLUME_PRICE_BINS_UNTIL_70_PERCENT",
        "vwap": vwap,
        "total_volume": total_volume,
        "verified_trade_tick_count": int(len(ticks)),
        "price_bin_points": TICK_POINTS,
        "watchlist_vol_not_accepted_as_trade_volume": True,
        "not_support_resistance": True,
        "not_probability": True,
    }


def _materialized_price_profile(session: dict[str, Any]) -> dict[str, Any]:
    bins = {
        float(k): int(v)
        for k, v in (session.get("price_trade_bins") or {}).items()
        if int(v) > 0
    }
    total = int(sum(bins.values()))
    if total < MIN_STRUCTURE_TRADES or not bins:
        return {
            "status": "PRICE_PROFILE_NOT_AVAILABLE",
            "reason": "INSUFFICIENT_VERIFIED_STOCKTICK_OBSERVATIONS",
            "observation_count": total,
        }
    ranked = sorted(bins.items(), key=lambda item: item[1], reverse=True)
    chosen: list[float] = []
    running = 0
    for price_bin, observations in ranked:
        chosen.append(float(price_bin))
        running += int(observations)
        if running / total >= 0.70:
            break
    return {
        "status": "AVAILABLE_DESCRIPTIVE_ONLY",
        "profile_semantics": "VERIFIED_STOCKTICK_PRICE_ACTIVITY",
        "most_observed_price_bin": float(ranked[0][0]),
        "activity_area_low": float(min(chosen)),
        "activity_area_high": float(max(chosen)),
        "activity_area_method": "HIGHEST_OBSERVATION_PRICE_BINS_UNTIL_70_PERCENT",
        "observation_count": total,
        "price_bin_points": TICK_POINTS,
        "not_volume_profile": True,
        "not_support_resistance": True,
        "not_probability": True,
    }


def _materialized_volume_profile(session: dict[str, Any]) -> dict[str, Any]:
    bins = {
        float(k): float(v)
        for k, v in (session.get("price_volume_bins") or {}).items()
        if float(v) > 0
    }
    total_volume = float(sum(bins.values()))
    trade_count = int(session.get("trade_count") or 0)
    if trade_count < MIN_STRUCTURE_TRADES or total_volume <= 0 or not bins:
        return {
            "status": "VOLUME_PROFILE_NOT_AVAILABLE",
            "reason": "INSUFFICIENT_VERIFIED_TRADE_TICK_DEALVOL",
            "verified_trade_tick_count": trade_count,
            "watchlist_vol_not_accepted_as_trade_volume": True,
            "not_support_resistance": True,
            "not_probability": True,
        }
    ranked = sorted(bins.items(), key=lambda item: item[1], reverse=True)
    chosen: list[float] = []
    running = 0.0
    for price_bin, volume in ranked:
        chosen.append(float(price_bin))
        running += float(volume)
        if running / total_volume >= 0.70:
            break
    return {
        "status": "AVAILABLE_VERIFIED_TRADE_TICK",
        "profile_semantics": "SUBSCRIBESTOCKTICK_DEALPRICE_DEALVOL_MATERIALIZED",
        "highest_volume_price_bin": float(ranked[0][0]),
        "value_area_low": float(min(chosen)),
        "value_area_high": float(max(chosen)),
        "value_area_method": "HIGHEST_VOLUME_PRICE_BINS_UNTIL_70_PERCENT",
        "vwap": session.get("vwap"),
        "total_volume": total_volume,
        "verified_trade_tick_count": trade_count,
        "price_bin_points": TICK_POINTS,
        "watchlist_vol_not_accepted_as_trade_volume": True,
        "not_support_resistance": True,
        "not_probability": True,
    }


def _materialized_session_snapshot(session: dict[str, Any] | None, session_name: str) -> dict[str, Any]:
    if not session:
        return {
            "status": "NOT_AVAILABLE",
            "session": session_name,
            "latest_price": None,
            "verified_close_price": None,
            "coverage_complete": False,
        }
    expected_end = pd.Timestamp(session["expected_session_close"]).tz_convert(JST)
    last_local = pd.Timestamp(session["last_event_at"]).tz_convert(JST)
    return {
        "status": "AVAILABLE",
        "session": session_name,
        "quote_code": session.get("live_quote_code"),
        "contract_month": session.get("contract_month"),
        "session_start_date": session.get("session_start_date"),
        "first_event_at": session.get("first_event_at"),
        "last_event_at": session.get("last_event_at"),
        "latest_price": session.get("latest_price"),
        "latest_received_at": session.get("last_received_at"),
        "timestamp_quality": "SOURCE_TIME_OF_DAY_ONLY",
        "open_boundary_observed": bool(session.get("open_boundary_observed")),
        "close_lag_seconds": float((last_local - expected_end).total_seconds()),
        "price_observation_count": int(session.get("trade_count") or 0),
        "expected_session_open": session.get("expected_session_open"),
        "expected_session_close": session.get("expected_session_close"),
        "coverage_complete": bool(session.get("coverage_complete")),
        "verified_close_price": session.get("verified_close_price"),
        "verified_close": bool(session.get("verified_close")),
        "close_semantics": session.get("close_semantics")
        or "LAST_OBSERVED_SESSION_PRICE_NOT_SESSION_CLOSE",
        "materialized": True,
        "label_ready": bool(session.get("label_ready")),
    }


def _structure_from_materialized(session: dict[str, Any]) -> dict[str, Any]:
    bars = materialized_bars_frame(session)
    trade_count = int(session.get("trade_count") or 0)
    price_profile = _materialized_price_profile(session)
    volume_profile = _materialized_volume_profile(session)
    if trade_count < MIN_STRUCTURE_TRADES or len(bars) < MIN_STRUCTURE_BARS:
        return {
            "status": "INSUFFICIENT_DATA",
            "rule": "DESCRIPTIVE_STRUCTURE_V1_NOT_PREDICTIVE",
            "price_observation_count": trade_count,
            "verified_trade_tick_count": trade_count,
            "bar_count": int(len(bars)),
            "bar_frequency": BAR_FREQUENCY,
            "bar_semantics": "VERIFIED_STOCKTICK_TRADE_BAR_MATERIALIZED",
            "price_profile": price_profile,
            "volume_profile": volume_profile,
            "materialized": True,
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
        "session_open": session.get("session_open"),
        "structure_window_open": first,
        "structure_window_partial": not bool(session.get("coverage_complete")),
        "latest_close": last,
        "observed_high": hi,
        "observed_low": lo,
        "observed_range_points": rng,
        "net_change_points": net,
        "last_location_in_range": pos,
        "price_observation_count": trade_count,
        "verified_trade_tick_count": trade_count,
        "bar_count": int(len(bars)),
        "bar_frequency": BAR_FREQUENCY,
        "bar_semantics": "VERIFIED_STOCKTICK_TRADE_BAR_MATERIALIZED",
        "price_profile": price_profile,
        "volume_profile": volume_profile,
        "support_resistance_generated": False,
        "predictive_claim": False,
        "materialized": True,
        "session_metrics": {
            "vwap": session.get("vwap"),
            "total_volume": session.get("total_volume"),
            "opening_range_high": session.get("opening_range_high"),
            "opening_range_low": session.get("opening_range_low"),
            "opening_range_complete": bool(session.get("opening_range_complete")),
            "mfe_from_session_open": session.get("mfe_from_session_open"),
            "mae_from_session_open": session.get("mae_from_session_open"),
            "label_ready": bool(session.get("label_ready")),
            "coverage_complete": bool(session.get("coverage_complete")),
            "open_boundary_observed": bool(session.get("open_boundary_observed")),
            "verified_close": bool(session.get("verified_close")),
        },
    }


def _evaluate_acceptance_from_bars(
    bars: pd.DataFrame,
    *,
    level: float | None,
    direction: str,
    price_observation_count: int,
    bar_semantics: str,
) -> dict[str, Any]:
    if level is None or not math.isfinite(float(level)):
        return {
            "status": "LEVEL_REQUIRED",
            "touch": None,
            "break": None,
            "acceptance": None,
            "false_breakout": None,
            "not_probability": True,
        }
    if len(bars) < MIN_STRUCTURE_BARS:
        return {
            "status": "INSUFFICIENT_DATA",
            "level": float(level),
            "bar_count": int(len(bars)),
            "price_observation_count": int(price_observation_count),
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
        "price_observation_count": int(price_observation_count),
        "bar_semantics": bar_semantics,
        "not_probability": True,
        "predictive_claim": False,
    }


def _first_passage_from_bars(
    bars: pd.DataFrame,
    *,
    level: float | None,
    direction: str,
    session_complete: bool,
) -> dict[str, Any]:
    if level is None or not math.isfinite(float(level)):
        return {"status": "LEVEL_REQUIRED", "value": None, "not_probability": True}
    d = str(direction or "AUTO").upper()
    if d not in {"AUTO", "UP", "DOWN"}:
        raise ValueError("direction must be AUTO, UP or DOWN")
    if bars.empty:
        return {"status": "INSUFFICIENT_DATA", "value": None, "not_probability": True}
    px = float(level)
    if d == "AUTO":
        d = "UP" if float(bars.iloc[-1]["close"]) >= px else "DOWN"
    touched = bars["high"] >= px if d == "UP" else bars["low"] <= px
    if bool(touched.any()):
        first_index = touched[touched].index[0]
        return {
            "status": "OBSERVED_TRUE",
            "value": True,
            "level": px,
            "direction": d,
            "first_passage_bar_start": pd.Timestamp(first_index).isoformat(),
            "resolution": "5MIN_OHLC",
            "exact_tick_order_not_claimed": True,
            "not_probability": True,
        }
    return {
        "status": "OBSERVED_FALSE" if session_complete else "OBSERVED_FALSE_SO_FAR",
        "value": False,
        "level": px,
        "direction": d,
        "first_passage_bar_start": None,
        "resolution": "5MIN_OHLC",
        "exact_tick_order_not_claimed": True,
        "not_probability": True,
    }


def _structure(frame: pd.DataFrame) -> dict[str, Any]:
    analysis_frame = _preferred_structure_rows(frame)
    verified_ticks = _verified_trade_ticks(frame)
    using_verified_ticks = bool(
        len(verified_ticks) >= MIN_STRUCTURE_TRADES
        and len(_bars(verified_ticks)) >= MIN_STRUCTURE_BARS
    )
    bar_semantics = (
        "VERIFIED_STOCKTICK_TRADE_BAR"
        if using_verified_ticks
        else "OBSERVED_PRICE_SNAPSHOT_BAR_NOT_EXCHANGE_OHLC"
    )
    bars = _bars(analysis_frame)
    if len(analysis_frame) < MIN_STRUCTURE_TRADES or len(bars) < MIN_STRUCTURE_BARS:
        return {
            "status": "INSUFFICIENT_DATA",
            "rule": "DESCRIPTIVE_STRUCTURE_V1_NOT_PREDICTIVE",
            "price_observation_count": int(len(analysis_frame)),
            "verified_trade_tick_count": int(len(verified_ticks)),
            "bar_count": int(len(bars)),
            "bar_frequency": BAR_FREQUENCY,
            "bar_semantics": bar_semantics,
            "price_profile": _price_activity_profile(analysis_frame),
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
        "price_observation_count": int(len(analysis_frame)),
        "verified_trade_tick_count": int(len(verified_ticks)),
        "bar_count": int(len(bars)),
        "bar_frequency": BAR_FREQUENCY,
        "bar_semantics": bar_semantics,
        "price_profile": _price_activity_profile(analysis_frame),
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
    analysis_frame = _preferred_structure_rows(frame)
    bars = _bars(analysis_frame)
    return _evaluate_acceptance_from_bars(
        bars,
        level=level,
        direction=direction,
        price_observation_count=len(analysis_frame),
        bar_semantics=(
            "VERIFIED_STOCKTICK_TRADE_BAR"
            if bool(analysis_frame.get("verified_trade_tick", pd.Series(False, index=analysis_frame.index)).all())
            else "OBSERVED_PRICE_SNAPSHOT_BAR_NOT_EXCHANGE_OHLC"
        ),
    )


def _current_quote_status(now: datetime, decision_code: str = "") -> dict[str, Any]:
    status_path = data_root() / "live" / "yuanta" / "status.json"
    latest_path = data_root() / "live" / "yuanta" / "latest.json"
    out = {
        "status_file_exists": status_path.exists(),
        "latest_file_exists": latest_path.exists(),
        "live_now_verified": False,
        "live_price_verified": False,
        "microstructure_live_verified": False,
        "jnu_microstructure_live_verified": False,
        "microstructure_runtime_verified": False,
        "jnu_microstructure_runtime_verified": False,
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
    microstructure_runtime_verified = bool(raw.get("jnu_microstructure_live_verified"))
    out.update(
        provider_status=str(raw.get("status") or "UNKNOWN"),
        health_reasons=list(raw.get("health_reasons") or []),
        connection_status=str(raw.get("connection_status") or ""),
        microstructure_runtime_verified=microstructure_runtime_verified,
        jnu_microstructure_runtime_verified=microstructure_runtime_verified,
        microstructure_live_verified=False,
        jnu_microstructure_live_verified=False,
        last_quote_at=raw.get("last_quote_at") or None,
        runtime_build_id=raw.get("runtime_build_id"),
    )

    latest_raw: dict[str, Any] = {}
    if latest_path.exists():
        try:
            latest_raw = json.loads(latest_path.read_text(encoding="utf-8"))
        except Exception:
            latest_raw = {}
    target_month = _contract_month(decision_code)
    candidates: list[tuple[pd.Timestamp, dict[str, Any]]] = []
    for quote in (latest_raw.get("quotes") or {}).values():
        if not isinstance(quote, dict):
            continue
        try:
            market_no = int(quote.get("market_no"))
        except (TypeError, ValueError):
            continue
        code = str(quote.get("instrument_code") or "").upper()
        if market_no != 207 or not _QUOTE_RE.fullmatch(code):
            continue
        if target_month and _contract_month(code) != target_month:
            continue
        try:
            deal = float(quote.get("deal"))
        except (TypeError, ValueError):
            continue
        if not math.isfinite(deal) or deal <= 0:
            continue
        provenance = quote.get("field_provenance") or {}
        deal_provenance = provenance.get("deal") if isinstance(provenance, dict) else {}
        stamp = (deal_provenance or {}).get("received_at") or quote.get("received_at")
        ts = pd.to_datetime(stamp, utc=True, errors="coerce")
        if pd.isna(ts):
            continue
        candidates.append((ts, quote))

    if candidates:
        ts, quote = max(candidates, key=lambda item: item[0])
        age_seconds = float((pd.Timestamp(now).tz_convert("UTC") - ts).total_seconds())
        provider_running = str(raw.get("status") or "").upper() in {"RUNNING", "HEALTHY"}
        live_price_verified = bool(
            provider_running
            and not out["health_reasons"]
            and 0.0 <= age_seconds <= LIVE_QUOTE_MAX_AGE_SECONDS
        )
        current_microstructure_verified = bool(
            microstructure_runtime_verified and live_price_verified
        )
        out.update(
            live_price=float(quote["deal"]),
            live_instrument_code=str(quote.get("instrument_code") or "").upper(),
            live_session_variant=_session_variant(str(quote.get("instrument_code") or "")),
            live_price_at=ts.isoformat(),
            live_price_age_seconds=age_seconds,
            live_price_source="SubscribeWatchlistAll.deal",
            live_price_verified=live_price_verified,
            microstructure_live_verified=current_microstructure_verified,
            jnu_microstructure_live_verified=current_microstructure_verified,
        )
        out["live_now_verified"] = live_price_verified
    return out


def build_jnu_trading_path_context(
    *,
    level: float | None = None,
    direction: str = "AUTO",
    now: datetime | None = None,
    trade_rows: pd.DataFrame | None = None,
) -> dict[str, Any]:
    as_of = _aware_utc(now)
    resolver = YuantaInstrumentResolver().resolve(
        "OSE_NIKKEI225_MICRO_FUTURES",
        as_of.astimezone(JST).date(),
    )
    decision_code = str(resolver.spark_code or "").upper() if resolver.verified else ""
    decision_month = _contract_month(decision_code)
    resolver_status = "VERIFIED_FUNCTION_LIST" if decision_code else "UNAVAILABLE"
    settlement_series, settlement = load_direct_micro_settlements(decision_month)
    settlement_ok = settlement.get("status") == "OK" and not settlement_series.empty
    settlement_month = str(settlement.get("contract_month") or "") if settlement_ok else ""
    same_contract = bool(settlement_month and decision_month and settlement_month == decision_month)

    materialized_artifact: dict[str, Any] = {
        "status": "NOT_USED",
        "reason": "EXPLICIT_TRADE_ROWS" if trade_rows is not None else "NOT_ATTEMPTED",
    }
    materialized_day = materialized_night = materialized_latest = None
    use_materialized = False
    if trade_rows is None and decision_month:
        # A live materializer can persist a newer artifact while settlement/reference
        # loading is still running.  Use the actual read time for live freshness;
        # explicit now= remains pinned for deterministic replay/tests.
        materialized_check_time = _aware_utc(None) if now is None else as_of
        materialized_artifact = load_materialized_sessions(
            _materialized_root(),
            now=materialized_check_time,
        )
        if materialized_artifact.get("status") == "FRESH":
            materialized_day = select_materialized_session(
                materialized_artifact,
                contract_month=decision_month,
                session="DAY",
            )
            materialized_night = select_materialized_session(
                materialized_artifact,
                contract_month=decision_month,
                session="NIGHT",
            )
            materialized_candidates = [
                x for x in (materialized_day, materialized_night) if x
            ]
            if materialized_candidates:
                materialized_latest = max(
                    materialized_candidates,
                    key=lambda x: str(x.get("last_event_at") or ""),
                )
                use_materialized = True

    decision_rows = pd.DataFrame()
    structure_rows = pd.DataFrame()
    first_passage = {
        "status": "LEVEL_REQUIRED" if level is None else "NOT_AVAILABLE",
        "value": None,
        "not_probability": True,
    }
    if use_materialized and materialized_latest is not None:
        day = _materialized_session_snapshot(materialized_day, "DAY")
        night = _materialized_session_snapshot(materialized_night, "NIGHT")
        available_sessions = [x for x in (day, night) if x.get("status") == "AVAILABLE"]
        latest_session = max(
            available_sessions,
            key=lambda x: pd.Timestamp(x["last_event_at"]),
            default=None,
        )
        latest_price = materialized_latest.get("latest_price")
        structure = _structure_from_materialized(materialized_latest)
        materialized_bars = materialized_bars_frame(materialized_latest)
        acceptance = _evaluate_acceptance_from_bars(
            materialized_bars,
            level=level,
            direction=direction,
            price_observation_count=int(materialized_latest.get("trade_count") or 0),
            bar_semantics="VERIFIED_STOCKTICK_TRADE_BAR_MATERIALIZED",
        )
        if level is not None:
            first_passage = _first_passage_from_bars(
                materialized_bars,
                level=level,
                direction=direction,
                session_complete=bool(materialized_latest.get("coverage_complete")),
            )
    else:
        rows = _normalize_trade_rows(trade_rows) if trade_rows is not None else load_jnu_trade_rows()
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
        first_passage = _first_passage_from_bars(
            _bars(_preferred_structure_rows(structure_rows)),
            level=level,
            direction=direction,
            session_complete=bool(latest_session and latest_session.get("coverage_complete")),
        )

    settlement_gap = None
    session_settlement_excursion = {"status": "NOT_AVAILABLE"}
    if same_contract and materialized_latest is not None:
        session_settlement_excursion = materialized_settlement_excursion(
            materialized_latest,
            float(settlement["latest_settlement"]) if settlement_ok else None,
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
    # When this is a live call, freshness must be evaluated at the time the
    # quote snapshot is inspected, not at function entry.  The bounded archive
    # load can take several seconds and quotes may legitimately arrive meanwhile.
    quote_check_time = _aware_utc(None) if now is None else as_of
    quote_runtime = _current_quote_status(quote_check_time, decision_code)
    current_price = (
        float(quote_runtime["live_price"])
        if quote_runtime.get("live_price_verified") and quote_runtime.get("live_price") is not None
        else latest_price
    )
    if same_contract and current_price is not None:
        settlement_gap = float(current_price) - float(settlement["latest_settlement"])

    if not decision_code:
        status = "NO_VERIFIED_DECISION_CONTRACT"
    elif latest_session is None:
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
            "product": "TRADING_PATH_SAME_CONTRACT_SETTLEMENT_REFERENCE",
            "target": "LATEST_PUBLISHED_SETTLEMENT_OBSERVATION_FOR_LIVE_CONTRACT",
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
        "contract_roles": {
            "live_trading_contract": {
                "base_quote_code": decision_code or None,
                "live_quote_code": quote_runtime.get("live_instrument_code"),
                "contract_month": decision_month or None,
                "session_variant": quote_runtime.get("live_session_variant"),
            },
            "same_contract_settlement_reference": {
                "quote_code": settlement.get("quote_code") if settlement_ok else None,
                "contract_month": settlement_month or None,
            },
            "governed_settlement_prediction_target": "SEPARATE_PRODUCT_NOT_INFERRED_FROM_TRADING_PATH",
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
            "TARGET_LATEST_LIVE_OR_SESSION_PRICE": current_price,
            "TARGET_LATEST_WATCHLIST_DEAL": quote_runtime.get("live_price"),
            "TARGET_LATEST_WATCHLIST_DEAL_AT": quote_runtime.get("live_price_at"),
            "TARGET_LATEST_PRICE_LIVE_NOW_VERIFIED": bool(quote_runtime.get("live_price_verified")),
            "TARGET_MICROSTRUCTURE_LIVE_VERIFIED": bool(
                quote_runtime.get("microstructure_live_verified")
            ),
            "TARGET_PREVIOUS_DAY_CLOSE": day.get("verified_close_price"),
            "TARGET_PREVIOUS_NIGHT_CLOSE": night.get("verified_close_price"),
            "night_close_available": bool(night.get("verified_close")),
            "latest_night_observation_is_close": bool(night.get("verified_close")),
        },
        "day_session": day,
        "night_session": night,
        "market_structure": structure,
        "acceptance": acceptance,
        "first_passage_label": first_passage,
        "session_settlement_excursion": session_settlement_excursion,
        "session_materialization": {
            "used": bool(use_materialized),
            "artifact_status": materialized_artifact.get("status"),
            "artifact_path": materialized_artifact.get("artifact_path"),
            "artifact_age_seconds": materialized_artifact.get("artifact_age_seconds"),
            "fallback_to_bounded_parquet": bool(trade_rows is None and not use_materialized),
            "fallback_reason": (
                materialized_artifact.get("reason")
                if not use_materialized
                else None
            ),
            "source_semantics": (
                "INCREMENTAL_VERIFIED_STOCKTICK_MATERIALIZATION"
                if use_materialized
                else "BOUNDED_DURABLE_PARQUET"
            ),
        },
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
            "model_quantiles_are_market_structure_levels": False,
            "model_quantiles_may_drive_acceptance": False,
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
    runtime = result.get("quote_runtime") or {}
    latest = price.get("TARGET_LATEST_LIVE_OR_SESSION_PRICE")
    live_code = runtime.get("live_instrument_code") or decision.get("quote_code") or "JNU"

    if latest is None:
        latest_text = "目前沒有可用的真實 JNU Micro session 成交價"
    elif price.get("TARGET_LATEST_PRICE_LIVE_NOW_VERIFIED"):
        latest_text = f"{float(latest):,.0f} 點（{live_code}，新鮮 Watchlist deal）"
    else:
        latest_text = f"{float(latest):,.0f} 點（{live_code}，歷史/最新可用 session observation）"

    night_close = price.get("TARGET_PREVIOUS_NIGHT_CLOSE")
    return {
        "產品分層": {
            "同限月官方清算價參考": "只作 live trading contract 的同限月已公布 settlement reference",
            "正式清算價預測": "屬於另一個 governed settlement prediction product；本工具不把兩者混為目前合約",
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
            "證據限制": "描述性規則，不是方向概率；Price Activity 不等於成交量；Volume Profile 只有 verified StockTick DealPrice/DealVol 足夠時才可用，否則 fail-closed；模型 P10/P90 不得當支撐壓力或 Acceptance 水位。",
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
