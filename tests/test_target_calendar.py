"""V1.2 temporal & calendar tests（forecast target date / timezone / exchange calendar）。

使用 exchange_calendars：TWSE=XTAI、TSE=XTKS。forecast targets 必須是 future sessions。
"""
from __future__ import annotations

import pytest

from market_ai_hub.services.calendar import (
    calendar_metadata,
    forecast_anchor,
    is_session,
    next_trading_sessions,
    trading_date_of,
)


# ── H.3 台灣官方假日正確跳過（2026-09-25 中秋節 + 9/28 彈性放假）──
def test_twse_mid_autumn_holiday_2026():
    assert not is_session("3706.TW", "2026-09-25")  # 中秋節
    assert not is_session("3706.TW", "2026-09-28")  # 彈性放假
    assert is_session("3706.TW", "2026-09-24")
    assert is_session("3706.TW", "2026-09-29")


# ── H.5 ^N225 TSE 假日（9/21 敬老之日、9/22 國民休日、9/23 秋分之日）──
def test_tse_holiday_week_2026():
    for d in ("2026-09-21", "2026-09-22", "2026-09-23"):
        assert not is_session("^N225", d)
    assert is_session("^N225", "2026-09-24")
    assert is_session("^N225", "2026-09-25")


# ── H.4 UTC -> Asia/Taipei 日期正確（不得少一天）──
def test_twse_trading_date_no_off_by_one():
    # TWSE bar 2026-09-18 收盤；TWSE 日 bar 的 UTC 常為前一日 16:00Z（= Taipei 00:00）
    assert trading_date_of("2026-09-17T16:00:00Z", "3706.TW") == "2026-09-18"


# ── H.5 ^N225 UTC -> Asia/Tokyo 正確 ──
def test_tse_trading_date_tokyo():
    assert trading_date_of("2026-09-17T15:00:00Z", "^N225") == "2026-09-18"  # 15:00Z = 9/18 00:00 JST
    assert trading_date_of("2026-09-18T06:00:00Z", "^N225") == "2026-09-18"


# ── H.1 3706 1d target 不得為 last observed date ──
def test_twse_1d_target_is_future():
    a = forecast_anchor("3706.TW", "2026-09-18T05:30:00Z", 1)
    assert a["last_observed_trading_date"] == "2026-09-18"
    assert a["forecast_target_dates"] == ["2026-09-21"]  # 下一個真正 TWSE 交易日
    assert "2026-09-18" not in a["forecast_target_dates"]


# ── H.2 3706 2d/5d/10d 全為 future sessions ──
def test_twse_multi_step_targets_all_future():
    a = forecast_anchor("3706.TW", "2026-09-18T05:30:00Z", 10)
    last = a["last_observed_trading_date"]
    assert len(a["forecast_target_dates"]) == 10
    assert all(t > last for t in a["forecast_target_dates"])
    assert "2026-09-18" not in a["forecast_target_dates"]
    # 9/25（中秋）與 9/28（彈性放假）不得出現
    assert "2026-09-25" not in a["forecast_target_dates"]
    assert "2026-09-28" not in a["forecast_target_dates"]


# ── H.6 ^N225 5d 全是 future XTKS sessions ──
def test_tse_5d_targets_all_future():
    a = forecast_anchor("^N225", "2026-09-18T06:00:00Z", 5)
    assert a["forecast_target_dates"] == ["2026-09-24", "2026-09-25", "2026-09-28", "2026-09-29", "2026-09-30"]
    for h in ("2026-09-21", "2026-09-22", "2026-09-23", "2026-09-18"):
        assert h not in a["forecast_target_dates"]


# ── H.7 OSE user window vs ^N225 target mismatch（wrapper 層）──
def test_ose_window_mismatch(monkeypatch):
    from market_ai_hub.services import analysis
    from tests.test_horizon_integrity import _FakeYF

    class FA:
        pass

    from market_ai_hub.models.chronos_model import chronos_forecast
    from tests.test_horizon_integrity import FakeChronosAdapter as FC

    def fake_chronos(adapter, symbol, closes, horizon="1d", horizon_steps=7, data_grade="RESEARCH_PROXY", data_frequency="1d"):
        return chronos_forecast(FC(), symbol, closes, horizon=horizon, horizon_steps=horizon_steps)

    monkeypatch.setattr(analysis, "chronos_forecast", fake_chronos)
    monkeypatch.setattr(analysis, "timesfm_forecast", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("skip")))
    monkeypatch.setattr(analysis, "baseline_forecast", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("skip")))
    monkeypatch.setattr(analysis, "YFinanceProvider", lambda: _FakeYF())
    monkeypatch.setattr(analysis, "get_chronos", lambda: FA())
    monkeypatch.setattr(analysis, "get_timesfm", lambda: FA())
    monkeypatch.setattr(analysis, "BaselineClassifier", lambda n: None)

    r = analysis.analyze_osaka_nikkei(horizon="5d", requested_dates="2026-09-21..2026-09-25")
    assert r["calendar_mismatch"] is True
    assert "CALENDAR_TARGET_MISMATCH" in r["mismatch_detail"]
    assert set(r["unmapped_sessions"]) == {"2026-09-21", "2026-09-22", "2026-09-23"}
    assert r["proxy_target_calendar"] == "XTKS"
    # forecast targets 全是 future TSE sessions
    assert all(t > r["last_observed_trading_date"] for t in r["forecast_target_dates"])


# ── H.10 stale / unverified calendar detection ──
def test_calendar_metadata_verified():
    m = calendar_metadata("^N225")
    assert m["calendar_name"] == "XTKS"
    assert m["calendar_verified"] is True
    assert m["calendar_grade"] == "EXCHANGE_VERIFIED"
    assert m["calendar_source"]


def test_calendar_unverified_when_lib_missing(monkeypatch):
    import market_ai_hub.services.calendar as cal

    monkeypatch.setattr(cal, "_HAS_XCALS", False)
    monkeypatch.setattr(cal, "_CAL", {})
    m = cal.calendar_metadata("^N225")
    assert m["calendar_verified"] is False
    assert m["calendar_grade"] == "CALENDAR_UNVERIFIED"


def test_next_sessions_strictly_future():
    ts = next_trading_sessions("3706.TW", "2026-09-18", 3)
    assert ts == ["2026-09-21", "2026-09-22", "2026-09-23"]
    assert "2026-09-18" not in ts
