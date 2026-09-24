"""Phase V2-B — daily gap / overnight decomposition + session truth tests."""
from __future__ import annotations

import sys

import pytest

sys.path.insert(0, "src")

from market_ai_hub.research.v2 import gap_session as g
from market_ai_hub.research.v2 import asof


def _rec(**kw):
    base = dict(instrument="JNU", target_family="OSAKA_MICRO", calendar_id="OSE_DERIVATIVES",
                trading_date="2026-09-18", previous_close=100.0, open_=102.0, close=101.0,
                previous_trading_date="2026-09-17", instrument_role="DIRECT")
    base.update(kw)
    return g.build_gap_session_record(**base)


# ── §5 identity ──
def test_gap_return_identity():
    d = g.decompose(100.0, 102.0, 101.0)
    assert d.identity_ok is True
    assert abs((1 + d.overnight_gap_return) * (1 + d.session_return) - (1 + d.close_to_close_return)) < 1e-6


# ── §7 taxonomy ──
def test_gap_up_continuation():
    r = _rec(previous_close=100.0, open_=102.0, close=104.0)
    assert r.gap_classification == "GAP_UP"
    assert r.session_outcome == "GAP_UP_CONTINUATION"


def test_gap_up_fade():
    r = _rec(previous_close=100.0, open_=102.0, close=101.0)
    assert r.gap_classification == "GAP_UP"
    assert r.session_outcome == "GAP_UP_FADE"


def test_gap_down_continuation():
    r = _rec(previous_close=100.0, open_=98.0, close=96.0)
    assert r.gap_classification == "GAP_DOWN"
    assert r.session_outcome == "GAP_DOWN_CONTINUATION"


def test_gap_down_recovery():
    r = _rec(previous_close=100.0, open_=98.0, close=99.0)
    assert r.gap_classification == "GAP_DOWN"
    assert r.session_outcome == "GAP_DOWN_RECOVERY"


def test_flat_gap():
    r = _rec(previous_close=100.0, open_=100.05, close=100.2)
    assert r.gap_classification == "FLAT_GAP"


# ── §18/§19 fail closed ──
def test_missing_open_no_gap():
    r = _rec(open_=None)
    assert r.missing_open is True
    assert r.gap_interpretation == "MISSING_OPEN"
    assert r.overnight_gap_return is None


def test_missing_previous_close_no_gap():
    r = _rec(previous_close=None)
    assert r.missing_previous_close is True
    assert r.gap_interpretation == "MISSING_PREVIOUS_CLOSE"
    assert r.overnight_gap_return is None


# ── §17 calendar-aware previous session ──
def test_previous_trading_session_not_calendar_minus_one():
    # 2026-09-22 (Tue) previous session is 2026-09-18 (Fri) — NOT 09-21 (Mon holiday)
    prev = g.previous_trading_session("2026-09-22", "XTKS")
    assert prev == "2026-09-18"


# ── §10/§11/§13 target isolation ──
def test_osaka_direct_proxy_isolated():
    direct = _rec(instrument="JNU", target_family="OSAKA_MICRO", calendar_id="OSE_DERIVATIVES",
                  instrument_role="DIRECT")
    proxy = _rec(instrument="^N225", target_family="OSAKA_MICRO", calendar_id="XTKS",
                 instrument_role="PROXY")
    assert direct.calendar_id == "OSE_DERIVATIVES"
    assert proxy.calendar_id == "XTKS"
    assert direct.instrument != proxy.instrument


def test_taiwan_osaka_isolated():
    tw = _rec(instrument="3706.TW", target_family="TAIWAN_STOCK", calendar_id="XTAI",
              instrument_role="DIRECT")
    jp = _rec(instrument="JNU", target_family="OSAKA_MICRO", calendar_id="OSE_DERIVATIVES",
              instrument_role="DIRECT")
    assert tw.target_family != jp.target_family
    assert tw.calendar_id == "XTAI"
    assert jp.calendar_id == "OSE_DERIVATIVES"


def test_taiex_not_executable():
    r = _rec(instrument="TAIEX", target_family="TAIWAN_INDEX", calendar_id="XTAI",
             instrument_role="DIRECT")
    assert r.target_family == "TAIWAN_INDEX"
    # record carries no execution instruction (no such field)


# ── §21 roll boundary ──
def test_roll_boundary_not_real_gap():
    r = _rec(roll_status="ROLL_BOUNDARY")
    assert r.gap_interpretation == "NOT_COMPARABLE"
    assert r.overnight_gap_return is None


# ── §12 holiday semantics ──
def test_holiday_ose_cash_closed_semantics():
    r = _rec(holiday_status="HOLIDAY_TRADING", cash_reference_status="CLOSED_MARKET_REFERENCE",
             basis_comparability="NOT_COMPARABLE")
    assert r.holiday_status == "HOLIDAY_TRADING"
    assert r.cash_reference_status == "CLOSED_MARKET_REFERENCE"
    assert r.basis_comparability == "NOT_COMPARABLE"


# ── §22 daily OHLC cannot claim path order ──
def test_daily_ohlc_cannot_claim_path_order():
    # record exposes OHLC location but NO touch/first-passage/acceptance sequence fields
    r = _rec(high=105.0, low=99.0, close=101.0)
    assert r.open_to_high is not None
    assert not hasattr(r, "first_passage")
    assert not hasattr(r, "touch_sequence")
    assert not hasattr(r, "acceptance")


# ── §16 legacy data not asof verified ──
def test_legacy_data_not_asof_verified():
    r = _rec(asof_status="LEGACY_TEMPORAL_UNVERIFIED")
    assert r.temporal_evidence_status == "LEGACY_TEMPORAL_UNVERIFIED"
    assert r.public_evidence_status == "NOT_VALIDATED"


# ── §24/§25/§26 no public probability / no strategy ──
def test_no_public_probability():
    recs = [_rec() for _ in range(25)]
    s = g.summarize_gaps(recs, min_sample=20)
    assert s.public_probability_status == "NOT_PUBLIC_PROBABILITY"
    assert s.calibration_status == "NOT_CALIBRATED"
    assert s.evidence_class == "DESCRIPTIVE_HISTORICAL_RATE"
    cr = g.conditional_rate(recs, gap="GAP_UP", outcome="GAP_UP_FADE")
    assert cr["public_probability_status"] == "NOT_PUBLIC_PROBABILITY"


def test_no_trade_instruction():
    r = _rec()
    assert not hasattr(r, "trade_instruction")
    assert not hasattr(r, "signal")
    assert not hasattr(r, "short_signal")
    assert not hasattr(r, "long_signal")


def test_insufficient_sample():
    recs = [_rec() for _ in range(3)]
    s = g.summarize_gaps(recs, min_sample=20)
    assert s.sample_sufficiency == "INSUFFICIENT_SAMPLE"


# ── V2-A regression: Defect A ──
def test_market_context_quality_missing_count_truthful():
    q = asof.market_context_quality({}, expected_sources=["NQ", "SOX"])
    assert q.missing_source_count == 2
    assert q.source_coverage == {"NQ": "MISSING", "SOX": "MISSING"}
    assert q.overall_status != "GOOD"


# ── V2-A regression: Defect B ──
def test_forward_fill_flag_truthful():
    from datetime import datetime, timezone
    def dt(d, h, m):
        return datetime(2026, 9, d, h, m, tzinfo=timezone.utc)
    obs = [asof.AsOfObservation(instrument="JNU", field="close", value=100.0,
                                observed_at=dt(1, 9, 30), event_timestamp=dt(1, 9, 0))]
    rows = asof.point_in_time_join([dt(1, 10, 0), dt(2, 10, 0)], obs, "close", "JNU",
                                   allow_forward_fill=True, max_age_seconds=3600)
    assert rows[0].forward_filled is False  # genuine match
    assert rows[1].forward_filled is True   # carry-forward
    assert rows[1].value == 100.0           # preserved value
    assert rows[1].source_observed_at is not None  # original observed_at preserved


def test_version_2b():
    assert g.V2_GAP_SESSION_SCHEMA_VERSION == "2B.1"
    assert asof.V2_ASOF_SCHEMA_VERSION == "2A.2"  # V2-A.2 session/factor foundation