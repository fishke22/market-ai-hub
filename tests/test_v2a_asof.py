"""Phase V2-A — as-of / timestamp / data-truth foundation tests."""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, "src")

from market_ai_hub.research.v2 import asof


def _dt(y, m, d, hh=0, mm=0, tz="UTC"):
    if tz == "UTC":
        return datetime(y, m, d, hh, mm, tzinfo=timezone.utc)
    from zoneinfo import ZoneInfo
    return datetime(y, m, d, hh, mm, tzinfo=ZoneInfo(tz))


def _obs(value, event, observed, field="close", instrument="JNU", frequency="DAILY"):
    return asof.AsOfObservation(
        instrument=instrument, target_family="OSAKA_MICRO", provider="jpx", field=field,
        value=value, event_timestamp=event, observed_at=observed, ingested_at=observed,
        source_timestamp=event, frequency=frequency, calendar_id="OSE_DERIVATIVES",
        availability_status="AVAILABLE")


# ── §47: future event ──
def test_future_event_rejected():
    obs = _obs(40000.0, event=_dt(2026, 9, 22, 10, 5), observed=_dt(2026, 9, 22, 10, 5))
    cutoff = _dt(2026, 9, 22, 10, 0)
    res = asof.get_asof([obs], "JNU", cutoff=cutoff)
    assert res == []


# ── §48: early event / late observation ──
def test_early_event_late_observation_rejected():
    obs = _obs(40000.0, event=_dt(2026, 9, 22, 9, 50), observed=_dt(2026, 9, 22, 10, 5))
    cutoff = _dt(2026, 9, 22, 10, 0)
    assert asof.reject_future_information(obs, cutoff) == ["FAIL_OBSERVED_AFTER_CUTOFF"]
    assert asof.get_asof([obs], "JNU", cutoff=cutoff) == []


# ── §49: valid as-of ──
def test_valid_asof_returned():
    obs = _obs(40000.0, event=_dt(2026, 9, 22, 9, 50), observed=_dt(2026, 9, 22, 9, 51))
    cutoff = _dt(2026, 9, 22, 10, 0)
    res = asof.get_asof([obs], "JNU", cutoff=cutoff)
    assert len(res) == 1
    assert res[0].value == 40000.0


# ── §50: macro release after forecast origin ──
def test_macro_release_after_origin_blocked():
    rel = asof.ReleaseTimeContext(release_timestamp=_dt(2026, 9, 22, 8, 35),
                                  revision_status="VINTAGE_NOT_AVAILABLE")
    cutoff = _dt(2026, 9, 22, 8, 30)  # release after cutoff
    ok, reason = asof.macro_asof_safe(rel, cutoff)
    assert ok is False
    assert reason == "FAIL_RELEASE_AFTER_CUTOFF"


def test_macro_release_before_cutoff_revision_risk():
    rel = asof.ReleaseTimeContext(release_timestamp=_dt(2026, 9, 22, 8, 25),
                                  revision_status="VINTAGE_NOT_AVAILABLE")
    cutoff = _dt(2026, 9, 22, 8, 30)
    ok, reason = asof.macro_asof_safe(rel, cutoff)
    assert ok is True
    assert reason == "REVISION_RISK_PRESENT"


# ── §51: stale reference not fresh ──
def test_previous_session_close_is_reference_not_live():
    # previous-session SOX close in a new Asian session
    close = _dt(2026, 9, 21, 20, 0)  # prior US close
    now = _dt(2026, 9, 22, 1, 0)      # Asian overnight
    st = asof.staleness_for(close, now=now, soft_seconds=3600, hard_seconds=86400, market_open=False)
    assert st == "CLOSED_MARKET_REFERENCE"
    role = asof.context_role_for(st, market_open=False)
    assert role == "PREVIOUS_SESSION_REFERENCE"
    assert role != "LIVE"


# ── §52: OSE holiday trading ──
def test_ose_holiday_trading_representable():
    sc = asof.ose_holiday_session_context(trading_date="2026-09-22",
                                          cash_open=False, derivatives_open=True, is_holiday=True)
    assert sc.cash_market_open is False
    assert sc.derivatives_market_open is True
    assert sc.is_holiday_trading is True
    assert sc.session_type == "HOLIDAY_DAY"


# ── §53: direct / proxy calendars separated ──
def test_direct_proxy_calendars_separated():
    assert asof.TARGET_SEMANTICS["OSAKA_MICRO"]["calendar"] == "OSE_DERIVATIVES"
    assert asof.TARGET_SEMANTICS["OSAKA_MICRO"]["role"] == "DIRECT"
    assert asof.TARGET_SEMANTICS["^N225"]["calendar"] == "XTKS"
    assert asof.TARGET_SEMANTICS["^N225"]["role"] == "PROXY"


# ── §54: overnight trading date ──
def test_overnight_session_type_and_timezone():
    sc = asof.MarketSessionContext(market="OSE_DERIVATIVES", calendar_id="OSE_DERIVATIVES",
                                   trading_date="2026-09-22", session_type="OVERNIGHT",
                                   derivatives_market_open=True)
    assert sc.session_type == "OVERNIGHT"
    # canonical tz for OSE is Asia/Tokyo
    assert asof.EXCHANGE_TIMEZONES["OSE_DERIVATIVES"] == "Asia/Tokyo"


# ── §55: no naive datetime ──
def test_naive_datetime_rejected():
    with pytest.raises(ValueError):
        asof.TemporalContext(event_timestamp=datetime(2026, 9, 22, 10, 0))


def test_naive_datetime_with_tz_context_ok():
    tc = asof.TemporalContext(event_timestamp=_dt(2026, 9, 22, 10, 0))
    assert tc.event_timestamp.tzinfo is not None


def test_ensure_utc_aware_requires_tz_for_naive():
    with pytest.raises(ValueError):
        asof.ensure_utc_aware(datetime(2026, 9, 22, 10, 0))


# ── §56: snapshot lineage stable identity ──
def test_snapshot_identity_stable_and_content_sensitive():
    s1 = asof.DataSnapshot(provider="yfinance", instrument="^N225", schema_version="v1",
                           content_hash="abc", retrieved_at=_dt(2026, 9, 22, 1, 0))
    s2 = asof.DataSnapshot(provider="yfinance", instrument="^N225", schema_version="v1",
                           content_hash="abc", retrieved_at=_dt(2026, 9, 22, 1, 0))
    s3 = asof.DataSnapshot(provider="yfinance", instrument="^N225", schema_version="v1",
                           content_hash="def", retrieved_at=_dt(2026, 9, 22, 1, 0))
    assert s1.identity_key() == s2.identity_key()
    assert s1.identity_key() != s3.identity_key()


def test_snapshot_default_immutability_is_honest():
    s = asof.DataSnapshot(provider="yfinance", instrument="^N225")
    assert s.immutability == "MUTABLE_CACHE"  # not falsely IMMUTABLE


# ── §57: capability fail closed ──
def test_capability_fail_closed_1m():
    ok, reason = asof.supports_capability("OSAKA_MICRO", "1M")
    assert ok is False
    assert reason == "MISSING_DATA_CAPABILITY"
    with pytest.raises(asof.MissingDataCapabilityError):
        asof.require_capability("OSAKA_MICRO", "1M")


def test_capability_daily_true():
    ok, _ = asof.supports_capability("OSAKA_MICRO", "DAILY")
    assert ok is True


def test_capability_tick_l1_l2_all_false():
    for cap in ("TICK", "L1", "L2", "ORDER_EVENT"):
        ok, _ = asof.supports_capability("OSAKA_MICRO", cap)
        assert ok is False
        ok2, _ = asof.supports_capability("TAIWAN_STOCK", cap)
        assert ok2 is False


def test_taiwan_1m_not_supported():
    ok, reason = asof.supports_capability("TAIWAN_STOCK", "1M")
    assert ok is False
    assert reason == "MISSING_DATA_CAPABILITY"


# ── §58: no secret in logs / snapshots ──
def test_snapshot_and_audit_never_hold_secret_material():
    s = asof.DataSnapshot(provider="fred", instrument="MACRO", content_hash="h")
    blob = str(s.model_dump())
    for secret in ("FRED_API_KEY", "FINMIND_API_TOKEN", "yuanta_password", "WinCred"):
        assert secret not in blob
    tc = asof.TemporalContext(forecast_origin=_dt(2026, 9, 22, 10, 0))
    assert "FRED_API_KEY" not in str(tc.model_dump())


# ── temporal ordering invariant ──
def test_cutoff_after_origin_rejected():
    tc = asof.TemporalContext(
        feature_cutoff_timestamp=_dt(2026, 9, 22, 10, 0),
        forecast_origin=_dt(2026, 9, 22, 9, 0))
    assert "CUTOFF_AFTER_ORIGIN" in tc.validate_ordering()


def test_temporal_ordering_valid():
    tc = asof.TemporalContext(
        event_timestamp=_dt(2026, 9, 22, 8, 0),
        observed_at=_dt(2026, 9, 22, 8, 5),
        feature_cutoff_timestamp=_dt(2026, 9, 22, 8, 30),
        forecast_origin=_dt(2026, 9, 22, 8, 35))
    assert tc.validate_ordering() == []


# ── point-in-time join ──
def test_point_in_time_join_no_forward_fill():
    obs = [
        _obs(100.0, event=_dt(2026, 9, 1, 0), observed=_dt(2026, 9, 1, 9, 30)),
        _obs(101.0, event=_dt(2026, 9, 2, 0), observed=_dt(2026, 9, 2, 9, 30)),
    ]
    cutoffs = [_dt(2026, 9, 1, 12, 0), _dt(2026, 9, 2, 12, 0)]
    rows = asof.point_in_time_join(cutoffs, obs, "close", "JNU", allow_forward_fill=False)
    assert [r.value for r in rows] == [100.0, 101.0]


def test_point_in_time_join_future_observation_excluded():
    obs = [
        _obs(100.0, event=_dt(2026, 9, 1, 0), observed=_dt(2026, 9, 1, 9, 30)),
        _obs(999.0, event=_dt(2026, 9, 2, 0), observed=_dt(2026, 9, 2, 12, 0)),  # observed after cutoff
    ]
    cutoffs = [_dt(2026, 9, 2, 11, 0)]  # 999 not yet observed at cutoff
    rows = asof.point_in_time_join(cutoffs, obs, "close", "JNU", allow_forward_fill=False)
    # only 100 available (999 observed 12:00 > 11:00 cutoff)
    assert rows[0].value == 100.0


# ── no-zero-fill / unavailable ──
def test_unavailable_observation_no_zero_fill():
    u = asof.unavailable_observation("SOX", instrument="SOX", provider="none")
    assert u.value is None
    assert u.availability_status == "NOT_AVAILABLE"
    assert u.is_available() is False


# ── market context quality ──
def test_market_context_quality_degrades_on_stale():
    fresh = _obs(1.0, event=_dt(2026, 9, 22, 8, 0), observed=_dt(2026, 9, 22, 8, 1), field="a")
    stale = _obs(2.0, event=_dt(2026, 9, 20, 8, 0), observed=_dt(2026, 9, 20, 8, 1), field="b")
    q = asof.market_context_quality({"FRESH": [fresh], "STALE": [stale]},
                                    cutoff=_dt(2026, 9, 22, 8, 5))
    assert q.overall_status in ("DEGRADED", "CRITICAL")


def test_healthcheck_display_not_required():
    # V2-A does not add public probability / trade action; only capability status surface exists
    assert asof.V2_ASOF_SCHEMA_VERSION == "2A.2"


# ── §29/§30: legacy feature-store bridge ──
def test_feature_store_bridge_readonly_and_safe():
    rows = asof.read_feature_store_asof()  # data root is temp in tests → returns list, no crash
    assert isinstance(rows, list)


def test_legacy_observation_tagged_unverified():
    # synthetic legacy row (constructed, not from real DB)
    from datetime import timezone as _tz
    obs = asof.AsOfObservation(
        instrument="^N225", provider="panel", field="close", value=45303.0,
        event_timestamp=datetime(2025, 9, 17, 0, 0, tzinfo=_tz.utc),
        observed_at=datetime(2025, 9, 17, 0, 0, tzinfo=_tz.utc),
        provenance={"legacy_status": asof.LEGACY_TEMPORAL_UNVERIFIED})
    assert obs.provenance["legacy_status"] == "LEGACY_TEMPORAL_UNVERIFIED"
    assert obs.provenance["legacy_status"] != "ASOF_VERIFIED"