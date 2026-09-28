from datetime import datetime, timezone

import pandas as pd

import market_ai_hub.services.jnu_trading_path as tp


UTC = timezone.utc


def _raw_session(*, pm: bool, start_hour: int, n: int, base: float, step: float = 5.0):
    code = "JNUPM2612" if pm else "JNU2612"
    rows = []
    start = pd.Timestamp("2026-09-25", tz="Asia/Tokyo") + pd.Timedelta(hours=start_hour)
    for i in range(n):
        ts = start + pd.Timedelta(minutes=5 * i)
        price = base + step * i
        rows.append(
            {
                "received_at": ts.tz_convert("UTC").isoformat(),
                "provider": "YUANTA_SPARK",
                "callback_type": "SubscribeWatchlistAll",
                "market_no": 207,
                "instrument_code": code,
                "deal": price,
                "vol": 2 + (i % 3),
                "source_time_of_day": ts.strftime("%H:%M:%S.000"),
                "timestamp_quality": "SOURCE_TIME_OF_DAY_ONLY",
            }
        )
    return rows


class _Resolved:
    verified = True
    spark_code = "JNU2612"


class _Resolver:
    def resolve(self, logical_instrument, asof):
        assert logical_instrument == "OSE_NIKKEI225_MICRO_FUTURES"
        return _Resolved()


def _settlement(month="202610"):
    s = pd.Series(
        [66000.0, 66140.0],
        index=pd.to_datetime(["2026-09-24", "2026-09-25"], utc=True),
    )
    return s, {
        "status": "OK",
        "contract_month": month,
        "quote_code": "JNU2610" if month == "202610" else "JNU2612",
        "latest_date": "2026-09-25",
        "latest_settlement": 66140.0,
    }


def _patch_common(monkeypatch, settlement_month="202610"):
    monkeypatch.setattr(tp, "YuantaInstrumentResolver", lambda: _Resolver())
    monkeypatch.setattr(tp, "load_direct_micro_settlements", lambda: _settlement(settlement_month))
    monkeypatch.setattr(
        tp,
        "_current_quote_status",
        lambda now: {
            "live_now_verified": False,
            "provider_status": "DEGRADED",
            "health_reasons": ["NO_RECENT_CALLBACK_SESSION_UNCHECKED"],
        },
    )
    class Venue:
        def model_dump(self):
            return {"venue_id": "OSE_DERIVATIVES", "session_status": "CLOSED"}
    monkeypatch.setattr(tp, "resolve_venue_session", lambda venue, asof: Venue())


def test_contract_mismatch_blocks_gap_and_incomplete_night_is_not_close(monkeypatch):
    _patch_common(monkeypatch, "202610")
    rows = pd.DataFrame(_raw_session(pm=True, start_hour=17, n=13, base=66200.0))
    out = tp.build_jnu_trading_path_context(
        now=datetime(2026, 9, 27, 12, tzinfo=UTC),
        trade_rows=rows,
    )
    assert out["status"] == "OK"
    assert out["settlement_forecast"]["contract_month"] == "202610"
    assert out["decision_contract"]["contract_month"] == "202612"
    assert out["contract_alignment"]["status"] == "CONTRACT_MISMATCH"
    assert out["contract_alignment"]["settlement_to_session_gap_points"] is None
    assert out["hard_boundaries"]["cross_contract_gap_allowed"] is False
    assert out["price_semantics"]["TARGET_PREVIOUS_NIGHT_CLOSE"] is None
    assert out["night_session"]["verified_close"] is False
    assert out["price_semantics"]["TARGET_LATEST_PRICE_LIVE_NOW_VERIFIED"] is False
    assert out["event_context"]["dated_event_status"] == "PROVIDER_FRAMEWORK_ONLY_NO_DATED_EVENTS"
    assert out["event_context"]["dated_event_data_ready"] is False


def test_same_contract_allows_typed_settlement_to_session_gap(monkeypatch):
    _patch_common(monkeypatch, "202612")
    rows = pd.DataFrame(_raw_session(pm=False, start_hour=9, n=36, base=66150.0, step=0.0))
    out = tp.build_jnu_trading_path_context(
        now=datetime(2026, 9, 25, 7, tzinfo=UTC),
        trade_rows=rows,
    )
    assert out["contract_alignment"]["status"] == "SAME_CONTRACT"
    assert out["contract_alignment"]["cross_contract_arithmetic_allowed"] is True
    assert out["contract_alignment"]["settlement_to_session_gap_points"] == 10.0


def test_structure_price_profile_is_descriptive_and_volume_profile_fails_closed():
    rows = pd.DataFrame(_raw_session(pm=False, start_hour=9, n=40, base=66000.0, step=5.0))
    norm = tp._normalize_trade_rows(rows)
    s = tp._structure(norm)
    assert s["status"] == "AVAILABLE_DESCRIPTIVE_ONLY"
    assert s["structure_state"] == "UP_TREND_CANDIDATE"
    assert s["predictive_claim"] is False
    assert s["support_resistance_generated"] is False
    assert s["price_profile"]["status"] == "AVAILABLE_DESCRIPTIVE_ONLY"
    assert s["price_profile"]["not_volume_profile"] is True
    assert s["price_profile"]["not_support_resistance"] is True
    assert s["volume_profile"]["status"] == "VOLUME_PROFILE_NOT_AVAILABLE"
    assert s["volume_profile"]["watchlist_vol_not_accepted_as_trade_volume"] is True
    assert s["volume_profile"]["not_probability"] is True


def test_acceptance_distinguishes_touch_break_acceptance_and_false_breakout():
    rows = []
    start = pd.Timestamp("2026-09-25 09:00", tz="Asia/Tokyo")
    closes = [66580, 66590, 66600, 66610, 66620, 66625, 66630, 66635]
    for i, close in enumerate(closes):
        ts = start + pd.Timedelta(minutes=5 * i)
        # 4 observations per bar; enough rows for structure gate.
        for j, px in enumerate([close - 5, close, close + 5, close]):
            t = ts + pd.Timedelta(seconds=30 * j)
            rows.append({
                "received_at": t.tz_convert("UTC").isoformat(),
                "instrument_code": "JNU2612",
                "market_no": 207,
                "deal": px,
                "vol": 1,
                "source_time_of_day": t.strftime("%H:%M:%S.000"),
                "timestamp_quality": "SOURCE_TIME_OF_DAY_ONLY",
            })
    norm = tp._normalize_trade_rows(pd.DataFrame(rows))
    ev = tp.evaluate_acceptance_from_trades(norm, level=66600.0, direction="UP")
    assert ev["touch"] is True
    assert ev["break"] is True
    assert ev["acceptance"] is True
    assert ev["false_breakout"] is False
    assert ev["touch_is_not_break"] is True
    assert ev["break_is_not_acceptance"] is True
    assert ev["not_probability"] is True


def test_acceptance_requires_explicit_level():
    out = tp.evaluate_acceptance_from_trades(pd.DataFrame(), level=None)
    assert out["status"] == "LEVEL_REQUIRED"
    assert out["acceptance"] is None


def test_night_close_requires_actual_close_boundary():
    # Last PM trade exactly 06:00 JST next day; verified close may be surfaced.
    rows = pd.DataFrame([
        {
            "received_at": "2026-09-25T08:00:00+00:00",  # 17:00 JST
            "instrument_code": "JNUPM2612", "market_no": 207,
            "deal": 66200.0, "vol": 1, "source_time_of_day": "17:00:00.000",
            "timestamp_quality": "SOURCE_TIME_OF_DAY_ONLY",
        },
        {
            "received_at": "2026-09-25T21:00:00+00:00",  # 06:00 JST next day
            "instrument_code": "JNUPM2612", "market_no": 207,
            "deal": 66475.0, "vol": 1, "source_time_of_day": "06:00:00.000",
            "timestamp_quality": "SOURCE_TIME_OF_DAY_ONLY",
        },
    ])
    norm = tp._normalize_trade_rows(rows)
    snap = tp._session_snapshot(norm, "NIGHT")
    assert snap["verified_close"] is True
    assert snap["verified_close_price"] == 66475.0


def test_preclose_observation_is_never_upgraded_to_verified_close():
    rows = pd.DataFrame([
        {
            "received_at": "2026-09-25T06:44:59+00:00",  # 15:44:59 JST
            "instrument_code": "JNU2612", "market_no": 207,
            "deal": 66280.0, "vol": 1, "source_time_of_day": "15:44:59.000",
            "timestamp_quality": "SOURCE_TIME_OF_DAY_ONLY",
        },
    ])
    norm = tp._normalize_trade_rows(rows)
    snap = tp._session_snapshot(norm, "DAY")
    assert snap["verified_close"] is False
    assert snap["verified_close_price"] is None
    assert snap["coverage_complete"] is False
    assert snap["close_lag_seconds"] == -1.0


def test_user_summary_never_calls_partial_night_observation_a_close(monkeypatch):
    _patch_common(monkeypatch, "202610")
    rows = pd.DataFrame(_raw_session(pm=True, start_hour=17, n=13, base=66200.0))
    out = tp.build_jnu_trading_path_context(
        now=datetime(2026, 9, 27, 12, tzinfo=UTC),
        trade_rows=rows,
    )
    summary = tp.jnu_trading_path_user_summary(out)
    assert "不能把最後一筆夜盤資料冒充收盤價" in summary["前一夜收盤"]
    assert "禁止直接相減" in summary["合約對齊"]
    assert summary["PREDICTIVE_GAIN"] is False
    assert summary["CALIBRATED"] is False
    assert summary["TRADING_EDGE"] is False
