"""Incremental JNU session facts from verified Yuanta StockTick callbacks.

This is a compact, descriptive evidence layer.  It does not create forecasts,
probabilities, support/resistance, or execution guidance.  Raw recorder
Parquet remains the source-of-record; this artifact exists to avoid rescanning
thousands of tiny files on each live analysis request.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, time, timedelta, timezone
import math
from pathlib import Path
import threading
import time as time_module
from typing import Any
from zoneinfo import ZoneInfo

from market_ai_hub.integrations.yuanta.durable_spool import durable_json_replace


SCHEMA_VERSION = "JNU.SESSION.MATERIALIZED.2"
JST = ZoneInfo("Asia/Tokyo")
TICK_POINTS = 5.0
PERSIST_INTERVAL_SECONDS = 1.0
MATERIALIZED_MAX_AGE_SECONDS = 120.0
MAX_SESSIONS = 12
MAX_RECENT_TICK_IDS = 1024
_JNU_PREFIXES = ("JNU", "JNUPM")


def materialized_path(recorder_root: Path) -> Path:
    return Path(recorder_root) / "materialized" / "jnu_sessions.json"


def _finite_positive(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) and out > 0 else None


def _finite_nonnegative(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) and out >= 0 else None


def _contract_month(code: str) -> str:
    text = str(code or "").upper()
    if text.startswith("JNUPM") and len(text) == 9 and text[-4:].isdigit():
        yymm = text[-4:]
        return f"20{yymm[:2]}{yymm[2:]}"
    if text.startswith("JNU") and len(text) == 7 and text[-4:].isdigit():
        yymm = text[-4:]
        return f"20{yymm[:2]}{yymm[2:]}"
    return ""


def _base_quote_code(code: str) -> str:
    month = _contract_month(code)
    return f"JNU{month[-4:]}" if month else ""


def _session_variant(code: str) -> str:
    return "NIGHT" if str(code or "").upper().startswith("JNUPM") else "DAY"


def _source_time(payload: dict[str, Any], received_at: datetime) -> datetime:
    raw = str(payload.get("source_time_of_day") or "")
    try:
        hh, mm, tail = raw.split(":")
        ss = float(tail)
        tod = time(int(hh), int(mm), int(ss), int(round((ss % 1) * 1_000_000)))
    except Exception:
        return received_at.astimezone(JST)
    local_received = received_at.astimezone(JST)
    candidates = [
        datetime.combine(local_received.date() + timedelta(days=offset), tod, tzinfo=JST)
        for offset in (-1, 0, 1)
    ]
    return min(candidates, key=lambda x: abs((x - local_received).total_seconds()))


def _session_start_date(event_local: datetime, session: str) -> date:
    if session == "NIGHT" and event_local.time() <= time(6, 0):
        return event_local.date() - timedelta(days=1)
    return event_local.date()


def expected_bounds(session: str, start_date: date) -> tuple[datetime, datetime]:
    if session == "DAY":
        return (
            datetime.combine(start_date, time(8, 45), tzinfo=JST),
            datetime.combine(start_date, time(15, 45), tzinfo=JST),
        )
    return (
        datetime.combine(start_date, time(17, 0), tzinfo=JST),
        datetime.combine(start_date + timedelta(days=1), time(6, 0), tzinfo=JST),
    )


def _bar_start(event_local: datetime) -> datetime:
    minute = (event_local.minute // 5) * 5
    return event_local.replace(minute=minute, second=0, microsecond=0)


def _session_key(base_code: str, session: str, start_date: date) -> str:
    return f"{base_code}|{session}|{start_date.isoformat()}"


def _new_session(
    *,
    code: str,
    session: str,
    start_date: date,
    event_local: datetime,
    received_at: datetime,
    price: float,
    volume: float,
    serial_no: str,
    runtime_build_id: str,
) -> dict[str, Any]:
    expected_start, expected_end = expected_bounds(session, start_date)
    start_lag = (event_local - expected_start).total_seconds()
    open_observed = 0.0 <= start_lag <= 60.0
    return {
        "schema_version": SCHEMA_VERSION,
        "base_quote_code": _base_quote_code(code),
        "live_quote_code": code,
        "contract_month": _contract_month(code),
        "session": session,
        "session_start_date": start_date.isoformat(),
        "expected_session_open": expected_start.astimezone(timezone.utc).isoformat(),
        "expected_session_close": expected_end.astimezone(timezone.utc).isoformat(),
        "first_event_at": event_local.astimezone(timezone.utc).isoformat(),
        "last_event_at": event_local.astimezone(timezone.utc).isoformat(),
        "last_received_at": received_at.astimezone(timezone.utc).isoformat(),
        "first_observed_price": price,
        "latest_price": price,
        "observed_high": price,
        "observed_low": price,
        "observed_range_points": 0.0,
        "session_open": price if open_observed else None,
        "open_boundary_observed": open_observed,
        "verified_close": False,
        "verified_close_price": None,
        "coverage_complete": False,
        "close_semantics": "LAST_OBSERVED_SESSION_PRICE_NOT_SESSION_CLOSE",
        "total_volume": 0.0,
        "trade_count": 0,
        "sum_price_volume": 0.0,
        "vwap": None,
        "mfe_from_session_open": 0.0 if open_observed else None,
        "mae_from_session_open": 0.0 if open_observed else None,
        "opening_range_minutes": 30,
        "opening_range_high": None,
        "opening_range_low": None,
        "opening_range_complete": False,
        "bars": {},
        "price_volume_bins": {},
        "price_trade_bins": {},
        "first_serial_no": serial_no or None,
        "last_serial_no": serial_no or None,
        "recent_tick_ids": [],
        "source_provenance": {
            "provider": "YUANTA_SPARK",
            "callback_type": "SubscribeStockTick",
            "price_field": "DealPrice",
            "volume_field": "DealVol",
            "timestamp_field": "source_time_of_day",
            "runtime_build_id": runtime_build_id,
        },
        "label_ready": False,
        "partial_reason": "SESSION_BOUNDARIES_NOT_FULLY_OBSERVED",
    }


def _tick_id(payload: dict[str, Any]) -> str:
    return "|".join(
        str(payload.get(k) or "")
        for k in ("instrument_code", "SerialNo", "source_time_of_day", "DealPrice", "DealVol")
    )


def update_session(
    session: dict[str, Any],
    *,
    event_local: datetime,
    received_at: datetime,
    price: float,
    volume: float,
    serial_no: str,
    tick_id: str,
) -> bool:
    recent = list(session.get("recent_tick_ids") or [])
    if tick_id and tick_id in recent:
        return False
    if tick_id:
        recent.append(tick_id)
        session["recent_tick_ids"] = recent[-MAX_RECENT_TICK_IDS:]

    session["last_event_at"] = event_local.astimezone(timezone.utc).isoformat()
    session["last_received_at"] = received_at.astimezone(timezone.utc).isoformat()
    session["latest_price"] = price
    session["observed_high"] = max(float(session["observed_high"]), price)
    session["observed_low"] = min(float(session["observed_low"]), price)
    session["observed_range_points"] = float(session["observed_high"]) - float(session["observed_low"])
    session["trade_count"] = int(session.get("trade_count", 0)) + 1
    session["total_volume"] = float(session.get("total_volume", 0.0)) + volume
    session["sum_price_volume"] = float(session.get("sum_price_volume", 0.0)) + price * volume
    if session["total_volume"] > 0:
        session["vwap"] = session["sum_price_volume"] / session["total_volume"]
    session["last_serial_no"] = serial_no or session.get("last_serial_no")

    if session.get("session_open") is not None:
        open_px = float(session["session_open"])
        session["mfe_from_session_open"] = float(session["observed_high"]) - open_px
        session["mae_from_session_open"] = float(session["observed_low"]) - open_px

    expected_start = datetime.fromisoformat(session["expected_session_open"]).astimezone(JST)
    expected_end = datetime.fromisoformat(session["expected_session_close"]).astimezone(JST)
    if expected_start <= event_local < expected_start + timedelta(minutes=30):
        session["opening_range_high"] = (
            price if session.get("opening_range_high") is None
            else max(float(session["opening_range_high"]), price)
        )
        session["opening_range_low"] = (
            price if session.get("opening_range_low") is None
            else min(float(session["opening_range_low"]), price)
        )
    session["opening_range_complete"] = bool(
        session.get("open_boundary_observed")
        and event_local >= expected_start + timedelta(minutes=30)
    )

    close_lag = (event_local - expected_end).total_seconds()
    if 0.0 <= close_lag <= 1.0:
        session["verified_close"] = True
        session["verified_close_price"] = price
        session["close_semantics"] = "VERIFIED_SESSION_BOUNDARY_PRINT"
    session["coverage_complete"] = bool(
        session.get("open_boundary_observed") and session.get("verified_close")
    )
    session["label_ready"] = bool(session["coverage_complete"])
    session["partial_reason"] = None if session["coverage_complete"] else "SESSION_BOUNDARIES_NOT_FULLY_OBSERVED"

    bar_key = _bar_start(event_local).astimezone(timezone.utc).isoformat()
    bars = session.setdefault("bars", {})
    bar = bars.get(bar_key)
    if bar is None:
        bars[bar_key] = {
            "bar_start": bar_key,
            "open": price,
            "high": price,
            "low": price,
            "close": price,
            "volume": volume,
            "trades": 1,
        }
    else:
        bar["high"] = max(float(bar["high"]), price)
        bar["low"] = min(float(bar["low"]), price)
        bar["close"] = price
        bar["volume"] = float(bar.get("volume", 0.0)) + volume
        bar["trades"] = int(bar.get("trades", 0)) + 1

    bin_key = f"{round(price / TICK_POINTS) * TICK_POINTS:.1f}"
    volume_bins = session.setdefault("price_volume_bins", {})
    trade_bins = session.setdefault("price_trade_bins", {})
    volume_bins[bin_key] = float(volume_bins.get(bin_key, 0.0)) + volume
    trade_bins[bin_key] = int(trade_bins.get(bin_key, 0)) + 1
    return True


class JNUSessionMaterializer:
    def __init__(
        self,
        recorder_root: Path,
        *,
        runtime_build_id: str = "",
        persist_interval_seconds: float = PERSIST_INTERVAL_SECONDS,
    ) -> None:
        self.path = materialized_path(recorder_root)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.runtime_build_id = str(runtime_build_id or "")
        self.persist_interval_seconds = max(0.0, float(persist_interval_seconds))
        self._lock = threading.Lock()
        self._last_persist = 0.0
        self._state = {
            "schema_version": SCHEMA_VERSION,
            "updated_at": None,
            "runtime_build_id": self.runtime_build_id,
            "sessions": {},
        }
        self._load_existing()

    def _load_existing(self) -> None:
        if not self.path.exists():
            return
        try:
            import json
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return
        if raw.get("schema_version") != SCHEMA_VERSION or not isinstance(raw.get("sessions"), dict):
            return
        self._state = raw
        self._state["runtime_build_id"] = self.runtime_build_id

    def ingest(self, payload: dict[str, Any]) -> bool:
        if str(payload.get("callback_type") or "") != "SubscribeStockTick":
            return False
        try:
            market_no = int(payload.get("market_no"))
        except (TypeError, ValueError):
            return False
        code = str(payload.get("instrument_code") or "").upper()
        if market_no != 207 or not code.startswith(_JNU_PREFIXES) or not _contract_month(code):
            return False
        price = _finite_positive(payload.get("DealPrice"))
        volume = _finite_nonnegative(payload.get("DealVol"))
        if price is None or volume is None:
            return False
        try:
            received_at = datetime.fromisoformat(str(payload.get("received_at"))).astimezone(timezone.utc)
        except Exception:
            return False
        event_local = _source_time(payload, received_at)
        session_variant = _session_variant(code)
        start_date = _session_start_date(event_local, session_variant)
        key = _session_key(_base_quote_code(code), session_variant, start_date)
        serial_no = str(payload.get("SerialNo") or "")
        tick_id = _tick_id(payload)

        with self._lock:
            sessions = self._state.setdefault("sessions", {})
            session = sessions.get(key)
            if session is None:
                session = _new_session(
                    code=code,
                    session=session_variant,
                    start_date=start_date,
                    event_local=event_local,
                    received_at=received_at,
                    price=price,
                    volume=volume,
                    serial_no=serial_no,
                    runtime_build_id=self.runtime_build_id,
                )
                sessions[key] = session
                changed = update_session(
                    session,
                    event_local=event_local,
                    received_at=received_at,
                    price=price,
                    volume=volume,
                    serial_no=serial_no,
                    tick_id=tick_id,
                )
            else:
                changed = update_session(
                    session,
                    event_local=event_local,
                    received_at=received_at,
                    price=price,
                    volume=volume,
                    serial_no=serial_no,
                    tick_id=tick_id,
                )
            if not changed:
                return False
            self._trim_sessions()
            now = time_module.monotonic()
            if now - self._last_persist >= self.persist_interval_seconds:
                self._persist_locked()
            return True

    def _trim_sessions(self) -> None:
        sessions = self._state.get("sessions", {})
        if len(sessions) <= MAX_SESSIONS:
            return
        ordered = sorted(
            sessions.items(),
            key=lambda item: str(item[1].get("last_event_at") or ""),
            reverse=True,
        )
        self._state["sessions"] = dict(ordered[:MAX_SESSIONS])

    def _persist_locked(self) -> None:
        self._state["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._state["runtime_build_id"] = self.runtime_build_id
        durable_json_replace(self.path, self._state)
        self._last_persist = time_module.monotonic()

    def flush(self) -> None:
        with self._lock:
            self._persist_locked()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return deepcopy(self._state)


def load_materialized_sessions(
    recorder_root: Path,
    *,
    now: datetime | None = None,
    max_age_seconds: float = MATERIALIZED_MAX_AGE_SECONDS,
) -> dict[str, Any]:
    path = materialized_path(recorder_root)
    if not path.exists():
        return {"status": "NOT_AVAILABLE", "reason": "MATERIALIZED_ARTIFACT_MISSING", "path": str(path)}
    try:
        import json
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"status": "NOT_AVAILABLE", "reason": type(exc).__name__, "path": str(path)}
    if raw.get("schema_version") != SCHEMA_VERSION or not isinstance(raw.get("sessions"), dict):
        return {"status": "NOT_AVAILABLE", "reason": "SCHEMA_MISMATCH", "path": str(path)}
    updated_at = raw.get("updated_at")
    try:
        stamp = datetime.fromisoformat(str(updated_at)).astimezone(timezone.utc)
        reference = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
        age = (reference - stamp).total_seconds()
    except Exception:
        age = math.inf
    raw["artifact_path"] = str(path)
    raw["artifact_age_seconds"] = float(age)
    raw["status"] = "FRESH" if 0.0 <= age <= float(max_age_seconds) else "STALE"
    return raw


def select_session(
    artifact: dict[str, Any],
    *,
    contract_month: str,
    session: str | None = None,
) -> dict[str, Any] | None:
    candidates = []
    for value in (artifact.get("sessions") or {}).values():
        if str(value.get("contract_month") or "") != str(contract_month or ""):
            continue
        if session and str(value.get("session") or "") != session:
            continue
        candidates.append(value)
    if not candidates:
        return None
    return deepcopy(max(candidates, key=lambda x: str(x.get("last_event_at") or "")))


def bars_frame(session: dict[str, Any]):
    import pandas as pd
    rows = list((session.get("bars") or {}).values())
    if not rows:
        return pd.DataFrame()
    frame = pd.DataFrame(rows)
    frame["bar_start"] = pd.to_datetime(frame["bar_start"], utc=True, errors="coerce")
    return frame.dropna(subset=["bar_start"]).sort_values("bar_start").set_index("bar_start")


def settlement_excursion(session: dict[str, Any], settlement: float | None) -> dict[str, Any]:
    px = _finite_positive(settlement)
    if px is None:
        return {"status": "NOT_AVAILABLE"}
    return {
        "status": "AVAILABLE",
        "settlement_reference": px,
        "latest_minus_settlement": float(session["latest_price"]) - px,
        "high_minus_settlement": float(session["observed_high"]) - px,
        "low_minus_settlement": float(session["observed_low"]) - px,
        "max_favorable_excursion_up": float(session["observed_high"]) - px,
        "max_adverse_excursion_down": float(session["observed_low"]) - px,
        "not_probability": True,
    }


def first_passage_to_level(
    session: dict[str, Any],
    *,
    level: float | None,
    direction: str,
) -> dict[str, Any]:
    px = _finite_positive(level)
    if px is None:
        return {"status": "LEVEL_REQUIRED", "value": None, "not_probability": True}
    d = str(direction or "").upper()
    if d not in {"UP", "DOWN"}:
        return {"status": "DIRECTION_REQUIRED", "value": None, "not_probability": True}
    bars = bars_frame(session)
    if bars.empty:
        return {"status": "INSUFFICIENT_DATA", "value": None, "not_probability": True}
    touched = bars["high"] >= px if d == "UP" else bars["low"] <= px
    if bool(touched.any()):
        first_index = touched[touched].index[0]
        return {
            "status": "OBSERVED_TRUE",
            "value": True,
            "level": px,
            "direction": d,
            "first_passage_bar_start": first_index.isoformat(),
            "resolution": "5MIN_OHLC",
            "exact_tick_order_not_claimed": True,
            "not_probability": True,
        }
    return {
        "status": "OBSERVED_FALSE" if session.get("coverage_complete") else "OBSERVED_FALSE_SO_FAR",
        "value": False,
        "level": px,
        "direction": d,
        "first_passage_bar_start": None,
        "resolution": "5MIN_OHLC",
        "exact_tick_order_not_claimed": True,
        "not_probability": True,
    }


def label_ready_row(session: dict[str, Any]) -> dict[str, Any]:
    return {
        "instrument": session.get("base_quote_code"),
        "target_family": "OSAKA_MICRO",
        "calendar_id": "OSE_DERIVATIVES",
        "contract_month": session.get("contract_month"),
        "session": session.get("session"),
        "trading_date": session.get("session_start_date"),
        "open": session.get("session_open"),
        "high": session.get("observed_high"),
        "low": session.get("observed_low"),
        "close": session.get("verified_close_price"),
        "vwap": session.get("vwap"),
        "total_volume": session.get("total_volume"),
        "trade_count": session.get("trade_count"),
        "coverage_complete": bool(session.get("coverage_complete")),
        "label_eligible": bool(session.get("label_ready")),
        "series_semantics": "CONTRACT",
        "roll_status": "NONE",
        "asof_status": "ASOF_VERIFIED",
        "source_provenance": deepcopy(session.get("source_provenance") or {}),
    }
