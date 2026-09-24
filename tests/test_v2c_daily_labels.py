"""Phase V2-C — daily multi-target label engine tests."""
from __future__ import annotations

import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, "src")

from market_ai_hub.research.v2 import labels as L


def _dt(d, h=0, m=0):
    return datetime(2026, 9, d, h, m, tzinfo=timezone.utc)


def _policy(**kw):
    base = dict(acceptance_consecutive_closes=2)
    base.update(kw)
    return L.DailyLabelPolicy(**base)


def _request(**kw):
    base = dict(
        instrument="JNU", target_family="OSAKA_MICRO", instrument_role="DIRECT",
        calendar_id="OSE_DERIVATIVES", feature_cutoff_timestamp=_dt(18, 8, 0),
        forecast_origin=_dt(18, 8, 0), origin_session_date="2026-09-18",
        horizon_sessions=3, previous_close=100.0,
        previous_close_available_at=_dt(18, 7, 0),
        previous_close_provenance="VERIFIED_INPUT")
    base.update(kw)
    return L.DailyLabelRequest(**base)


def _bar(trading_date, open_, high, low, close, day=18, **kw):
    base = dict(
        instrument="JNU", target_family="OSAKA_MICRO", instrument_role="DIRECT",
        calendar_id="OSE_DERIVATIVES", trading_date=trading_date,
        session_open_timestamp=_dt(day, 0, 30), open=open_, high=high, low=low, close=close,
        roll_status="NONE", series_semantics="CONTRACT")
    base.update(kw)
    return L.DailyOutcomeBar(**base)


def _up_barrier(level=105.0, **kw):
    base = dict(barrier_id="B1", level=level, direction="UP",
                barrier_source="research", barrier_available_at=_dt(18, 7, 0))
    base.update(kw)
    return L.BarrierSpec(**base)


def _run(request, barrier, bars, **kw):
    # synthetic trusted fixture default: window = bars' dates, trusted calendar + prev close
    if "expected_sessions" not in kw:
        kw["expected_sessions"] = [b.trading_date for b in bars]
    if "calendar_provenance" not in kw:
        kw["calendar_provenance"] = "VERIFIED_INPUT"
    return L.build_daily_barrier_labels(request, barrier, bars, _policy(), **kw)


# ── normal cases ──
def test_up_touch_true():
    r = _run(_request(horizon_sessions=1), _up_barrier(105.0),
             [_bar("2026-09-21", 102, 106, 101, 104, day=21)])
    assert r.touch.value is True
    assert r.touch.status == "OBSERVED_TRUE"
    assert r.touch.first_session_date == "2026-09-21"


def test_down_touch_true():
    r = _run(_request(horizon_sessions=1),
             L.BarrierSpec(barrier_id="B1", level=95.0, direction="DOWN",
                           barrier_source="s", barrier_available_at=_dt(18, 7, 0)),
             [_bar("2026-09-21", 98, 99, 94, 97, day=21)])
    assert r.touch.value is True


def test_up_break_true():
    r = _run(_request(horizon_sessions=1), _up_barrier(105.0),
             [_bar("2026-09-21", 102, 107, 101, 106, day=21)])
    assert r.break_.value is True
    assert r.break_.first_session_date == "2026-09-21"


def test_down_break_true():
    r = _run(_request(horizon_sessions=1),
             L.BarrierSpec(barrier_id="B1", level=95.0, direction="DOWN",
                           barrier_source="s", barrier_available_at=_dt(18, 7, 0)),
             [_bar("2026-09-21", 98, 99, 96, 94, day=21)])
    assert r.break_.value is True


def test_close_equal_barrier_not_break():
    r = _run(_request(horizon_sessions=1), _up_barrier(105.0),
             [_bar("2026-09-21", 102, 106, 101, 105.0, day=21)],
             expected_sessions=["2026-09-21"])
    assert r.break_.value is False
    assert r.break_.status == "OBSERVED_FALSE"


def test_acceptance_two_consecutive_true():
    bars = [_bar("2026-09-21", 102, 107, 101, 106, day=21),
            _bar("2026-09-22", 106, 108, 105, 107, day=22)]
    r = _run(_request(horizon_sessions=2), _up_barrier(105.0), bars)
    assert r.acceptance.value is True
    assert r.acceptance.first_session_date == "2026-09-22"


def test_acceptance_one_close_only_false():
    bars = [_bar("2026-09-21", 102, 107, 101, 106, day=21),
            _bar("2026-09-22", 106, 107, 104, 104, day=22)]
    r = _run(_request(horizon_sessions=2), _up_barrier(105.0), bars,
             expected_sessions=["2026-09-21", "2026-09-22"])
    assert r.acceptance.value is False
    assert r.acceptance.status == "OBSERVED_FALSE"


def test_acceptance_break_then_revert_false():
    bars = [_bar("2026-09-21", 102, 107, 101, 106, day=21),
            _bar("2026-09-22", 106, 107, 104, 104, day=22)]
    r = _run(_request(horizon_sessions=2), _up_barrier(105.0), bars,
             expected_sessions=["2026-09-21", "2026-09-22"])
    assert r.break_.value is True
    assert r.acceptance.value is False


# ── maturity ──
def test_unmature_no_positive():
    r = _run(_request(horizon_sessions=3), _up_barrier(105.0),
             [_bar("2026-09-21", 102, 104, 101, 103, day=21)],
             expected_sessions=["2026-09-21"])
    assert r.touch.value is None
    assert r.touch.status == "UNMATURED"


def test_touch_early_true_despite_unmature():
    r = _run(_request(horizon_sessions=3), _up_barrier(105.0),
             [_bar("2026-09-21", 102, 106, 101, 103, day=21)])
    assert r.touch.value is True


def test_acceptance_early_true_despite_longer_horizon():
    bars = [_bar("2026-09-21", 102, 107, 101, 106, day=21),
            _bar("2026-09-22", 106, 108, 105, 107, day=22)]
    r = _run(_request(horizon_sessions=5), _up_barrier(105.0), bars)
    assert r.acceptance.value is True


# ── gap ambiguity ──
def test_gap_cross_touch_ambiguous_break_true():
    # prev close 100 < L 105, next open 106 > L, low 105.5 > L → gap over
    bars = [_bar("2026-09-21", 106, 108, 105.5, 107, day=21)]
    r = _run(_request(horizon_sessions=1, previous_close=100.0), _up_barrier(105.0), bars)
    assert r.touch.value is None
    assert r.touch.status == "AMBIGUOUS_GAP_CROSS"
    assert r.break_.value is True


def test_gap_over_then_later_touch_true():
    bars = [_bar("2026-09-21", 106, 108, 105.5, 107, day=21),
            _bar("2026-09-22", 107, 109, 104.0, 108, day=22)]
    r = _run(_request(horizon_sessions=2, previous_close=100.0), _up_barrier(105.0), bars)
    assert r.touch.value is True
    assert r.touch.first_session_date == "2026-09-22"


# ── no path fabrication ──
def test_same_bar_touch_break_no_first_passage():
    r = _run(_request(horizon_sessions=1), _up_barrier(105.0),
             [_bar("2026-09-21", 102, 106, 101, 106, day=21)])
    assert r.touch.value is True and r.break_.value is True
    assert r.path_order_status == "UNKNOWN_WITHIN_DAILY_BAR"
    assert not hasattr(r.touch, "first_passage_timestamp")


def test_multi_barrier_same_bar_order_unknown():
    r = _run(_request(horizon_sessions=1), _up_barrier(103.0),
             [_bar("2026-09-21", 102, 106, 100, 106, day=21)])
    assert r.touch.value is True
    assert r.path_order_status == "UNKNOWN_WITHIN_DAILY_BAR"


# ── leakage ──
def test_barrier_available_after_cutoff_fail():
    req = _request(feature_cutoff_timestamp=_dt(18, 8, 0))
    barrier = _up_barrier(105.0, barrier_available_at=_dt(18, 9, 0))
    r = _run(req, barrier, [_bar("2026-09-21", 102, 106, 101, 104, day=21)])
    assert r.series_block == L.BLOCKED_BARRIER_PROVENANCE
    assert r.touch.value is None and r.break_.value is None


def test_feature_cutoff_after_origin_fail():
    req = _request(feature_cutoff_timestamp=_dt(18, 9, 0), forecast_origin=_dt(18, 8, 0))
    r = _run(req, _up_barrier(105.0), [_bar("2026-09-21", 102, 106, 101, 104, day=21)])
    assert r.series_block == L.BLOCKED_TEMPORAL_CONTRACT


def test_mid_session_bar_excluded():
    # forecast_origin 09:00; bar opened 08:30 (before origin) → mid-session, excluded (never labels)
    req = _request(forecast_origin=_dt(21, 9, 0), origin_session_date="2026-09-21", horizon_sessions=1)
    bars = [_bar("2026-09-21", 102, 106, 101, 104, day=21, session_open_timestamp=_dt(21, 8, 30))]
    r = _run(req, _up_barrier(105.0), bars)
    assert r.touch.value is None
    assert r.break_.value is None
    assert r.acceptance.value is None


def test_naive_timestamp_reject():
    with pytest.raises(ValueError):
        L.DailyLabelRequest(instrument="JNU", feature_cutoff_timestamp=datetime(2026, 9, 18, 8, 0),
                            forecast_origin=_dt(18, 8, 0))


# ── data quality ──
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf"), 0.0, -5.0])
def test_invalid_price_rejected(bad):
    bar = _bar("2026-09-21", 102, 106, bad, 104, day=21)
    reasons = L.validate_daily_bar(bar)
    assert any("INVALID_LOW" in r for r in reasons)


def test_low_gt_high_invalid():
    bar = _bar("2026-09-21", 102, 101, 103, 102, day=21)
    assert "LOW_GT_HIGH" in L.validate_daily_bar(bar)


def test_open_outside_range_invalid():
    bar = _bar("2026-09-21", 110, 106, 101, 104, day=21)
    assert "OPEN_OUTSIDE_RANGE" in L.validate_daily_bar(bar)


def test_close_outside_range_invalid():
    bar = _bar("2026-09-21", 102, 106, 101, 108, day=21)
    assert "CLOSE_OUTSIDE_RANGE" in L.validate_daily_bar(bar)


def test_missing_high_low_touch_unavailable():
    bar = _bar("2026-09-21", 102, None, None, 104, day=21)
    r = _run(_request(horizon_sessions=1), _up_barrier(105.0), [bar])
    assert r.touch.value is None
    assert r.touch.status in ("INVALID_OHLC",)


def test_missing_close_break_unavailable():
    bar = _bar("2026-09-21", 102, 106, 101, None, day=21)
    r = _run(_request(horizon_sessions=1), _up_barrier(105.0), [bar])
    assert r.break_.value is None


# ── identity isolation ──
def test_osaka_direct_proxy_mixed_reject():
    req = _request(instrument="JNU", target_family="OSAKA_MICRO", instrument_role="DIRECT")
    bars = [_bar("2026-09-21", 102, 106, 101, 104, day=21, instrument="^N225", instrument_role="PROXY")]
    r = _run(req, _up_barrier(105.0), bars)
    assert r.series_block == L.BLOCKED_IDENTITY_MISMATCH


def test_osaka_taiwan_mixed_reject():
    req = _request(instrument="JNU", target_family="OSAKA_MICRO")
    bars = [_bar("2026-09-21", 102, 106, 101, 104, day=21, target_family="TAIWAN_STOCK",
                 instrument="3706.TW", calendar_id="XTAI")]
    r = _run(req, _up_barrier(105.0), bars)
    assert r.series_block == L.BLOCKED_IDENTITY_MISMATCH


def test_different_tw_symbols_mixed_reject():
    req = _request(instrument="2330.TW", target_family="TAIWAN_STOCK", calendar_id="XTAI",
                   instrument_role="DIRECT")
    bars = [_bar("2026-09-21", 102, 106, 101, 104, day=21, instrument="3706.TW",
                 target_family="TAIWAN_STOCK", calendar_id="XTAI", roll_status="NOT_APPLICABLE",
                 series_semantics="CASH")]
    r = _run(req, _up_barrier(105.0), bars)
    assert r.series_block == L.BLOCKED_IDENTITY_MISMATCH


def test_calendar_mismatch_reject():
    req = _request(calendar_id="OSE_DERIVATIVES")
    bars = [_bar("2026-09-21", 102, 106, 101, 104, day=21, calendar_id="XTKS")]
    r = _run(req, _up_barrier(105.0), bars)
    assert r.series_block == L.BLOCKED_IDENTITY_MISMATCH


def test_instrument_role_mismatch_reject():
    req = _request(instrument_role="DIRECT")
    bars = [_bar("2026-09-21", 102, 106, 101, 104, day=21, instrument_role="PROXY")]
    r = _run(req, _up_barrier(105.0), bars)
    assert r.series_block == L.BLOCKED_IDENTITY_MISMATCH


# ── roll ──
def test_roll_boundary_blocked():
    bars = [_bar("2026-09-21", 102, 106, 101, 104, day=21, roll_status="ROLL_BOUNDARY")]
    r = _run(_request(horizon_sessions=1), _up_barrier(105.0), bars)
    assert r.series_block == L.BLOCKED_ROLL_PROVENANCE


def test_roll_unknown_blocked_not_none():
    bars = [_bar("2026-09-21", 102, 106, 101, 104, day=21, roll_status="UNKNOWN")]
    r = _run(_request(horizon_sessions=1), _up_barrier(105.0), bars)
    assert r.series_block == L.BLOCKED_ROLL_PROVENANCE


def test_roll_unknown_not_silently_none():
    # dataclass default roll_status is UNKNOWN (not NONE) — P5: don't default futures roll to NONE
    bar = L.DailyOutcomeBar()
    assert bar.roll_status == "UNKNOWN"
    assert bar.roll_status != "NONE"


# ── expected sessions / calendar ──
def test_weekend_not_counted():
    # horizon 3 trading sessions, but bars skip a weekend via trading_date ordering handled by caller
    bars = [_bar("2026-09-21", 102, 106, 101, 104, day=21),
            _bar("2026-09-22", 103, 105, 102, 104, day=22),
            _bar("2026-09-24", 104, 106, 103, 105, day=24)]
    r = _run(_request(horizon_sessions=3), _up_barrier(105.0), bars,
             expected_sessions=["2026-09-21", "2026-09-22", "2026-09-24"])
    assert r.break_.value is False  # no close beyond 105


def test_missing_expected_session_negative_unavailable():
    bars = [_bar("2026-09-21", 102, 104, 101, 103, day=21)]
    r = _run(_request(horizon_sessions=2), _up_barrier(105.0), bars,
             expected_sessions=["2026-09-21", "2026-09-22"])
    assert r.touch.value is None
    assert r.touch.status == "UNOBSERVABLE_MISSING_DATA"


def test_acceptance_cannot_cross_missing_session():
    bars = [_bar("2026-09-21", 102, 107, 101, 106, day=21)]  # 1 close beyond, then missing 09-22
    r = _run(_request(horizon_sessions=3), _up_barrier(105.0), bars,
             expected_sessions=["2026-09-21", "2026-09-22", "2026-09-23"])
    # missing 09-22 breaks consecutive; acceptance cannot be True
    assert r.acceptance.value is None
    assert r.acceptance.status == "UNOBSERVABLE_MISSING_DATA"


# ── legacy / asof ──
def test_legacy_not_asof_verified():
    bar = _bar("2026-09-21", 102, 106, 101, 104, day=21, asof_status="LEGACY_TEMPORAL_UNVERIFIED")
    r = _run(_request(horizon_sessions=1), _up_barrier(105.0), [bar])
    assert r.asof_status == "LEGACY_TEMPORAL_UNVERIFIED"
    assert r.asof_status != "ASOF_VERIFIED"


# ── public probability / trade signal ──
def test_no_public_probability():
    r = _run(_request(horizon_sessions=1), _up_barrier(105.0),
             [_bar("2026-09-21", 102, 106, 101, 104, day=21)])
    assert r.public_probability_status == "NOT_PUBLIC_PROBABILITY"
    assert r.calibration_status == "NOT_CALIBRATED"
    assert r.validation_status == "HYPOTHESIS_ONLY"


def test_no_trade_signal():
    r = _run(_request(horizon_sessions=1), _up_barrier(105.0),
             [_bar("2026-09-21", 102, 106, 101, 104, day=21)])
    assert not hasattr(r, "trade_signal")
    assert not hasattr(r, "long")
    assert not hasattr(r, "short")
    assert not hasattr(r, "order")


# ── versions ──
def test_versions():
    from market_ai_hub.research.v2.asof import V2_ASOF_SCHEMA_VERSION
    from market_ai_hub.research.v2.gap_session import V2_GAP_SESSION_SCHEMA_VERSION
    from market_ai_hub.research.price_probability_map import PRICE_PROBABILITY_MAP_VERSION
    assert L.V2_DAILY_LABEL_SCHEMA_VERSION == "2C.2"
    assert V2_ASOF_SCHEMA_VERSION == "2A.2"
    assert V2_GAP_SESSION_SCHEMA_VERSION == "2B.1"
    assert PRICE_PROBABILITY_MAP_VERSION == "3A.2.3"


def test_duplicate_trading_session_reject():
    bars = [_bar("2026-09-21", 102, 106, 101, 104, day=21),
            _bar("2026-09-21", 103, 107, 102, 105, day=21)]
    r = _run(_request(horizon_sessions=1), _up_barrier(105.0), bars,
             expected_sessions=["2026-09-21"])
    assert r.series_block == L.BLOCKED_TEMPORAL_CONTRACT


# ── dataset adapter (read-only, truthful field readiness) ──
def test_field_readiness_caret225_close_only():
    from market_ai_hub.research.v2.daily_adapter import local_field_readiness
    r = local_field_readiness("^N225")
    assert r["close"] is True
    assert r["open"] is False
    assert r["high"] is False
    assert r["low"] is False


def test_field_readiness_taiwan_index_no_ohlc():
    from market_ai_hub.research.v2.daily_adapter import local_field_readiness
    r = local_field_readiness("TAIWAN_INDEX")
    assert r["close"] is False
    assert r["open"] is False


def test_field_readiness_osaka_ohlc_but_no_roll():
    from market_ai_hub.research.v2.daily_adapter import local_field_readiness
    r = local_field_readiness("OSAKA_MICRO")
    assert r["open"] is True and r["high"] is True and r["low"] is True and r["close"] is True
    assert r["roll_provenance"] is False


def test_adapter_osaka_no_dataset_in_test_env():
    # conftest redirects data root to temp → no parquet → blocker DATASET_NOT_FOUND (honest)
    from market_ai_hub.research.v2.daily_adapter import osaka_micro_bars
    bars, rd = osaka_micro_bars()
    assert rd.blocker == "DATASET_NOT_FOUND"
    assert bars == []


# ── self-validation correction: roll + calendar + local readiness adversarial ──
def test_osaka_unknown_roll_blocks_single_session_touch():
    bar = _bar("2026-09-21", 102, 106, 101, 104, day=21, roll_status="UNKNOWN")
    r = _run(_request(horizon_sessions=1), _up_barrier(105.0), [bar])
    assert r.series_block == L.BLOCKED_ROLL_PROVENANCE
    assert r.touch.value is None
    assert r.touch.status == L.BLOCKED_ROLL_PROVENANCE


def test_osaka_unknown_roll_blocks_single_session_break():
    bar = _bar("2026-09-21", 102, 107, 101, 106, day=21, roll_status="UNKNOWN")
    r = _run(_request(horizon_sessions=1), _up_barrier(105.0), [bar])
    assert r.series_block == L.BLOCKED_ROLL_PROVENANCE
    assert r.break_.value is None
    assert r.break_.status == L.BLOCKED_ROLL_PROVENANCE


def test_negative_label_not_false_when_calendar_provenance_unknown():
    # trusted session window absent (calendar_provenance=UNKNOWN) → negative cannot be OBSERVED_FALSE
    r = _run(_request(horizon_sessions=1), _up_barrier(105.0),
             [_bar("2026-09-21", 102, 104, 101, 103, day=21)],
             calendar_provenance="UNKNOWN")
    assert r.calendar_provenance == "UNKNOWN"
    assert r.break_.value is None
    assert r.break_.status == "BLOCKED_CALENDAR_PROVENANCE"


def test_positive_label_blocks_without_trusted_session_window():
    # §4: positive events also require trusted session-window provenance
    r = _run(_request(horizon_sessions=1), _up_barrier(105.0),
             [_bar("2026-09-21", 102, 107, 101, 106, day=21)],
             calendar_provenance="UNKNOWN")
    assert r.break_.value is None
    assert r.break_.status == "BLOCKED_CALENDAR_PROVENANCE"


def test_positive_label_succeeds_with_trusted_session_window():
    r = _run(_request(horizon_sessions=1), _up_barrier(105.0),
             [_bar("2026-09-21", 102, 107, 101, 106, day=21)],
             expected_sessions=["2026-09-21"], calendar_provenance="VERIFIED_INPUT")
    assert r.break_.value is True
    assert r.break_.status == "OBSERVED_TRUE"


def test_n225_close_only_blocks_touch_even_if_coarse_registry_says_daily_ohlcv():
    from market_ai_hub.research.v2 import asof
    from market_ai_hub.research.v2.daily_adapter import local_field_readiness
    # coarse registry may say daily/OHLCV, but local field readiness says close-only
    ok, _ = asof.supports_capability("^N225", "DAILY")
    r = local_field_readiness("^N225")
    assert r["close"] is True and r["open"] is False and r["high"] is False and r["low"] is False
    # Touch requires open+high+low → NOT ready
    assert not (r["open"] and r["high"] and r["low"])


def test_taiwan_index_without_local_dataset_not_touch_ready():
    from market_ai_hub.research.v2.daily_adapter import local_field_readiness
    r = local_field_readiness("TAIWAN_INDEX")
    assert r["open"] is False and r["close"] is False
    assert not (r["open"] and r["high"] and r["low"])


def test_legacy_input_not_promoted_to_asof_verified():
    bar = _bar("2026-09-21", 102, 106, 101, 104, day=21, asof_status="LEGACY_TEMPORAL_UNVERIFIED")
    r = _run(_request(horizon_sessions=1), _up_barrier(105.0), [bar],
             expected_sessions=["2026-09-21"])
    assert r.asof_status == "LEGACY_TEMPORAL_UNVERIFIED"
    assert r.asof_status != "ASOF_VERIFIED"


# ── Final closure: session-boundary truth on POSITIVE labels ──
def test_positive_touch_blocks_when_outcome_session_not_proven_after_origin():
    # no session_open_timestamp → cannot prove bar is after forecast_origin → touch NOT True
    bar = _bar("2026-09-21", 102, 106, 101, 104, day=21, session_open_timestamp=None)
    r = _run(_request(horizon_sessions=1), _up_barrier(105.0), [bar],
             expected_sessions=["2026-09-21"])
    assert r.touch.value is None
    assert r.touch.status == L.BLOCKED_TEMPORAL_SESSION_BOUNDARY
    assert r.series_block == L.BLOCKED_TEMPORAL_SESSION_BOUNDARY


def test_positive_break_blocks_when_outcome_session_not_proven_after_origin():
    bar = _bar("2026-09-21", 102, 107, 101, 106, day=21, session_open_timestamp=None)
    r = _run(_request(horizon_sessions=1), _up_barrier(105.0), [bar],
             expected_sessions=["2026-09-21"])
    assert r.break_.value is None
    assert r.break_.status == L.BLOCKED_TEMPORAL_SESSION_BOUNDARY


def test_current_session_full_daily_bar_cannot_label_mid_session_forecast():
    # forecast_origin 09:00; bar opened 08:30 same day → full daily bar must NOT be labeled
    req = _request(forecast_origin=_dt(21, 9, 0), origin_session_date="2026-09-21", horizon_sessions=1)
    bar = _bar("2026-09-21", 102, 106, 101, 104, day=21, session_open_timestamp=_dt(21, 8, 30))
    r = _run(req, _up_barrier(105.0), [bar], expected_sessions=["2026-09-21"])
    assert r.touch.value is None
    assert r.break_.value is None
    assert r.acceptance.value is None


# ── Final closure: calendar provenance trust ──
def test_expected_sessions_without_trusted_calendar_provenance_still_blocks_negative():
    r = _run(_request(horizon_sessions=1), _up_barrier(105.0),
             [_bar("2026-09-21", 102, 104, 101, 103, day=21)],
             expected_sessions=["2026-09-21"], calendar_provenance="UNKNOWN")
    assert r.calendar_provenance == "UNKNOWN"
    assert r.break_.value is None
    assert r.break_.status == "BLOCKED_CALENDAR_PROVENANCE"


def test_trusted_expected_sessions_can_resolve_negative_maturity():
    r = _run(_request(horizon_sessions=1), _up_barrier(105.0),
             [_bar("2026-09-21", 102, 104, 101, 103, day=21)],
             expected_sessions=["2026-09-21"], calendar_provenance="VERIFIED_INPUT")
    assert r.break_.value is False
    assert r.break_.status == "OBSERVED_FALSE"


# ── Final closure: roll H=1 acceptance ──
def test_osaka_unknown_roll_blocks_h1_acceptance():
    bar = _bar("2026-09-21", 102, 107, 101, 106, day=21, roll_status="UNKNOWN")
    r = _run(_request(horizon_sessions=1), _up_barrier(105.0), [bar])
    assert r.series_block == L.BLOCKED_ROLL_PROVENANCE
    assert r.acceptance.value is None
    assert r.acceptance.status == L.BLOCKED_ROLL_PROVENANCE


# ── Final closure: acceptance consecutive integrity ──
def test_acceptance_does_not_bridge_missing_expected_session():
    # D1 beyond, D2 MISSING, D3 beyond → must NOT count as 2 consecutive
    bars = [_bar("2026-09-21", 102, 107, 101, 106, day=21),
            _bar("2026-09-23", 106, 108, 105, 107, day=23)]
    r = _run(_request(horizon_sessions=3), _up_barrier(105.0), bars,
             expected_sessions=["2026-09-21", "2026-09-22", "2026-09-23"],
             calendar_provenance="VERIFIED_INPUT")
    assert r.acceptance.value is None
    assert r.acceptance.status == "UNOBSERVABLE_MISSING_DATA"


def test_acceptance_blocks_duplicate_session():
    bars = [_bar("2026-09-21", 102, 107, 101, 106, day=21),
            _bar("2026-09-21", 103, 108, 102, 107, day=21)]
    r = _run(_request(horizon_sessions=1), _up_barrier(105.0), bars,
             expected_sessions=["2026-09-21"])
    assert r.series_block == L.BLOCKED_TEMPORAL_CONTRACT


# ── Final closure: successful label does not promote legacy asof ──
def test_successful_label_does_not_promote_legacy_asof_status():
    bar = _bar("2026-09-21", 102, 107, 101, 106, day=21,
               asof_status="LEGACY_TEMPORAL_UNVERIFIED")
    r = _run(_request(horizon_sessions=1), _up_barrier(105.0), [bar],
             expected_sessions=["2026-09-21"])
    assert r.break_.value is True  # label computed
    assert r.asof_status == "LEGACY_TEMPORAL_UNVERIFIED"  # not promoted

# ── Horizon/provenance hardening (§17) ──
def test_h1_second_session_touch_does_not_count():
    # H=1: D1 no touch, D2 touch → D2 out of window, MUST NOT produce True
    bars = [_bar("2026-09-21", 102, 104, 101, 103, day=21),
            _bar("2026-09-22", 102, 106, 101, 104, day=22)]
    r = _run(_request(horizon_sessions=1), _up_barrier(105.0), bars,
             expected_sessions=["2026-09-21", "2026-09-22"])
    assert r.touch.value is not True
    assert r.observed_outcome_sessions == ["2026-09-21"]
    assert r.ignored_out_of_window_sessions == ["2026-09-22"]


def test_h1_second_session_break_does_not_count():
    bars = [_bar("2026-09-21", 102, 104, 101, 103, day=21),
            _bar("2026-09-22", 102, 107, 101, 106, day=22)]
    r = _run(_request(horizon_sessions=1), _up_barrier(105.0), bars,
             expected_sessions=["2026-09-21", "2026-09-22"])
    assert r.break_.value is False  # only D1 (close 103 < 105) considered; D2 ignored
    assert r.break_.status == "OBSERVED_FALSE"


def test_h1_second_session_acceptance_does_not_count():
    bars = [_bar("2026-09-21", 102, 107, 101, 106, day=21),
            _bar("2026-09-22", 106, 108, 105, 107, day=22)]
    r = _run(_request(horizon_sessions=1), _up_barrier(105.0), bars,
             expected_sessions=["2026-09-21", "2026-09-22"])
    # acceptance needs N=2 consecutive closes; only D1 is in window → D2 must NOT count
    assert r.acceptance.value is False
    assert r.observed_outcome_sessions == ["2026-09-21"]
    assert r.ignored_out_of_window_sessions == ["2026-09-22"]


def test_out_of_window_roll_unknown_does_not_block():
    # D1 valid (roll NONE), D2 roll UNKNOWN (out of H=1 window) → must NOT block D1
    bars = [_bar("2026-09-21", 102, 106, 101, 104, day=21, roll_status="NONE"),
            _bar("2026-09-22", 102, 106, 101, 104, day=22, roll_status="UNKNOWN")]
    r = _run(_request(horizon_sessions=1), _up_barrier(105.0), bars,
             expected_sessions=["2026-09-21", "2026-09-22"])
    assert r.series_block == ""
    assert r.touch.value is True  # D1 touch (low 101 <= 105 <= high 106)


def test_out_of_window_invalid_ohlc_does_not_block():
    bars = [_bar("2026-09-21", 102, 106, 101, 104, day=21),
            _bar("2026-09-22", 102, 104, 999, 103, day=22)]  # D2 low>high invalid
    r = _run(_request(horizon_sessions=1), _up_barrier(105.0), bars,
             expected_sessions=["2026-09-21", "2026-09-22"])
    assert r.series_block == ""
    assert r.touch.value is True


def test_out_of_window_identity_mismatch_does_not_block():
    bars = [_bar("2026-09-21", 102, 106, 101, 104, day=21),
            _bar("2026-09-22", 102, 106, 101, 104, day=22, instrument="^N225")]
    r = _run(_request(horizon_sessions=1), _up_barrier(105.0), bars,
             expected_sessions=["2026-09-21", "2026-09-22"])
    assert r.series_block == ""
    assert r.touch.value is True


def test_positive_acceptance_blocks_without_trusted_session_window():
    bars = [_bar("2026-09-21", 102, 107, 101, 106, day=21),
            _bar("2026-09-22", 106, 108, 105, 107, day=22)]
    r = _run(_request(horizon_sessions=2), _up_barrier(105.0), bars,
             calendar_provenance="UNKNOWN")
    assert r.acceptance.value is None
    assert r.acceptance.status == "BLOCKED_CALENDAR_PROVENANCE"


def test_trusted_empty_elapsed_session_list_is_unmatured():
    r = _run(_request(horizon_sessions=1), _up_barrier(105.0), [],
             expected_sessions=[], calendar_provenance="VERIFIED_INPUT")
    assert r.touch.status == "UNMATURED"
    assert r.break_.status == "UNMATURED"
    assert r.acceptance.status == "UNMATURED"
    assert r.series_block == ""


def test_partial_horizon_touch_true_early():
    # H=3, elapsed=[D1], D1 touch true → Touch True (early positive)
    r = _run(_request(horizon_sessions=3), _up_barrier(105.0),
             [_bar("2026-09-21", 102, 106, 101, 104, day=21)],
             expected_sessions=["2026-09-21"], calendar_provenance="VERIFIED_INPUT")
    assert r.touch.value is True


def test_partial_horizon_no_touch_not_false():
    r = _run(_request(horizon_sessions=3), _up_barrier(105.0),
             [_bar("2026-09-21", 102, 104, 101, 103, day=21)],
             expected_sessions=["2026-09-21"], calendar_provenance="VERIFIED_INPUT")
    assert r.touch.value is None
    assert r.touch.status == "UNMATURED"


def test_touch_negative_requires_trusted_previous_close():
    # previous_close provenance UNKNOWN → Touch negative must NOT be False
    req = _request(horizon_sessions=1, previous_close=None)
    r = _run(req, _up_barrier(105.0), [_bar("2026-09-21", 102, 104, 101, 103, day=21)],
             expected_sessions=["2026-09-21"])
    assert r.touch.value is None
    assert r.touch.status == "BLOCKED_PREWINDOW_REFERENCE_PROVENANCE"


def test_gap_cross_with_missing_previous_close_not_false():
    # first bar entirely above UP barrier, no previous_close → cannot rule out gap cross
    req = _request(horizon_sessions=1, previous_close=None)
    r = _run(req, _up_barrier(105.0), [_bar("2026-09-21", 106, 108, 105.5, 107, day=21)],
             expected_sessions=["2026-09-21"])
    assert r.touch.value is None
    assert r.break_.value is True  # break independent of previous_close


def test_touch_true_does_not_require_previous_close():
    req = _request(horizon_sessions=1, previous_close=None)
    r = _run(req, _up_barrier(105.0), [_bar("2026-09-21", 102, 106, 101, 104, day=21)],
             expected_sessions=["2026-09-21"])
    assert r.touch.value is True  # low<=105<=high → touch regardless of prev close


def test_break_independent_of_previous_close():
    req = _request(horizon_sessions=1, previous_close=None)
    r = _run(req, _up_barrier(105.0), [_bar("2026-09-21", 102, 107, 101, 106, day=21)],
             expected_sessions=["2026-09-21"])
    assert r.break_.value is True


def test_missing_barrier_available_at_blocks_labels():
    r = _run(_request(horizon_sessions=1), _up_barrier(105.0, barrier_available_at=None),
             [_bar("2026-09-21", 102, 104, 101, 103, day=21)],
             expected_sessions=["2026-09-21"])
    assert r.series_block == L.BLOCKED_BARRIER_PROVENANCE
    assert r.touch.value is None and r.break_.value is None and r.acceptance.value is None


def test_verified_request_plus_legacy_outcome_not_asof_verified():
    req = _request(horizon_sessions=1, asof_status="ASOF_VERIFIED")
    bar = _bar("2026-09-21", 102, 106, 101, 104, day=21, asof_status="LEGACY_TEMPORAL_UNVERIFIED")
    r = _run(req, _up_barrier(105.0), [bar], expected_sessions=["2026-09-21"])
    assert r.forecast_asof_status == "ASOF_VERIFIED"
    assert r.outcome_asof_status == "LEGACY_TEMPORAL_UNVERIFIED"
    assert r.asof_status == "LEGACY_TEMPORAL_UNVERIFIED"


def test_legacy_outcome_cannot_be_promoted_by_request_string():
    req = _request(horizon_sessions=1, asof_status="ASOF_VERIFIED")
    bar = _bar("2026-09-21", 102, 106, 101, 104, day=21, asof_status="LEGACY_TEMPORAL_UNVERIFIED")
    r = _run(req, _up_barrier(105.0), [bar], expected_sessions=["2026-09-21"])
    assert r.asof_status != "ASOF_VERIFIED"


def test_result_preserves_forecast_barrier_outcome_snapshot_lineage():
    req = _request(horizon_sessions=1, source_snapshot_ids=["f1"])
    bar = _bar("2026-09-21", 102, 106, 101, 104, day=21, source_snapshot_ids=["o1"])
    barrier = _up_barrier(105.0, source_snapshot_ids=["b1"])
    r = _run(req, barrier, [bar], expected_sessions=["2026-09-21"])
    assert r.forecast_source_snapshot_ids == ["f1"]
    assert r.barrier_source_snapshot_ids == ["b1"]
    assert r.outcome_source_snapshot_ids == ["o1"]
    assert set(r.source_snapshot_ids) == {"f1", "b1", "o1"}


def test_mixed_in_window_series_semantics_blocks():
    bars = [_bar("2026-09-21", 102, 106, 101, 104, day=21, series_semantics="CONTRACT"),
            _bar("2026-09-22", 103, 105, 102, 104, day=22, series_semantics="CONTINUOUS")]
    r = _run(_request(horizon_sessions=2), _up_barrier(105.0), bars,
             expected_sessions=["2026-09-21", "2026-09-22"])
    assert r.series_block == L.BLOCKED_SERIES_SEMANTICS_MISMATCH
