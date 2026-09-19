"""V1.3.1 market open / quote freshness tests（session 與 freshness 分離）。"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from market_ai_hub.services.market_session import (
    asset_class,
    freshness_level,
    quote_freshness,
    session_status,
)


def _sat() -> datetime:
    return datetime(2026, 9, 19, 12, 0, 0, tzinfo=timezone.utc)  # 週六


def _mon() -> datetime:
    return datetime(2026, 9, 21, 12, 0, 0, tzinfo=timezone.utc)  # 週一


def _tue_taipei_open() -> datetime:
    # 2026-09-22 10:00 Taipei = 02:00 UTC（TWSE 交易時段）
    return datetime(2026, 9, 22, 2, 0, 0, tzinfo=timezone.utc)


# ── V1.3.1 回歸測試 ──

def test_A_twse_open_but_quote_stale():
    """週二 10:00 Taipei TWSE open，但 quote stale →
    market_open=true / tradable_now=true / freshness=STALE / quote_live=false / usable=false。"""
    src = datetime(2026, 9, 15, 0, 0, 0, tzinfo=timezone.utc)  # 7 天前 → 日線 STALE~HISTORICAL
    f = quote_freshness("3706.TW", src, received_at=_tue_taipei_open(), as_of=_tue_taipei_open())
    assert f["market_open"] is True
    assert f["tradable_now"] is True
    assert f["freshness_status"] in ("STALE", "HISTORICAL")
    assert f["quote_live"] is False
    assert f["usable_for_live_decision"] is False
    assert f["session_status"] == "OPEN"  # session 不受 stale 影響


def test_B_saturday_usdjpy_closed():
    s = session_status("USDJPY=X", _sat())
    assert s["market_open"] is False
    assert s["tradable_now"] is False
    assert s["session_status"] == "CLOSED"
    # freshness 依實際 quote 判定（fresh quote → 不得因 closed 強制 STALE）
    src = datetime(2026, 9, 19, 11, 59, 0, tzinfo=timezone.utc)
    f = quote_freshness("USDJPY=X", src, received_at=_sat(), as_of=_sat())
    assert f["freshness_status"] in ("LIVE", "RECENT")
    assert f["market_open"] is False


def test_C_saturday_btc_open():
    s = session_status("BTC-USD", _sat())
    assert s["market_open"] is True
    assert s["tradable_now"] is True
    assert s["session_status"] == "OPEN"
    f = quote_freshness("BTC-USD", datetime(2026, 9, 19, 11, 59, 0, tzinfo=timezone.utc),
                        received_at=_sat(), as_of=_sat())
    assert f["freshness_status"] in ("LIVE", "RECENT")
    assert f["market_open"] is True


def test_D_closed_market_fresh_quote_not_forced_stale():
    """閉市 + 新鮮最後 quote → market_open=false，但 freshness 不得被強制 STALE。"""
    src = datetime(2026, 9, 19, 11, 59, 0, tzinfo=timezone.utc)  # 剛收到的 quote（age 小）
    f = quote_freshness("USDJPY=X", src, received_at=_sat(), as_of=_sat())
    assert f["market_open"] is False
    assert f["session_status"] == "CLOSED"
    assert f["freshness_status"] in ("LIVE", "RECENT")  # 不是 STALE


def test_stale_does_not_flip_market_open():
    """核心分離：stale 只影響 quote_live/usable，不影響 market_open/tradable_now。"""
    src = datetime(2026, 9, 14, 0, 0, 0, tzinfo=timezone.utc)  # 很舊
    f = quote_freshness("USDJPY=X", src, received_at=_mon(), as_of=_mon())
    assert f["market_open"] is True      # 週一 fx open，不受 stale 影響
    assert f["tradable_now"] is True
    assert f["session_status"] == "OPEN"
    assert f["freshness_status"] in ("STALE", "HISTORICAL")
    assert f["quote_live"] is False
    assert f["usable_for_live_decision"] is False


# ── 語彙正確性 ──

def test_session_status_vocabulary():
    assert session_status("USDJPY=X", _sat())["session_status"] == "CLOSED"
    assert session_status("USDJPY=X", _mon())["session_status"] == "OPEN"
    assert session_status("BTC-USD", _sat())["session_status"] == "OPEN"
    assert session_status("NQ=F", _mon())["session_status"] == "UNKNOWN"
    # 不得出現 stale 作為 session status
    for sym, ts in (("USDJPY=X", _sat()), ("USDJPY=X", _mon()), ("BTC-USD", _sat()), ("NQ=F", _mon())):
        assert session_status(sym, ts)["session_status"] != "STALE"


def test_freshness_level_vocabulary():
    assert freshness_level(30, "fx") == "LIVE"
    assert freshness_level(600, "fx") == "RECENT"
    assert freshness_level(36000, "fx") == "STALE"
    assert freshness_level(200000, "fx") == "HISTORICAL"
    assert freshness_level(None, "fx") == "UNKNOWN"


def test_source_received_separated_and_live_flag():
    src = datetime(2026, 9, 21, 10, 0, 0, tzinfo=timezone.utc)
    rec = datetime(2026, 9, 21, 10, 0, 30, tzinfo=timezone.utc)
    f = quote_freshness("USDJPY=X", src, received_at=rec, as_of=rec)
    assert f["source_timestamp"] == "2026-09-21T10:00:00+00:00"
    assert f["received_at"] == "2026-09-21T10:00:30+00:00"
    assert f["quote_age_seconds"] == pytest.approx(30.0)
    assert f["quote_live"] is True
    assert f["usable_for_live_decision"] is True


def test_incomplete_data_not_usable():
    src = datetime(2026, 9, 21, 10, 0, 0, tzinfo=timezone.utc)
    rec = datetime(2026, 9, 21, 10, 0, 30, tzinfo=timezone.utc)
    f = quote_freshness("USDJPY=X", src, received_at=rec, as_of=rec, complete=False)
    assert f["quote_live"] is True
    assert f["usable_for_live_decision"] is False


def test_asset_class_mapping():
    assert asset_class("USDJPY=X") == "fx"
    assert asset_class("BTC-USD") == "crypto"
    assert asset_class("^N225") == "index"
    assert asset_class("3706.TW") == "equity"
    assert asset_class("3706") == "equity"
