"""V2-A.2 — Venue Session Truth (venue / session / trading-day contract).

RESEARCH ONLY. Machine-enforced session truth for the multi-factor runtime:

    MARKET OPEN != FEED FRESH
    FUTURES OPEN != LIVE DATA AVAILABLE
    TRADING DATE != LOCAL CALENDAR DATE FOR NIGHT SESSIONS
    XTKS CASH CLOSED != OSE DERIVATIVES CLOSED

This module answers, per venue and as-of instant: is a session open, which session, and which
trading day does the instant belong to. It never claims a live quote and never fabricates a
holiday calendar it does not have.

Cash trading-day calendars (XTAI / XTKS / XNAS / XNYS) reuse `exchange_calendars` (verified).
Intraday session hours for cash venues are taken from the calendar session open/close (and break),
so `^N225` / TAIEX cash are NOT reported OPEN for the whole local calendar day.

Derivatives session hours (OSE / TAIFEX / CME) are documented exchange rules, with holiday status
kept UNKNOWN unless a verified calendar exists.

Schema: V2_SESSION_TRUTH_SCHEMA_VERSION = "2A.2".
"""
from __future__ import annotations

from dataclasses import dataclass, field as dfield, asdict
from datetime import date, datetime, time, timedelta, timezone
from typing import Any

from market_ai_hub.research.v2.asof import ensure_utc_aware

V2_SESSION_TRUTH_SCHEMA_VERSION = "2A.2"

# ── session statuses ──
SESSION_STATUSES = (
    "REGULAR_SESSION", "AFTER_HOURS_SESSION", "NIGHT_SESSION",
    "PRE_MARKET", "POST_MARKET", "MAINTENANCE", "CLOSED", "HOLIDAY_CLOSED", "UNKNOWN",
)
# statuses that mean "some trading session is currently active"
TRADING_SESSION_STATUSES = ("REGULAR_SESSION", "AFTER_HOURS_SESSION", "NIGHT_SESSION",
                            "PRE_MARKET", "POST_MARKET")

HOLIDAY_STATUSES = ("VERIFIED_CALENDAR", "PARTIAL_HOLIDAY_TRADING", "UNKNOWN")
EXPIRY_EXCEPTION_STATUSES = ("NOT_APPLICABLE", "APPLIED", "UNKNOWN")
VERIFICATION_STATUSES = ("EXCHANGE_CALENDAR_VERIFIED", "SESSION_HOURS_VERIFIED", "UNVERIFIED", "UNKNOWN")

# OSE derivative sub-sessions (day opening 08:45 / regular through 15:40 / closing auction 15:45;
# night opening 17:00 / regular through 05:55 / closing 06:00).
_OSE_DAY_OPEN = time(8, 45)
_OSE_DAY_AUCTION = time(15, 40)
_OSE_DAY_CLOSE = time(15, 45)
_OSE_NIGHT_OPEN = time(17, 0)
_OSE_NIGHT_AUCTION = time(5, 55)
_OSE_NIGHT_CLOSE = time(6, 0)

# TAIFEX regular 08:45-13:45, after-hours 15:00-05:00 next day; expiring contract regular ends 13:30.
_TAIFEX_REG_OPEN = time(8, 45)
_TAIFEX_REG_CLOSE = time(13, 45)
_TAIFEX_EXPIRY_REG_CLOSE = time(13, 30)
_TAIFEX_AH_OPEN = time(15, 0)
_TAIFEX_AH_CLOSE = time(5, 0)

# US cash extended hours (ET).
_US_PRE_OPEN = time(4, 0)
_US_REG_OPEN = time(9, 30)
_US_REG_CLOSE = time(16, 0)
_US_POST_CLOSE = time(20, 0)

# CME Globex (America/Chicago): Sun 17:00 -> Fri 16:00, daily maintenance 16:00-17:00.
_CME_OPEN = time(17, 0)
_CME_CLOSE = time(16, 0)


VENUE_REGISTRY: dict[str, dict] = {
    "XTAI": {"timezone": "Asia/Taipei", "calendar_kind": "CASH", "session_kind": "CASH_EQUITY",
             "calendar_name": "XTAI"},
    "XTKS": {"timezone": "Asia/Tokyo", "calendar_kind": "CASH", "session_kind": "CASH_EQUITY",
             "calendar_name": "XTKS"},
    "XNAS": {"timezone": "America/New_York", "calendar_kind": "CASH", "session_kind": "US_CASH_EQUITY",
             "calendar_name": "XNAS"},
    "XNYS": {"timezone": "America/New_York", "calendar_kind": "CASH", "session_kind": "US_CASH_EQUITY",
             "calendar_name": "XNYS"},
    "CBOE": {"timezone": "America/New_York", "calendar_kind": "CASH", "session_kind": "US_CASH_EQUITY",
             "calendar_name": "XNYS"},
    "OSE_DERIVATIVES": {"timezone": "Asia/Tokyo", "calendar_kind": "DERIVATIVES",
                        "session_kind": "JPX_DERIVATIVES", "calendar_name": "OSE_DERIVATIVES"},
    "TAIFEX_DERIVATIVES": {"timezone": "Asia/Taipei", "calendar_kind": "DERIVATIVES",
                           "session_kind": "TAIFEX", "calendar_name": "TAIFEX"},
    "CME": {"timezone": "America/Chicago", "calendar_kind": "DERIVATIVES",
            "session_kind": "CME_GLOBEX", "calendar_name": "CME_GLOBEX"},
    "FX_OTC": {"timezone": "UTC", "calendar_kind": "OTC", "session_kind": "FX_SPOT",
               "calendar_name": "FX_OTC"},
    "CRYPTO_24_7": {"timezone": "UTC", "calendar_kind": "OTC", "session_kind": "CRYPTO_24_7",
                    "calendar_name": "CRYPTO_24_7"},
}

# explicit symbol -> venue mapping; no "unknown -> TWSE" fallback
_SYMBOL_VENUE = {
    "^N225": "XTKS", "^TPX": "XTKS",
    "^TWII": "XTAI",
    "^VIX": "CBOE", "^VIX9D": "CBOE", "^VXN": "CBOE",
    "^SOX": "XNAS", "^NDX": "XNAS", "^GSPC": "XNYS", "^DJI": "XNYS",
    "^TNX": "XNYS", "^FVX": "XNYS", "^TYX": "XNYS", "^IRX": "XNYS",
    "NKD=F": "CME", "NQ=F": "CME", "MNQ=F": "CME", "ES=F": "CME", "MES=F": "CME",
    "GC=F": "CME", "CL=F": "CME",
    "TX": "TAIFEX_DERIVATIVES", "MTX": "TAIFEX_DERIVATIVES", "TMF": "TAIFEX_DERIVATIVES",
    "UNF": "TAIFEX_DERIVATIVES",
    "USDJPY=X": "FX_OTC", "JPY=X": "FX_OTC",
    "BTC-USD": "CRYPTO_24_7",
}


def venue_ids() -> tuple[str, ...]:
    return tuple(VENUE_REGISTRY)


def is_known_venue(venue_id: str) -> bool:
    return venue_id in VENUE_REGISTRY


def venue_timezone(venue_id: str) -> str | None:
    v = VENUE_REGISTRY.get(venue_id)
    return v["timezone"] if v else None


def venue_for_symbol(symbol: str) -> str | None:
    """Explicit symbol -> venue mapping. Returns None for unknown (never defaults to TWSE)."""
    s = (symbol or "").strip().upper()
    if s in _SYMBOL_VENUE:
        return _SYMBOL_VENUE[s]
    if s.startswith("^TWII"):
        return "XTAI"
    if s.endswith(".TW") or s.endswith(".TWO"):
        return "XTAI"
    body = s.split(".")[0]
    if body.isdigit():
        return "XTAI"
    return None


# ── context ──
@dataclass
class VenueSessionContext:
    venue_id: str = ""
    calendar_id: str = ""
    timezone: str = ""
    asof_timestamp: datetime | None = None
    local_timestamp: datetime | None = None
    trading_date: str = ""
    session_id: str = ""
    session_status: str = "UNKNOWN"
    session_open_timestamp: datetime | None = None
    session_close_timestamp: datetime | None = None
    market_open: bool = False
    tradable_now: bool = False
    trading_day_assignment_rule: str = ""
    sub_session: str = ""
    holiday_status: str = "UNKNOWN"
    expiry_exception_status: str = "NOT_APPLICABLE"
    verification_status: str = "UNKNOWN"
    schema_version: str = V2_SESSION_TRUTH_SCHEMA_VERSION

    def __post_init__(self):
        if self.session_status not in SESSION_STATUSES:
            raise ValueError(f"unknown session_status: {self.session_status!r}")

    def model_dump(self) -> dict:
        return asdict(self)


def _cal(calendar_name: str):
    try:
        import exchange_calendars as xcals
        return xcals.get_calendar(calendar_name)
    except Exception:
        return None


def _local(asof: datetime, tz: str) -> datetime:
    return ensure_utc_aware(asof).astimezone(timezone.utc).astimezone(_zone(tz))


def _zone(tz: str):
    import zoneinfo
    return zoneinfo.ZoneInfo(tz)


def _tz_timestamp(value: Any, tz: str) -> datetime | None:
    """exchange_calendars returns UTC tz-aware Timestamps; normalize to tz-aware UTC datetime."""
    if value is None:
        return None
    try:
        import pandas as pd
        if pd.isna(value):
            return None
    except Exception:
        pass
    return ensure_utc_aware(value)


def _is_weekend(d: date) -> bool:
    return d.weekday() >= 5


def _cash_session(venue_id: str, asof: datetime) -> VenueSessionContext:
    info = VENUE_REGISTRY[venue_id]
    tz = info["timezone"]
    local = _local(asof, tz)
    cal = _cal(info["calendar_name"])
    ctx = VenueSessionContext(
        venue_id=venue_id, calendar_id=info["calendar_name"], timezone=tz,
        asof_timestamp=ensure_utc_aware(asof), local_timestamp=local,
        holiday_status="VERIFIED_CALENDAR" if cal is not None else "UNKNOWN",
        verification_status="EXCHANGE_CALENDAR_VERIFIED" if cal is not None else "UNVERIFIED",
    )
    if cal is None:
        ctx.session_status = "UNKNOWN"
        ctx.trading_day_assignment_rule = "NO_CALENDAR"
        ctx.session_id = f"{venue_id}|UNKNOWN"
        return ctx

    day = local.date()
    is_session_day = bool(cal.is_session(day))
    next_sessions = cal.sessions_in_range(day, day + timedelta(days=10))
    next_name = str(next_sessions[0].date()) if len(next_sessions) else ""

    if info["session_kind"] == "US_CASH_EQUITY":
        # US cash: PRE_MARKET / REGULAR_SESSION / POST_MARKET / CLOSED on session days; else HOLIDAY_CLOSED.
        if not is_session_day:
            ctx.session_status = "CLOSED" if _is_weekend(day) else "HOLIDAY_CLOSED"
            ctx.trading_date = next_name
            ctx.trading_day_assignment_rule = "NEXT_VERIFIED_CASH_SESSION"
        else:
            t = local.time()
            if _US_REG_OPEN <= t < _US_REG_CLOSE:
                ctx.session_status = "REGULAR_SESSION"
                ctx.trading_date = day.isoformat()
            elif _US_PRE_OPEN <= t < _US_REG_OPEN:
                ctx.session_status = "PRE_MARKET"
                ctx.trading_date = day.isoformat()
            elif _US_REG_CLOSE <= t < _US_POST_CLOSE:
                ctx.session_status = "POST_MARKET"
                ctx.trading_date = day.isoformat()
            else:
                ctx.session_status = "CLOSED"
                ctx.trading_date = next_name
            ctx.trading_day_assignment_rule = "LOCAL_CASH_SESSION_DATE"
            try:
                ctx.session_open_timestamp = _tz_timestamp(cal.session_open(day), tz)
                ctx.session_close_timestamp = _tz_timestamp(cal.session_close(day), tz)
            except Exception:
                pass
    else:
        # XTAI / XTKS: intraday open/close from the verified calendar (not whole-day open).
        if not is_session_day:
            ctx.session_status = "CLOSED" if _is_weekend(day) else "HOLIDAY_CLOSED"
            ctx.trading_date = next_name
            ctx.trading_day_assignment_rule = "NEXT_VERIFIED_CASH_SESSION"
        else:
            ctx.trading_date = day.isoformat()
            ctx.trading_day_assignment_rule = "LOCAL_CASH_SESSION_DATE"
            try:
                if bool(cal.is_open_on_minute(ensure_utc_aware(asof))):
                    ctx.session_status = "REGULAR_SESSION"
                else:
                    ctx.session_status = "CLOSED"
                ctx.session_open_timestamp = _tz_timestamp(cal.session_open(day), tz)
                ctx.session_close_timestamp = _tz_timestamp(cal.session_close(day), tz)
            except Exception:
                ctx.session_status = "UNKNOWN"
    ctx.market_open = ctx.session_status in TRADING_SESSION_STATUSES
    ctx.tradable_now = ctx.market_open
    ctx.session_id = f"{venue_id}|{ctx.trading_date}|{ctx.session_status}"
    return ctx


def _ose_session(asof: datetime) -> VenueSessionContext:
    from market_ai_hub.services.calendar import (
        is_ose_derivatives_session, next_ose_derivatives_session,
    )

    info = VENUE_REGISTRY["OSE_DERIVATIVES"]
    tz = info["timezone"]
    local = _local(asof, tz)
    t = local.time()
    d = local.date()
    ctx = VenueSessionContext(
        venue_id="OSE_DERIVATIVES", calendar_id="OSE_DERIVATIVES", timezone=tz,
        asof_timestamp=ensure_utc_aware(asof), local_timestamp=local,
        holiday_status="PARTIAL_HOLIDAY_TRADING",
        verification_status="SESSION_HOURS_VERIFIED",
        trading_day_assignment_rule="OSE_TRADING_DAY_BEGINS_WITH_NIGHT_SESSION",
    )

    # night window checked first: 17:00 -> 06:00 next day (a 03:00 instant belongs to the prior evening)
    start_date = None
    sub = ""
    if t >= _OSE_NIGHT_OPEN:
        start_date, sub = d, ("NIGHT_REGULAR" if t < _OSE_NIGHT_AUCTION else "NIGHT_CLOSING")
    elif t <= _OSE_NIGHT_CLOSE:
        start_date, sub = d - timedelta(days=1), ("NIGHT_CLOSING" if t >= _OSE_NIGHT_AUCTION else "NIGHT_REGULAR")

    if start_date is not None and not _is_weekend(start_date) and is_ose_derivatives_session(start_date):
        ctx.session_status = "NIGHT_SESSION"
        ctx.sub_session = sub
        ctx.trading_date = next_ose_derivatives_session(start_date) or ""
        ctx.session_open_timestamp = ensure_utc_aware(
            datetime.combine(start_date, _OSE_NIGHT_OPEN, tzinfo=_zone(tz)))
        ctx.session_close_timestamp = ensure_utc_aware(
            datetime.combine(start_date + timedelta(days=1), _OSE_NIGHT_CLOSE, tzinfo=_zone(tz)))
    elif _OSE_DAY_OPEN <= t <= _OSE_DAY_CLOSE and is_ose_derivatives_session(d):
        ctx.session_status = "REGULAR_SESSION"
        ctx.trading_date = d.isoformat()
        ctx.sub_session = "DAY_REGULAR" if t < _OSE_DAY_AUCTION else "DAY_CLOSING_AUCTION"
        ctx.session_open_timestamp = ensure_utc_aware(datetime.combine(d, _OSE_DAY_OPEN, tzinfo=_zone(tz)))
        ctx.session_close_timestamp = ensure_utc_aware(datetime.combine(d, _OSE_DAY_CLOSE, tzinfo=_zone(tz)))
    else:
        if _is_weekend(d) or is_ose_derivatives_session(d):
            ctx.session_status = "CLOSED"  # weekend, or a session day outside day/night hours
        else:
            ctx.session_status = "HOLIDAY_CLOSED"
        ctx.trading_date = next_ose_derivatives_session(d) or ""
    ctx.market_open = ctx.session_status in TRADING_SESSION_STATUSES
    ctx.tradable_now = ctx.market_open
    ctx.session_id = f"OSE_DERIVATIVES|{ctx.trading_date}|{ctx.session_status}"
    return ctx


def _taifex_session(asof: datetime, *, is_expiring_contract: bool | None) -> VenueSessionContext:
    from market_ai_hub.services.calendar import is_session, next_trading_sessions

    info = VENUE_REGISTRY["TAIFEX_DERIVATIVES"]
    tz = info["timezone"]
    local = _local(asof, tz)
    t = local.time()
    d = local.date()
    expiry_status = "NOT_APPLICABLE"
    if is_expiring_contract is True:
        expiry_status = "APPLIED"
    elif is_expiring_contract is None:
        expiry_status = "UNKNOWN"
    ctx = VenueSessionContext(
        venue_id="TAIFEX_DERIVATIVES", calendar_id="TAIFEX", timezone=tz,
        asof_timestamp=ensure_utc_aware(asof), local_timestamp=local,
        holiday_status="UNKNOWN",
        verification_status="SESSION_HOURS_VERIFIED",
        expiry_exception_status=expiry_status,
        trading_day_assignment_rule="AFTER_HOURS_BELONGS_TO_NEXT_VERIFIED_XTAI_SESSION",
    )

    # after-hours window checked first: 15:00 -> 05:00 next day
    start_date = None
    if t >= _TAIFEX_AH_OPEN:
        start_date = d
    elif t <= _TAIFEX_AH_CLOSE:
        start_date = d - timedelta(days=1)
    ah_held = (start_date is not None and not _is_weekend(start_date)
               and is_session("^TWII", start_date))

    reg_close = _TAIFEX_EXPIRY_REG_CLOSE if is_expiring_contract is True else _TAIFEX_REG_CLOSE
    if _TAIFEX_REG_OPEN <= t <= reg_close and is_session("^TWII", d):
        ctx.session_status = "REGULAR_SESSION"
        ctx.trading_date = d.isoformat()
        ctx.sub_session = "EXPIRY_DAY_REGULAR" if is_expiring_contract is True else "DAY_REGULAR"
        ctx.session_open_timestamp = ensure_utc_aware(datetime.combine(d, _TAIFEX_REG_OPEN, tzinfo=_zone(tz)))
        ctx.session_close_timestamp = ensure_utc_aware(datetime.combine(d, reg_close, tzinfo=_zone(tz)))
    elif (is_expiring_contract is True) and ah_held:
        # expiring contract has no after-hours session
        ctx.session_status = "CLOSED"
        ctx.trading_date = (next_trading_sessions("^TWII", start_date, 1) or [""])[0]
    elif ah_held:
        ctx.session_status = "AFTER_HOURS_SESSION"
        ctx.sub_session = "AFTER_HOURS_REGULAR"
        ctx.trading_date = (next_trading_sessions("^TWII", start_date, 1) or [""])[0]
        ctx.session_open_timestamp = ensure_utc_aware(
            datetime.combine(start_date, _TAIFEX_AH_OPEN, tzinfo=_zone(tz)))
        ctx.session_close_timestamp = ensure_utc_aware(
            datetime.combine(start_date + timedelta(days=1), _TAIFEX_AH_CLOSE, tzinfo=_zone(tz)))
    else:
        ctx.session_status = "CLOSED"
        ctx.trading_date = (next_trading_sessions("^TWII", d, 1) or [""])[0]
    ctx.market_open = ctx.session_status in TRADING_SESSION_STATUSES
    ctx.tradable_now = ctx.market_open
    ctx.session_id = f"TAIFEX|{ctx.trading_date}|{ctx.session_status}"
    return ctx


def _cme_session(asof: datetime) -> VenueSessionContext:
    tz = VENUE_REGISTRY["CME"]["timezone"]
    local = _local(asof, tz)
    t = local.time()
    d = local.date()
    ctx = VenueSessionContext(
        venue_id="CME", calendar_id="CME_GLOBEX", timezone=tz,
        asof_timestamp=ensure_utc_aware(asof), local_timestamp=local,
        holiday_status="UNKNOWN",  # no verified Globex holiday calendar
        verification_status="SESSION_HOURS_VERIFIED",
        trading_day_assignment_rule="LOCAL_CALENDAR_DATE_HOLIDAY_UNVERIFIED",
        trading_date=d.isoformat(),
    )
    weekday = d.weekday()  # Mon=0 .. Sun=6
    # Globex maintenance 16:00-17:00 CT every day
    if _CME_CLOSE <= t < _CME_OPEN:
        ctx.session_status = "MAINTENANCE"
    elif weekday == 5:  # Saturday: fully closed
        ctx.session_status = "CLOSED"
    elif weekday == 6:  # Sunday: open only from 17:00 CT
        ctx.session_status = "REGULAR_SESSION" if t >= _CME_OPEN else "CLOSED"
    elif weekday == 4:  # Friday: closes at 16:00 CT
        ctx.session_status = "REGULAR_SESSION" if t < _CME_CLOSE else "CLOSED"
    else:
        ctx.session_status = "REGULAR_SESSION"
    ctx.sub_session = "GLOBEX" if ctx.session_status == "REGULAR_SESSION" else ""
    ctx.market_open = ctx.session_status in TRADING_SESSION_STATUSES
    ctx.tradable_now = ctx.market_open
    ctx.session_id = f"CME|{ctx.trading_date}|{ctx.session_status}"
    return ctx


def _fx_session(asof: datetime) -> VenueSessionContext:
    tz = VENUE_REGISTRY["FX_OTC"]["timezone"]
    local = _local(asof, tz)
    ctx = VenueSessionContext(
        venue_id="FX_OTC", calendar_id="FX_OTC", timezone=tz,
        asof_timestamp=ensure_utc_aware(asof), local_timestamp=local,
        holiday_status="UNKNOWN", verification_status="SESSION_HOURS_VERIFIED",
        trading_day_assignment_rule="WEEKDAY_UTC_ONLY",
    )
    ctx.session_status = "CLOSED" if _is_weekend(local.date()) else "REGULAR_SESSION"
    ctx.trading_date = local.date().isoformat()
    ctx.market_open = ctx.session_status in TRADING_SESSION_STATUSES
    ctx.tradable_now = ctx.market_open
    ctx.session_id = f"FX_OTC|{ctx.trading_date}|{ctx.session_status}"
    return ctx


def _crypto_session(asof: datetime) -> VenueSessionContext:
    tz = VENUE_REGISTRY["CRYPTO_24_7"]["timezone"]
    local = _local(asof, tz)
    ctx = VenueSessionContext(
        venue_id="CRYPTO_24_7", calendar_id="CRYPTO_24_7", timezone=tz,
        asof_timestamp=ensure_utc_aware(asof), local_timestamp=local,
        holiday_status="UNKNOWN", verification_status="SESSION_HOURS_VERIFIED",
        trading_day_assignment_rule="UTC_CALENDAR_DATE",
    )
    ctx.session_status = "REGULAR_SESSION"
    ctx.trading_date = local.date().isoformat()
    ctx.market_open = True
    ctx.tradable_now = True
    ctx.session_id = f"CRYPTO_24_7|{ctx.trading_date}|{ctx.session_status}"
    return ctx


def resolve_venue_session(
    venue_id: str,
    asof_timestamp: datetime | None = None,
    *,
    contract_code: str = "",
    contract_month: str = "",
    is_expiring_contract: bool | None = None,
) -> VenueSessionContext:
    """Resolve venue session truth for an as-of instant. Unknown venue -> UNKNOWN (fail closed)."""
    asof = ensure_utc_aware(asof_timestamp) if asof_timestamp is not None else datetime.now(timezone.utc)
    if not is_known_venue(venue_id):
        return VenueSessionContext(
            venue_id=venue_id or "", asof_timestamp=asof, session_status="UNKNOWN",
            holiday_status="UNKNOWN", verification_status="UNKNOWN",
            trading_day_assignment_rule="UNKNOWN_VENUE",
            session_id=f"{venue_id or 'UNKNOWN'}|UNKNOWN",
        )
    info = VENUE_REGISTRY[venue_id]
    if info["session_kind"] == "JPX_DERIVATIVES":
        return _ose_session(asof)
    if info["session_kind"] == "TAIFEX":
        return _taifex_session(asof, is_expiring_contract=is_expiring_contract)
    if info["session_kind"] == "CME_GLOBEX":
        return _cme_session(asof)
    if info["session_kind"] == "FX_SPOT":
        return _fx_session(asof)
    if info["session_kind"] == "CRYPTO_24_7":
        return _crypto_session(asof)
    return _cash_session(venue_id, asof)


def resolve_symbol_session(symbol: str, asof_timestamp: datetime | None = None) -> VenueSessionContext | None:
    """Resolve session truth for a symbol. None when the symbol has no explicit venue."""
    venue = venue_for_symbol(symbol)
    if venue is None:
        return None
    return resolve_venue_session(venue, asof_timestamp)
