"""Market open / quote freshness（V1.3.1：session 與 freshness 正式分離）。

V1.3.1 語義修正：
- market_open / tradable_now / session_status 只由「市場交易制度 + session 規則」決定，
  與資料新鮮度無關。stale quote 不得把 market_open / tradable_now 改成 false。
- session_status 使用：OPEN / CLOSED / PREOPEN / AFTER_HOURS / HOLIDAY_SESSION / UNKNOWN。
  不得使用 STALE 當 session status。
- freshness_status 使用：LIVE / RECENT / STALE / HISTORICAL / UNKNOWN（只看 quote age / SLA）。
- quote_live：boolean，依 quote age / source SLA。
- usable_for_live_decision：boolean，只有資料夠新（quote_live）且完整才 true。
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

ASSET_CLASS = {
    "^N225": "index",
    "USDJPY=X": "fx",
    "JPY=X": "fx",
    "BTC-USD": "crypto",
}

# freshness 門檻（秒），依資產類別：LIVE <= live_after；RECENT <= recent_after；
# STALE <= stale_after；超過 → HISTORICAL。
_FRESHNESS_THRESHOLDS = {
    "fx": {"live": 60, "recent": 3600, "stale": 86400},
    "crypto": {"live": 60, "recent": 900, "stale": 86400},
    "index": {"live": 3600, "recent": 86400, "stale": 7 * 86400},
    "equity": {"live": 3600, "recent": 86400, "stale": 7 * 86400},
    "default": {"live": 60, "recent": 3600, "stale": 86400},
}


def asset_class(symbol: str) -> str:
    if symbol in ASSET_CLASS:
        return ASSET_CLASS[symbol]
    body = symbol.split(".")[0]
    if body.isdigit() or symbol.upper().endswith(".TW"):
        return "equity"
    return "proxy"


def _exchange_open(symbol: str, as_of: datetime) -> bool:
    from market_ai_hub.services.calendar import is_session, trading_date_of

    td = trading_date_of(as_of, symbol)
    return is_session(symbol, td)


def _fx_open(as_of: datetime) -> bool:
    """FX（USDJPY spot）簡化 session：週六/週日休市（UTC）。"""
    u = as_of.astimezone(timezone.utc)
    return u.weekday() not in (5, 6)


def session_status(symbol: str, as_of: datetime | None = None) -> dict:
    """只由交易制度/session 決定，與資料新鮮度無關。

    session_status ∈ OPEN / CLOSED / UNKNOWN（TWSE/TSE/fx 目前無 intraday 小時，
    故只分 OPEN/CLOSED；PREOPEN/AFTER_HOURS/HOLIDAY_SESSION 保留給未來 intraday/OSE）。
    """
    as_of = as_of or datetime.now(timezone.utc)
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    ac = asset_class(symbol)
    if ac == "crypto":
        return {"asset_class": ac, "market_open": True, "tradable_now": True, "session_status": "OPEN"}
    if ac == "fx":
        open_ = _fx_open(as_of)
        return {"asset_class": ac, "market_open": open_, "tradable_now": open_,
                "session_status": "OPEN" if open_ else "CLOSED"}
    if ac in ("index", "equity"):
        open_ = _exchange_open(symbol, as_of)
        return {"asset_class": ac, "market_open": open_, "tradable_now": open_,
                "session_status": "OPEN" if open_ else "CLOSED"}
    return {"asset_class": ac, "market_open": None, "tradable_now": None, "session_status": "UNKNOWN"}


def freshness_level(age_seconds: float | None, ac: str) -> str:
    """純 quote age → LIVE / RECENT / STALE / HISTORICAL / UNKNOWN。"""
    if age_seconds is None:
        return "UNKNOWN"
    t = _FRESHNESS_THRESHOLDS.get(ac, _FRESHNESS_THRESHOLDS["default"])
    if age_seconds <= t["live"]:
        return "LIVE"
    if age_seconds <= t["recent"]:
        return "RECENT"
    if age_seconds <= t["stale"]:
        return "STALE"
    return "HISTORICAL"


def quote_freshness(
    symbol: str,
    source_timestamp: datetime | pd.Timestamp | None,
    received_at: datetime | None = None,
    as_of: datetime | None = None,
    complete: bool = True,
) -> dict:
    """分離的 session 與 freshness。

    回傳：
    - session 欄位（market_open / tradable_now / session_status）：只由交易制度決定，不受 stale 影響
    - freshness 欄位（freshness_status / quote_live / quote_age_seconds）：只由 quote age 決定
    - usable_for_live_decision = quote_live AND complete
    """
    received_at = received_at or datetime.now(timezone.utc)
    as_of = as_of or received_at
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    if received_at.tzinfo is None:
        received_at = received_at.replace(tzinfo=timezone.utc)

    sess = session_status(symbol, as_of)

    if source_timestamp is None:
        age = None
        freshness = "UNKNOWN"
        src_iso = ""
    else:
        src = pd.Timestamp(source_timestamp)
        if src.tzinfo is None:
            src = src.tz_localize("UTC")
        src_iso = src.isoformat()
        age = (received_at - src.to_pydatetime()).total_seconds()
        freshness = freshness_level(age, sess["asset_class"])

    quote_live = freshness in ("LIVE", "RECENT")
    usable = bool(quote_live and complete and src_iso != "")

    return {
        **sess,
        "source_timestamp": src_iso,
        "received_at": received_at.isoformat(),
        "quote_age_seconds": round(age, 3) if age is not None else None,
        "freshness_status": freshness,
        "quote_live": quote_live,
        "usable_for_live_decision": usable,
    }
