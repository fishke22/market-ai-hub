"""Market open / quote freshness（V1.3.1：session 與 freshness 正式分離）。

V2-A.2：session 由 research.v2.session_truth 的 venue registry + intraday hours 決定
（不再把「日曆是交易日」等同「整個日曆日 OPEN」）。未知 symbol → UNKNOWN（不默認 TWSE）。
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from market_ai_hub.research.v2.session_truth import (
    resolve_symbol_session, TRADING_SESSION_STATUSES,
)

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


def session_status(symbol: str, as_of: datetime | None = None) -> dict:
    """Legacy OPEN/CLOSED/UNKNOWN，derived from V2-A.2 venue session truth.

    Only a real intraday trading session is OPEN; a tradeable calendar day outside session hours is
    CLOSED. Unknown symbols/venues → UNKNOWN (no silent venue fallback).
    """
    as_of = as_of or datetime.now(timezone.utc)
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=timezone.utc)
    ac = asset_class(symbol)
    ctx = resolve_symbol_session(symbol, as_of)
    if ctx is None or ctx.session_status == "UNKNOWN":
        return {"asset_class": ac, "market_open": None, "tradable_now": None,
                "session_status": "UNKNOWN"}
    open_ = ctx.session_status in TRADING_SESSION_STATUSES
    return {
        "asset_class": ac,
        "market_open": open_,
        "tradable_now": open_,
        "session_status": "OPEN" if open_ else "CLOSED",
        "venue_id": ctx.venue_id,
        "venue_session_status": ctx.session_status,
        "trading_date": ctx.trading_date,
    }


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
