"""Phase V2-A.2 — venue session truth tests (synthetic/local only, no network)."""
from __future__ import annotations

import sys
from datetime import datetime, timezone, timedelta

import pytest

sys.path.insert(0, "src")

from market_ai_hub.research.v2 import session_truth as ST
from market_ai_hub.services import calendar as cal

JST = timezone(timedelta(hours=9))
TPE = timezone(timedelta(hours=8))
CT = timezone(timedelta(hours=-5))
ET = timezone(timedelta(hours=-4))


def _ose(dt): return ST.resolve_venue_session("OSE_DERIVATIVES", dt)
def _taifex(dt, **kw): return ST.resolve_venue_session("TAIFEX_DERIVATIVES", dt, **kw)
def _cme(dt): return ST.resolve_venue_session("CME", dt)
def _xtks(dt): return ST.resolve_venue_session("XTKS", dt)
def _xtai(dt): return ST.resolve_venue_session("XTAI", dt)


# ── §52 source-level mapping ──
def test_exchange_for_symbol_cash_mappings():
    assert cal.exchange_for_symbol("^N225") == "TSE"
    assert cal.exchange_for_symbol("^TWII") == "TWSE"
    assert cal.exchange_for_symbol("2330.TW") == "TWSE"
    assert cal.exchange_for_symbol("2330") == "TWSE"


def test_exchange_for_symbol_derivatives_not_twse():
    for sym in ("NQ=F", "ES=F", "NKD=F", "TX", "MTX", "TMF", "UNF"):
        assert cal.exchange_for_symbol(sym) is None, sym


def test_unknown_symbol_has_no_silent_twse_fallback():
    assert cal.exchange_for_symbol("NOPE") is None
    assert ST.venue_for_symbol("NOPE") is None
    with pytest.raises(cal.UnknownVenueError):
        cal.trading_date_of("2026-09-18T00:30:00Z", "NQ=F")
    with pytest.raises(cal.UnknownVenueError):
        cal.exchange_timezone("TX")


def test_unknown_venue_session_is_unknown():
    ctx = ST.resolve_venue_session("NOT_A_VENUE", datetime(2026, 9, 24, 3, 0, tzinfo=timezone.utc))
    assert ctx.session_status == "UNKNOWN"
    assert ctx.verification_status == "UNKNOWN"


# ── §53 OSE ──
def test_ose_day_session_open():
    assert _ose(datetime(2026, 9, 24, 11, 0, tzinfo=JST)).session_status == "REGULAR_SESSION"


def test_ose_night_session_open():
    c = _ose(datetime(2026, 9, 24, 20, 0, tzinfo=JST))
    assert c.session_status == "NIGHT_SESSION"
    assert c.trading_date == "2026-09-25"


def test_ose_between_day_and_night_closed():
    assert _ose(datetime(2026, 9, 24, 16, 30, tzinfo=JST)).session_status == "CLOSED"


def test_ose_after_night_close_closed():
    assert _ose(datetime(2026, 9, 24, 6, 30, tzinfo=JST)).session_status == "CLOSED"


def test_ose_night_2000_maps_to_next_trading_date():
    assert _ose(datetime(2026, 9, 24, 20, 0, tzinfo=JST)).trading_date == "2026-09-25"


def test_ose_night_0300_same_trading_date():
    assert _ose(datetime(2026, 9, 25, 3, 0, tzinfo=JST)).trading_date == "2026-09-25"


def test_ose_night_session_not_split_across_calendar_midnight():
    a = _ose(datetime(2026, 9, 24, 20, 0, tzinfo=JST))
    b = _ose(datetime(2026, 9, 25, 3, 0, tzinfo=JST))
    assert a.session_status == b.session_status == "NIGHT_SESSION"
    assert a.trading_date == b.trading_date == "2026-09-25"


def test_ose_holiday_trading_not_equated_to_xtks_cash():
    # 2026-09-22: JPX Holiday Trading (OSE open) while TSE cash (XTKS) is closed
    assert cal.is_ose_derivatives_session("2026-09-22") is True
    assert cal.is_session("^N225", "2026-09-22") is False
    ose = _ose(datetime(2026, 9, 22, 11, 0, tzinfo=JST))
    cash = _xtks(datetime(2026, 9, 22, 11, 0, tzinfo=JST))
    assert ose.session_status == "REGULAR_SESSION"
    assert cash.session_status == "HOLIDAY_CLOSED"


# ── §54 TAIFEX ──
def test_taifex_regular_session():
    assert _taifex(datetime(2026, 9, 24, 11, 0, tzinfo=TPE)).session_status == "REGULAR_SESSION"


def test_taifex_after_hours_session():
    assert _taifex(datetime(2026, 9, 24, 20, 0, tzinfo=TPE)).session_status == "AFTER_HOURS_SESSION"


def test_taifex_after_hours_maps_to_following_regular_session():
    # 2026-09-25 is an XTAI holiday (Mid-Autumn); next verified XTAI session is 2026-09-29
    assert _taifex(datetime(2026, 9, 24, 20, 0, tzinfo=TPE)).trading_date == "2026-09-29"


def test_taifex_after_midnight_keeps_same_assigned_trading_date():
    a = _taifex(datetime(2026, 9, 24, 20, 0, tzinfo=TPE))
    b = _taifex(datetime(2026, 9, 25, 3, 0, tzinfo=TPE))
    assert a.trading_date == b.trading_date == "2026-09-29"


def test_taifex_friday_night_uses_next_verified_regular_session():
    # Fri 2026-10-02 (XTAI session) after-hours -> next verified XTAI session = Mon 2026-10-05
    c = _taifex(datetime(2026, 10, 2, 20, 0, tzinfo=TPE))
    assert c.session_status == "AFTER_HOURS_SESSION"
    assert c.trading_date == "2026-10-05"


def test_taifex_expiring_contract_last_day_closes_1330():
    assert _taifex(datetime(2026, 9, 24, 13, 30, tzinfo=TPE), is_expiring_contract=True).session_status == "REGULAR_SESSION"
    assert _taifex(datetime(2026, 9, 24, 13, 40, tzinfo=TPE), is_expiring_contract=True).session_status == "CLOSED"


def test_taifex_expiring_contract_has_no_after_hours():
    c = _taifex(datetime(2026, 9, 24, 20, 0, tzinfo=TPE), is_expiring_contract=True)
    assert c.session_status == "CLOSED"
    assert c.expiry_exception_status == "APPLIED"


def test_taifex_unknown_expiry_metadata_is_not_fabricated():
    c = _taifex(datetime(2026, 9, 24, 11, 0, tzinfo=TPE))
    assert c.expiry_exception_status == "UNKNOWN"


# ── §55 CME ──
def test_cme_nq_regular_globex_session():
    assert _cme(datetime(2026, 9, 24, 12, 0, tzinfo=CT)).session_status == "REGULAR_SESSION"


def test_cme_nq_daily_maintenance_closed():
    assert _cme(datetime(2026, 9, 24, 16, 30, tzinfo=CT)).session_status == "MAINTENANCE"


def test_cme_nq_weekend_closed():
    assert _cme(datetime(2026, 9, 26, 12, 0, tzinfo=CT)).session_status == "CLOSED"  # Saturday


def test_cme_holiday_unverified_is_not_claimed_exchange_verified():
    c = _cme(datetime(2026, 9, 24, 12, 0, tzinfo=CT))
    assert c.holiday_status == "UNKNOWN"
    assert c.verification_status != "EXCHANGE_CALENDAR_VERIFIED"


# ── §56 cash ──
def test_xtks_cash_not_open_entire_calendar_day():
    assert _xtks(datetime(2026, 9, 24, 11, 0, tzinfo=JST)).session_status == "REGULAR_SESSION"
    assert _xtks(datetime(2026, 9, 24, 20, 0, tzinfo=JST)).session_status == "CLOSED"


def test_xtks_2000_jst_closed():
    assert _xtks(datetime(2026, 9, 24, 20, 0, tzinfo=JST)).market_open is False


def test_xtks_0300_jst_closed():
    assert _xtks(datetime(2026, 9, 25, 3, 0, tzinfo=JST)).market_open is False


def test_xtai_cash_closed_during_taifex_after_hours():
    ts = datetime(2026, 9, 24, 20, 0, tzinfo=TPE)
    assert _xtai(ts).session_status == "CLOSED"
    assert _taifex(ts).session_status == "AFTER_HOURS_SESSION"
