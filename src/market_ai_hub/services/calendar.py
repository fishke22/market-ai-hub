"""交易所日曆（V1.2）。

正式改用 exchange_calendars（QuantConnect，可靠、含台灣補班/彈性放假規則）：
- TWSE → XTAI（Asia/Taipei）；TSE/^N225 → XTKS（Asia/Tokyo）
- trading_date = 該 bar 在交易所時區的「當地日期」（禁止用 UTC calendar date 當 trading_date）
- forecast_target_dates = 嚴格在 last_observed_trading_date 之後的未來 sessions
  （絕不包含已觀察 bar）

calendar 未確認（library 缺 / 未覆蓋到未來）→ CALENDAR_UNVERIFIED，不得假裝 exact。
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone

import pandas as pd

log = logging.getLogger(__name__)

try:
    import exchange_calendars as xcals

    _CAL = {
        "TWSE": xcals.get_calendar("XTAI"),
        "TSE": xcals.get_calendar("XTKS"),
    }
    _HAS_XCALS = True
except Exception as e:  # pragma: no cover
    log.warning("exchange_calendars unavailable: %s; calendar unverified", e)
    _CAL = {}
    _HAS_XCALS = False

EXCHANGE_TIMEZONE = {"TWSE": "Asia/Taipei", "TSE": "Asia/Tokyo"}


def exchange_for_symbol(symbol: str) -> str:
    if symbol == "^N225":
        return "TSE"
    return "TWSE"


def exchange_timezone(symbol: str) -> str:
    return EXCHANGE_TIMEZONE[exchange_for_symbol(symbol)]


def calendar_name(symbol: str) -> str:
    return {"TWSE": "XTAI", "TSE": "XTKS"}[exchange_for_symbol(symbol)]


def _cal(symbol: str):
    return _CAL.get(exchange_for_symbol(symbol))


def calendar_verified(symbol: str) -> bool:
    if not _HAS_XCALS:
        return False
    c = _cal(symbol)
    return c is not None


def trading_date_of(ts_utc: datetime | pd.Timestamp, symbol: str) -> str:
    """bar 的 UTC 時間戳 → 交易所當地 trading_date（YYYY-MM-DD）。"""
    ts = pd.Timestamp(ts_utc)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    local = ts.tz_convert(exchange_timezone(symbol))
    return local.date().strftime("%Y-%m-%d")


def is_session(symbol: str, d: date | datetime | str) -> bool:
    if not calendar_verified(symbol):
        return False
    ts = pd.Timestamp(d)
    return bool(_cal(symbol).is_session(ts))


def next_trading_sessions(symbol: str, after_date: date | datetime | str, n: int) -> list[str]:
    """after_date 之後的 n 個未來交易 session（嚴格不含 after_date 本身）。"""
    if n <= 0:
        return []
    if not calendar_verified(symbol):
        # CALENDAR_UNVERIFIED：給 best-effort（只跳週末），明確標記非 exact（由 caller 標 grade）
        start = pd.Timestamp(after_date) + pd.Timedelta(days=1)
        return [d.strftime("%Y-%m-%d") for d in pd.bdate_range(start=start, periods=n)]
    c = _cal(symbol)
    ts = pd.Timestamp(after_date)
    end = ts + pd.Timedelta(days=365 * 2)
    if c.last_session is not None:
        end = min(end, pd.Timestamp(c.last_session))
    sched = c.sessions_in_range(ts + pd.Timedelta(days=1), end)
    return [d.strftime("%Y-%m-%d") for d in sched[:n]]


def calendar_metadata(symbol: str) -> dict:
    ex = exchange_for_symbol(symbol)
    verified = calendar_verified(symbol)
    meta = {
        "calendar_name": calendar_name(symbol),
        "exchange_timezone": exchange_timezone(symbol),
        "calendar_source": "exchange_calendars (QuantConnect)" if _HAS_XCALS else "NONE",
        "calendar_verified": verified,
        "calendar_grade": "EXCHANGE_VERIFIED" if verified else "CALENDAR_UNVERIFIED",
        "calendar_last_verified": datetime.now(timezone.utc).isoformat() if verified else None,
    }
    if verified:
        c = _cal(symbol)
        meta["calendar_first_session"] = str(c.first_session.date())
        meta["calendar_last_session"] = str(c.last_session.date())
    return meta


# ── 2Q-F.3：OSE derivatives holiday trading calendar（JPX official）──
_OSE_HOLIDAY_SESSIONS: list[str] | None = None


def _ose_holiday_trading_sessions() -> list[str]:
    global _OSE_HOLIDAY_SESSIONS
    if _OSE_HOLIDAY_SESSIONS is None:
        try:
            import yaml

            from market_ai_hub.config.settings import project_root

            cfg = yaml.safe_load((project_root() / "config" / "ose_derivatives_calendar.yaml").read_text(encoding="utf-8"))
            _OSE_HOLIDAY_SESSIONS = [str(d) for d in cfg.get("holiday_trading_sessions", [])]
        except Exception as e:  # pragma: no cover
            log.warning("OSE derivatives calendar unavailable: %s", e)
            _OSE_HOLIDAY_SESSIONS = []
    return _OSE_HOLIDAY_SESSIONS


def next_ose_derivatives_sessions(after_date: date | datetime | str, n: int) -> list[str]:
    """after_date 之後的 n 個 OSE derivatives sessions。

    = XTKS（TSE cash）sessions + JPX Holiday Trading sessions（TSE cash 休市但 OSE OPEN）。
    e.g. after 2026-09-18 → 2026-09-21/22/23（holiday trading）+ 2026-09-24/25（XTKS）。
    """
    if n <= 0:
        return []
    holiday = _ose_holiday_trading_sessions()
    cash = next_trading_sessions("^N225", after_date, n)  # XTKS sessions
    combined = sorted(set(cash) | set(holiday))
    start = str(pd.Timestamp(after_date).date())
    return [d for d in combined if d > start][:n]


def sanitize_daily_exchange_sessions(df: "pd.DataFrame", symbol: str) -> "pd.DataFrame":
    """2Q-F.4：daily bars 只保留 exchange 有效 session（排除週末/休市 invalid bars）。

    對 ^TWII / *.TW / *.TWO → XTAI；^N225 → XTKS。非 session 的 rows 標 invalid_session 並排除。
    raw 保留供 audit；latest reference / model origin / features / forecast 不得用 invalid row。
    """
    if df is None or df.empty:
        return df
    out = df.copy()
    ex = exchange_for_symbol(symbol)
    invalid = []
    for idx, row in out.iterrows():
        ts = pd.Timestamp(row.get("timestamp_utc") or row.get("timestamp_local"))
        if ts.tzinfo is None:
            ts = ts.tz_localize("UTC")
        local_date = ts.tz_convert(exchange_timezone(symbol)).date()
        if not is_session(symbol, local_date):
            invalid.append(idx)
    if invalid:
        out.loc[invalid, "invalid_session"] = True
    valid = out[~out.index.isin(invalid)]
    return valid


def calendar_covers(symbol: str, dates: list[str]) -> bool:
    """calendar 是否覆蓋所有 target dates（超過 last_session → 未覆蓋）。"""
    if not calendar_verified(symbol) or not dates:
        return False
    c = _cal(symbol)
    return all(pd.Timestamp(d) <= pd.Timestamp(c.last_session.date()) for d in dates)


def forecast_anchor(symbol: str, last_ts: datetime | pd.Timestamp, steps: int) -> dict:
    """V1.2 temporal anchor：產生 forecast_origin / last_observed_trading_date /
    forecast_target_dates（future-only）+ calendar metadata。

    last_ts = 最後一根已觀察 bar 的 UTC 時間戳。
    forecast_target_dates 嚴格 = 該交易日之後的未來 sessions，不含已觀察 bar。
    """
    origin = pd.Timestamp(last_ts)
    if origin.tzinfo is None:
        origin = origin.tz_localize("UTC")
    origin = origin.tz_convert("UTC")
    last_obs = trading_date_of(origin, symbol)
    target_dates = next_trading_sessions(symbol, last_obs, steps)
    meta = calendar_metadata(symbol)
    covered = calendar_covers(symbol, target_dates)
    return {
        "forecast_origin": origin.isoformat(),
        "last_observed_trading_date": last_obs,
        "forecast_target_dates": target_dates,
        "exchange_timezone": meta["exchange_timezone"],
        "target_calendar": meta["calendar_name"],
        "calendar_name": meta["calendar_name"],
        "calendar_source": meta["calendar_source"],
        "calendar_verified": meta["calendar_verified"] and covered,
        "calendar_grade": "EXCHANGE_VERIFIED" if (meta["calendar_verified"] and covered) else "CALENDAR_UNVERIFIED",
        "calendar_last_verified": meta["calendar_last_verified"],
    }
