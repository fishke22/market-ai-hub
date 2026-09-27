"""Target-specific Taiwan-stock context with explicit as-of/source semantics.

This layer is intentionally CONTEXT ONLY. It does not feed the forecast models and
must not be interpreted as predictive gain, calibrated probability, or trading edge.
Date-only vendor fields use conservative availability boundaries; datasets that lack
publication timestamps remain non-PIT and cannot be promoted into model features.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
from typing import Any

import pandas as pd

from market_ai_hub.providers.finmind import DATASET_TIER, FinMindProvider
from market_ai_hub.services.taiwan_stock_data import normalize_taiwan_symbol

CONTEXT_SCHEMA_VERSION = "TAIWAN_STOCK_CONTEXT_V2"
SOURCE_SEMANTICS_VERSION = "FINMIND_FREE_TARGET_CONTEXT_ASOF_V2"
FRESHNESS_POLICY_VERSION = "TAIWAN_STOCK_CONTEXT_FRESHNESS_V2"
SOURCE_RECONCILIATION_VERSION = "TAIWAN_STOCK_SOURCE_RECONCILIATION_V1"
CONTEXT_ROLE = "TARGET_CONTEXT_ONLY_NOT_PREDICTIVE_FEATURE"
DATA_GRADE = "RESEARCH_CONTEXT_VENDOR_AGGREGATE"
_TW_TZ = "Asia/Taipei"
_FINMIND_ENDPOINT = "https://api.finmindtrade.com/api/v4/data"

_FRESHNESS_HOURS = {
    "valuation": (96.0, 168.0),
    "monthly_revenue": (45.0 * 24.0, 75.0 * 24.0),
    "institutional_flow": (96.0, 168.0),
    "margin_short": (96.0, 168.0),
    "securities_lending": (96.0, 168.0),
    "shareholding": (96.0, 168.0),
}

_FACTOR_SPECS: dict[str, dict[str, tuple[str, str, str]]] = {
    "valuation": {
        "pe_ratio": ("pe_ratio", "RATIO", "TRADING_DATE"),
        "pbr": ("pbr", "RATIO", "TRADING_DATE"),
        "dividend_yield": ("dividend_yield", "PERCENT", "TRADING_DATE"),
    },
    "monthly_revenue": {
        "monthly_revenue": ("revenue", "TWD", "REVENUE_MONTH"),
        "monthly_revenue_mom": ("mom_growth", "DECIMAL_RETURN", "REVENUE_MONTH"),
        "monthly_revenue_yoy": ("yoy_growth", "DECIMAL_RETURN", "REVENUE_MONTH"),
    },
    "eps": {
        "eps": ("eps", "TWD_PER_SHARE", "FINANCIAL_STATEMENT_PERIOD_END"),
    },
    "dividend_ex_right": {
        "cash_ex_dividend_trading_date": ("CashExDividendTradingDate", "DATE", "ANNOUNCED_CORPORATE_ACTION"),
        "stock_ex_dividend_trading_date": ("StockExDividendTradingDate", "DATE", "ANNOUNCED_CORPORATE_ACTION"),
        "cash_earnings_distribution": ("CashEarningsDistribution", "SOURCE_NATIVE_AMOUNT_UNIT_UNSPECIFIED", "ANNOUNCED_CORPORATE_ACTION"),
        "stock_earnings_distribution": ("StockEarningsDistribution", "SOURCE_NATIVE_AMOUNT_UNIT_UNSPECIFIED", "ANNOUNCED_CORPORATE_ACTION"),
    },
    "institutional_flow": {
        "foreign_investor_net": ("foreign_investor_net", "SHARES", "TRADING_DATE"),
        "investment_trust_net": ("investment_trust_net", "SHARES", "TRADING_DATE"),
        "dealer_net": ("dealer_net", "SHARES", "TRADING_DATE"),
        "foreign_dealer_self_net": ("foreign_dealer_self_net", "SHARES", "TRADING_DATE"),
        "institutional_total_net": ("total_net", "SHARES", "TRADING_DATE"),
    },
    "margin_short": {
        "margin_purchase_buy": ("MarginPurchaseBuy", "SOURCE_NATIVE_COUNT_UNIT_UNSPECIFIED", "TRADING_DATE"),
        "margin_purchase_sell": ("MarginPurchaseSell", "SOURCE_NATIVE_COUNT_UNIT_UNSPECIFIED", "TRADING_DATE"),
        "margin_purchase_today_balance": ("MarginPurchaseTodayBalance", "SOURCE_NATIVE_COUNT_UNIT_UNSPECIFIED", "TRADING_DATE"),
        "short_sale_buy": ("ShortSaleBuy", "SOURCE_NATIVE_COUNT_UNIT_UNSPECIFIED", "TRADING_DATE"),
        "short_sale_sell": ("ShortSaleSell", "SOURCE_NATIVE_COUNT_UNIT_UNSPECIFIED", "TRADING_DATE"),
        "short_sale_today_balance": ("ShortSaleTodayBalance", "SOURCE_NATIVE_COUNT_UNIT_UNSPECIFIED", "TRADING_DATE"),
    },
    "securities_lending": {
        "securities_lending_total_volume": ("total_volume", "SOURCE_NATIVE_VOLUME_UNIT_UNSPECIFIED", "TRADING_DATE"),
        "securities_lending_trade_count": ("trade_count", "COUNT", "TRADING_DATE"),
    },
    "shareholding": {
        "foreign_investment_shares": ("ForeignInvestmentShares", "SHARES", "TRADING_DATE"),
        "foreign_investment_shares_ratio": ("ForeignInvestmentSharesRatio", "PERCENT", "TRADING_DATE"),
        "foreign_investment_remaining_shares": ("ForeignInvestmentRemainingShares", "SHARES", "TRADING_DATE"),
        "foreign_investment_remaining_ratio": ("ForeignInvestmentRemainRatio", "PERCENT", "TRADING_DATE"),
        "shares_issued": ("NumberOfSharesIssued", "SHARES", "TRADING_DATE"),
    },
    "shareholding_concentration": {
        "shareholding_concentration": ("concentration", "PERCENT", "SOURCE_DEFINED_PERIOD"),
    },
    "news": {
        "target_news_provider_ready": ("target_news_provider_ready", "BOOLEAN", "AS_OF_CUTOFF"),
        "event_provider_ready": ("event_provider_ready", "BOOLEAN", "AS_OF_CUTOFF"),
    },
}


def _cutoff(as_of: datetime | str | pd.Timestamp | None) -> pd.Timestamp:
    ts = pd.Timestamp(as_of or datetime.now(timezone.utc))
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    return ts.tz_convert("UTC")


def _local_date(cutoff: pd.Timestamp) -> str:
    return cutoff.tz_convert(_TW_TZ).strftime("%Y-%m-%d")


def _safe_float(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) else None


def _row_hash(dataset: str, payload: Any) -> str:
    raw = json.dumps(
        {"dataset": dataset, "payload": payload},
        ensure_ascii=False,
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _filter_symbol(frame: pd.DataFrame, symbol: str) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()
    if "stock_id" not in frame.columns:
        return frame.copy()
    return frame[frame["stock_id"].astype(str).eq(symbol)].copy()


def _conservative_date_available_at(value: Any) -> pd.Timestamp | None:
    """Date-only source field -> next local midnight, never same-day midnight."""
    text = str(value or "").strip()
    if not text or text.lower() in {"nan", "none"}:
        return None
    try:
        day = pd.Timestamp(text[:10])
    except Exception:
        return None
    if day.tzinfo is None:
        day = day.tz_localize(_TW_TZ)
    else:
        day = day.tz_convert(_TW_TZ)
    return (day.normalize() + pd.Timedelta(days=1)).tz_convert("UTC")


def _announcement_available_at(date_value: Any, time_value: Any) -> pd.Timestamp | None:
    date_text = str(date_value or "").strip()
    time_text = str(time_value or "").strip()
    if not date_text or date_text.lower() in {"nan", "none"}:
        return None
    if not time_text or time_text.lower() in {"nan", "none"}:
        return _conservative_date_available_at(date_text)
    try:
        ts = pd.Timestamp(f"{date_text[:10]}T{time_text}")
    except Exception:
        return None
    if ts.tzinfo is None:
        ts = ts.tz_localize(_TW_TZ)
    else:
        ts = ts.tz_convert(_TW_TZ)
    return ts.tz_convert("UTC")


def _freshness(
    *,
    channel: str,
    available_at: pd.Timestamp | None,
    cutoff: pd.Timestamp,
) -> dict[str, Any]:
    if available_at is None:
        return {
            "status": "UNKNOWN",
            "age_hours": None,
            "policy_version": FRESHNESS_POLICY_VERSION,
            "basis": "PUBLICATION_TIME_UNAVAILABLE",
        }
    age_hours = max(0.0, (cutoff - available_at).total_seconds() / 3600.0)
    fresh, delayed = _FRESHNESS_HOURS[channel]
    if age_hours <= fresh:
        status = "FRESH"
    elif age_hours <= delayed:
        status = "DELAYED"
    else:
        status = "STALE"
    return {
        "status": status,
        "age_hours": age_hours,
        "policy_version": FRESHNESS_POLICY_VERSION,
        "basis": "CALENDAR_AGE_FROM_CONSERVATIVE_AVAILABLE_AT",
        "fresh_max_hours": fresh,
        "delayed_max_hours": delayed,
    }


def _base_channel(dataset: str, *, cadence: str) -> dict[str, Any]:
    return {
        "status": "NOT_AVAILABLE",
        "dataset": dataset,
        "provider": "FinMind",
        "source_tier": DATASET_TIER.get(dataset, "UNKNOWN"),
        "data_grade": DATA_GRADE,
        "cadence": cadence,
        "role": CONTEXT_ROLE,
        "pit_usable": False,
        "predictive_feature_eligible": False,
        "observation_date": None,
        "available_at": None,
        "availability_semantics": "UNAVAILABLE",
        "source_row_hash": None,
        "freshness": {
            "status": "UNKNOWN",
            "age_hours": None,
            "policy_version": FRESHNESS_POLICY_VERSION,
        },
    }


def _fetch(provider: FinMindProvider, dataset: str, symbol: str, start: str, end: str) -> pd.DataFrame:
    return _filter_symbol(provider.fetch_dataset(dataset, symbol, start, end), symbol)


def _valuation(provider: FinMindProvider, symbol: str, cutoff: pd.Timestamp) -> dict[str, Any]:
    out = _base_channel("TaiwanStockPER", cadence="TRADING_DAILY")
    start = (cutoff - pd.Timedelta(days=60)).strftime("%Y-%m-%d")
    end = _local_date(cutoff)
    try:
        frame = _fetch(provider, out["dataset"], symbol, start, end)
    except Exception as exc:
        out["status"] = "REQUEST_FAILED"
        out["reason"] = type(exc).__name__
        return out
    if frame.empty or "date" not in frame.columns:
        out["status"] = "EMPTY"
        return out

    work = frame.copy()
    work["_available_at"] = work["date"].map(_conservative_date_available_at)
    work = work[
        work["_available_at"].notna()
        & work["_available_at"].map(lambda x: pd.Timestamp(x) <= cutoff)
    ].copy()
    if work.empty:
        out["status"] = "NO_ASOF_ELIGIBLE_ROW"
        return out
    work["_date"] = pd.to_datetime(work["date"], errors="coerce")
    row = work.sort_values(["_date", "_available_at"]).iloc[-1]
    available_at = pd.Timestamp(row["_available_at"]).tz_convert("UTC")
    payload = {
        "date": str(row.get("date") or "")[:10],
        "PER": _safe_float(row.get("PER")),
        "PBR": _safe_float(row.get("PBR")),
        "dividend_yield": _safe_float(row.get("dividend_yield")),
    }
    out.update(
        {
            "status": "AVAILABLE",
            "pit_usable": True,
            "observation_date": payload["date"],
            "available_at": available_at.isoformat(),
            "availability_semantics": "SOURCE_DATE_PLUS_ONE_LOCAL_DAY_CONSERVATIVE",
            "source_row_hash": _row_hash(out["dataset"], payload),
            "values": {
                "pe_ratio": payload["PER"],
                "pbr": payload["PBR"],
                "dividend_yield": payload["dividend_yield"],
            },
            "freshness": _freshness(
                channel="valuation", available_at=available_at, cutoff=cutoff
            ),
        }
    )
    return out


def _monthly_revenue(
    provider: FinMindProvider,
    symbol: str,
    cutoff: pd.Timestamp,
) -> dict[str, Any]:
    out = _base_channel("TaiwanStockMonthRevenue", cadence="MONTHLY")
    start = (cutoff - pd.Timedelta(days=800)).strftime("%Y-%m-%d")
    end = _local_date(cutoff)
    try:
        frame = _fetch(provider, out["dataset"], symbol, start, end)
    except Exception as exc:
        out["status"] = "REQUEST_FAILED"
        out["reason"] = type(exc).__name__
        return out
    if frame.empty:
        out["status"] = "EMPTY"
        return out

    work = frame.copy()
    if "create_time" not in work.columns:
        if "date" not in work.columns:
            out["status"] = "AVAILABLE_NON_PIT_CONTEXT"
            out["availability_semantics"] = "CREATE_TIME_AND_PERIOD_DATE_MISSING"
            out["reason"] = "MONTH_REVENUE_CREATE_TIME_AND_PERIOD_DATE_MISSING"
            return out
        work["_date"] = pd.to_datetime(work["date"], errors="coerce")
        local_cutoff = cutoff.tz_convert(_TW_TZ).tz_localize(None)
        work = work[work["_date"].notna() & work["_date"].le(local_cutoff)].copy()
        if work.empty:
            out["status"] = "NO_ASOF_ELIGIBLE_ROW"
            out["availability_semantics"] = "CREATE_TIME_MISSING_PERIOD_DATE_CUTOFF_ONLY"
            return out
        row = work.sort_values("_date").iloc[-1]
        year = int(row["revenue_year"]) if pd.notna(row.get("revenue_year")) else None
        month = int(row["revenue_month"]) if pd.notna(row.get("revenue_month")) else None
        revenue = _safe_float(row.get("revenue"))
        payload = {
            "date": str(row.get("date") or "")[:10],
            "revenue_year": year,
            "revenue_month": month,
            "revenue": revenue,
        }
        out.update(
            {
                "status": "AVAILABLE_NON_PIT_CONTEXT",
                "observation_date": payload["date"],
                "availability_semantics": "CREATE_TIME_MISSING_PUBLICATION_TIME_UNKNOWN",
                "source_row_hash": _row_hash(out["dataset"], payload),
                "reason": "MONTH_REVENUE_CREATE_TIME_MISSING",
                "values": {
                    "revenue": revenue,
                    "revenue_year": year,
                    "revenue_month": month,
                    "mom_growth": None,
                    "yoy_growth": None,
                },
            }
        )
        return out

    work["_available_at"] = work["create_time"].map(_conservative_date_available_at)
    eligible = work[
        work["_available_at"].notna()
        & work["_available_at"].map(lambda x: pd.Timestamp(x) <= cutoff)
    ].copy()
    if eligible.empty:
        out["status"] = "NO_ASOF_ELIGIBLE_ROW"
        return out

    eligible["_available_at"] = eligible["_available_at"].map(pd.Timestamp)
    row = eligible.sort_values(["_available_at", "date"]).iloc[-1]
    available_at = pd.Timestamp(row["_available_at"]).tz_convert("UTC")
    year = int(row["revenue_year"]) if pd.notna(row.get("revenue_year")) else None
    month = int(row["revenue_month"]) if pd.notna(row.get("revenue_month")) else None
    revenue = _safe_float(row.get("revenue"))

    by_period: dict[tuple[int, int], float] = {}
    for rec in eligible.to_dict("records"):
        try:
            key = (int(rec["revenue_year"]), int(rec["revenue_month"]))
        except (TypeError, ValueError, KeyError):
            continue
        value = _safe_float(rec.get("revenue"))
        if value is not None:
            by_period[key] = value

    previous_month = None
    previous_year = None
    if year is not None and month is not None:
        prev_key = (year - 1, 12) if month == 1 else (year, month - 1)
        previous_month = by_period.get(prev_key)
        previous_year = by_period.get((year - 1, month))

    def growth(current: float | None, base: float | None) -> float | None:
        if current is None or base in (None, 0):
            return None
        return current / base - 1.0

    payload = {
        "date": str(row.get("date") or "")[:10],
        "create_time": str(row.get("create_time") or "")[:10],
        "revenue_year": year,
        "revenue_month": month,
        "revenue": revenue,
    }
    out.update(
        {
            "status": "AVAILABLE",
            "pit_usable": True,
            "observation_date": payload["date"],
            "available_at": available_at.isoformat(),
            "availability_semantics": "CREATE_DATE_PLUS_ONE_LOCAL_DAY_CONSERVATIVE",
            "source_row_hash": _row_hash(out["dataset"], payload),
            "values": {
                "revenue": revenue,
                "revenue_year": year,
                "revenue_month": month,
                "mom_growth": growth(revenue, previous_month),
                "yoy_growth": growth(revenue, previous_year),
            },
            "freshness": _freshness(
                channel="monthly_revenue", available_at=available_at, cutoff=cutoff
            ),
        }
    )
    return out


def _eps(provider: FinMindProvider, symbol: str, cutoff: pd.Timestamp) -> dict[str, Any]:
    out = _base_channel("TaiwanStockFinancialStatements", cadence="QUARTERLY")
    start = (cutoff - pd.Timedelta(days=900)).strftime("%Y-%m-%d")
    end = _local_date(cutoff)
    try:
        frame = _fetch(provider, out["dataset"], symbol, start, end)
    except Exception as exc:
        out["status"] = "REQUEST_FAILED"
        out["reason"] = type(exc).__name__
        return out
    if frame.empty or "type" not in frame.columns:
        out["status"] = "EMPTY"
        return out
    eps = frame[frame["type"].astype(str).eq("EPS")].copy()
    if "date" in eps.columns:
        eps["_date"] = pd.to_datetime(eps["date"], errors="coerce")
        local_cutoff = cutoff.tz_convert(_TW_TZ).tz_localize(None)
        eps = eps[eps["_date"].notna() & eps["_date"].le(local_cutoff)]
    if eps.empty:
        out["status"] = "EMPTY"
        return out
    row = eps.sort_values("_date" if "_date" in eps.columns else "date").iloc[-1]
    payload = {
        "date": str(row.get("date") or "")[:10],
        "type": "EPS",
        "value": _safe_float(row.get("value")),
        "origin_name": str(row.get("origin_name") or ""),
    }
    out.update(
        {
            "status": "AVAILABLE_NON_PIT_CONTEXT",
            "observation_date": payload["date"],
            "available_at": None,
            "availability_semantics": "PERIOD_END_ONLY_PUBLICATION_TIME_UNKNOWN",
            "source_row_hash": _row_hash(out["dataset"], payload),
            "reason": "FINANCIAL_STATEMENT_PUBLICATION_TIMESTAMP_NOT_IN_DATASET",
            "values": {
                "eps": payload["value"],
                "statement_label": payload["origin_name"],
            },
            "freshness": {
                "status": "UNKNOWN",
                "age_hours": None,
                "policy_version": FRESHNESS_POLICY_VERSION,
                "basis": "PUBLICATION_TIME_UNKNOWN_PERIOD_END_IS_NOT_AVAILABILITY",
            },
        }
    )
    return out


def _dividend_ex_right(
    provider: FinMindProvider,
    symbol: str,
    cutoff: pd.Timestamp,
) -> dict[str, Any]:
    out = _base_channel("TaiwanStockDividend", cadence="EVENT_DRIVEN")
    start = (cutoff - pd.Timedelta(days=900)).strftime("%Y-%m-%d")
    end = _local_date(cutoff)
    try:
        frame = _fetch(provider, out["dataset"], symbol, start, end)
    except Exception as exc:
        out["status"] = "REQUEST_FAILED"
        out["reason"] = type(exc).__name__
        return out
    if frame.empty:
        out["status"] = "EMPTY"
        return out
    required = {"AnnouncementDate"}
    missing = sorted(required - set(frame.columns))
    if missing:
        out["status"] = "AVAILABLE_NON_PIT_CONTEXT"
        out["reason"] = f"MISSING_ANNOUNCEMENT_COLUMNS:{','.join(missing)}"
        out["availability_semantics"] = "ANNOUNCEMENT_TIME_UNKNOWN_NOT_ASSUMED_KNOWN"
        return out

    work = frame.copy()
    announcement_time = (
        work["AnnouncementTime"]
        if "AnnouncementTime" in work.columns
        else pd.Series([None] * len(work), index=work.index)
    )
    work["_available_at"] = [
        _announcement_available_at(day, clock)
        for day, clock in zip(work["AnnouncementDate"], announcement_time)
    ]
    eligible = work[
        work["_available_at"].notna()
        & work["_available_at"].map(lambda x: pd.Timestamp(x) <= cutoff)
    ].copy()
    if eligible.empty:
        out["status"] = "NO_ASOF_ELIGIBLE_ROW"
        out["reason"] = "NO_ANNOUNCEMENT_KNOWN_BY_CUTOFF"
        return out
    eligible["_available_at"] = eligible["_available_at"].map(pd.Timestamp)
    row = eligible.sort_values("_available_at").iloc[-1]
    available_at = pd.Timestamp(row["_available_at"]).tz_convert("UTC")
    payload = {
        "AnnouncementDate": str(row.get("AnnouncementDate") or "")[:10],
        "AnnouncementTime": str(row.get("AnnouncementTime") or ""),
        "CashExDividendTradingDate": str(row.get("CashExDividendTradingDate") or "")[:10] or None,
        "StockExDividendTradingDate": str(row.get("StockExDividendTradingDate") or "")[:10] or None,
        "CashEarningsDistribution": _safe_float(row.get("CashEarningsDistribution")),
        "StockEarningsDistribution": _safe_float(row.get("StockEarningsDistribution")),
    }
    out.update(
        {
            "status": "AVAILABLE",
            "pit_usable": True,
            "observation_date": payload["AnnouncementDate"],
            "available_at": available_at.isoformat(),
            "published_at": available_at.isoformat(),
            "availability_semantics": (
                "ANNOUNCEMENT_TIME_IF_PRESENT_ELSE_ANNOUNCEMENT_DATE_PLUS_ONE_LOCAL_DAY"
            ),
            "source_row_hash": _row_hash(out["dataset"], payload),
            "values": payload,
            "freshness": {
                "status": "NOT_APPLICABLE_EVENT_CONTEXT",
                "age_hours": max(
                    0.0, (cutoff - available_at).total_seconds() / 3600.0
                ),
                "policy_version": FRESHNESS_POLICY_VERSION,
                "basis": "EVENT_ANNOUNCEMENT_AGE",
            },
            "normalization_contract": (
                "REFERENCE_RESET_NORMALIZATION_REMAINS_GOVERNED_BY_"
                "TAIWAN_STOCK_REFERENCE_RESET_CONTINUITY_V1"
            ),
        }
    )
    return out


def _institutional_flow(
    provider: FinMindProvider,
    symbol: str,
    cutoff: pd.Timestamp,
) -> dict[str, Any]:
    out = _base_channel(
        "TaiwanStockInstitutionalInvestorsBuySell", cadence="TRADING_DAILY"
    )
    start = (cutoff - pd.Timedelta(days=45)).strftime("%Y-%m-%d")
    end = _local_date(cutoff)
    try:
        frame = _fetch(provider, out["dataset"], symbol, start, end)
    except Exception as exc:
        out["status"] = "REQUEST_FAILED"
        out["reason"] = type(exc).__name__
        return out
    required = {"date", "name", "buy", "sell"}
    if frame.empty:
        out["status"] = "EMPTY"
        return out
    missing = sorted(required - set(frame.columns))
    if missing:
        out["status"] = "SCHEMA_INCOMPLETE"
        out["reason"] = f"MISSING_COLUMNS:{','.join(missing)}"
        return out

    work = frame.copy()
    work["_available_at"] = work["date"].map(_conservative_date_available_at)
    work = work[
        work["_available_at"].notna()
        & work["_available_at"].map(lambda x: pd.Timestamp(x) <= cutoff)
    ].copy()
    if work.empty:
        out["status"] = "NO_ASOF_ELIGIBLE_ROW"
        return out
    latest_date = work["date"].astype(str).max()
    latest = work[work["date"].astype(str).eq(latest_date)].copy()
    latest["buy"] = pd.to_numeric(latest["buy"], errors="coerce")
    latest["sell"] = pd.to_numeric(latest["sell"], errors="coerce")
    latest = latest[
        latest["name"].notna() & latest["buy"].notna() & latest["sell"].notna()
    ].copy()
    if latest.empty:
        out["status"] = "SCHEMA_INCOMPLETE"
        out["reason"] = "NO_VALID_INSTITUTION_ROWS"
        return out
    latest["net"] = latest["buy"] - latest["sell"]
    available_at = _conservative_date_available_at(latest_date)
    rows = [
        {
            "name": str(rec.get("name") or ""),
            "buy": float(rec.get("buy") or 0.0),
            "sell": float(rec.get("sell") or 0.0),
            "net": float(rec.get("net") or 0.0),
        }
        for rec in latest.sort_values("name").to_dict("records")
    ]
    total_net = float(sum(r["net"] for r in rows))
    by_name = {r["name"]: r["net"] for r in rows}
    dealer_net = float(
        sum(
            by_name.get(name, 0.0)
            for name in ("Dealer", "Dealer_self", "Dealer_Hedging")
        )
    )
    out.update(
        {
            "status": "AVAILABLE",
            "pit_usable": True,
            "observation_date": latest_date[:10],
            "available_at": available_at.isoformat() if available_at is not None else None,
            "availability_semantics": "SOURCE_DATE_PLUS_ONE_LOCAL_DAY_CONSERVATIVE",
            "source_row_hash": _row_hash(out["dataset"], rows),
            "values": {
                "total_net": total_net,
                "foreign_investor_net": float(by_name.get("Foreign_Investor", 0.0)),
                "investment_trust_net": float(by_name.get("Investment_Trust", 0.0)),
                "dealer_net": dealer_net,
                "foreign_dealer_self_net": float(by_name.get("Foreign_Dealer_Self", 0.0)),
                "by_institution": rows,
                "aggregation_semantics": (
                    "SUM_REPORTED_INSTITUTION_ROWS_SAME_DATE;"
                    "DEALER=Dealer+Dealer_self+Dealer_Hedging;"
                    "FOREIGN_DEALER_SELF_KEPT_SEPARATE"
                ),
            },
            "freshness": _freshness(
                channel="institutional_flow",
                available_at=available_at,
                cutoff=cutoff,
            ),
        }
    )
    return out


def _latest_daily_rows(
    frame: pd.DataFrame,
    cutoff: pd.Timestamp,
) -> tuple[str | None, pd.DataFrame, pd.Timestamp | None]:
    if frame.empty or "date" not in frame.columns:
        return None, pd.DataFrame(), None
    work = frame.copy()
    work["_available_at"] = work["date"].map(_conservative_date_available_at)
    work = work[
        work["_available_at"].notna()
        & work["_available_at"].map(lambda x: pd.Timestamp(x) <= cutoff)
    ].copy()
    if work.empty:
        return None, pd.DataFrame(), None
    latest_date = work["date"].astype(str).max()[:10]
    latest = work[work["date"].astype(str).str[:10].eq(latest_date)].copy()
    return latest_date, latest, _conservative_date_available_at(latest_date)


def _margin_short(
    provider: FinMindProvider,
    symbol: str,
    cutoff: pd.Timestamp,
) -> dict[str, Any]:
    out = _base_channel("TaiwanStockMarginPurchaseShortSale", cadence="TRADING_DAILY")
    start = (cutoff - pd.Timedelta(days=45)).strftime("%Y-%m-%d")
    end = _local_date(cutoff)
    try:
        frame = _fetch(provider, out["dataset"], symbol, start, end)
    except Exception as exc:
        out["status"] = "REQUEST_FAILED"
        out["reason"] = type(exc).__name__
        return out
    required = {
        "date",
        "MarginPurchaseBuy",
        "MarginPurchaseSell",
        "MarginPurchaseTodayBalance",
        "ShortSaleBuy",
        "ShortSaleSell",
        "ShortSaleTodayBalance",
    }
    if frame.empty:
        out["status"] = "EMPTY"
        return out
    missing = sorted(required - set(frame.columns))
    if missing:
        out["status"] = "SCHEMA_INCOMPLETE"
        out["reason"] = f"MISSING_COLUMNS:{','.join(missing)}"
        return out
    latest_date, latest, available_at = _latest_daily_rows(frame, cutoff)
    if latest.empty or latest_date is None:
        out["status"] = "NO_ASOF_ELIGIBLE_ROW"
        return out
    row = latest.sort_values("date").iloc[-1]
    values = {
        key: _safe_float(row.get(key))
        for key in (
            "MarginPurchaseBuy",
            "MarginPurchaseCashRepayment",
            "MarginPurchaseLimit",
            "MarginPurchaseSell",
            "MarginPurchaseTodayBalance",
            "MarginPurchaseYesterdayBalance",
            "OffsetLoanAndShort",
            "ShortSaleBuy",
            "ShortSaleCashRepayment",
            "ShortSaleLimit",
            "ShortSaleSell",
            "ShortSaleTodayBalance",
            "ShortSaleYesterdayBalance",
        )
    }
    payload = {"date": latest_date, **values}
    out.update(
        {
            "status": "AVAILABLE",
            "pit_usable": True,
            "observation_date": latest_date,
            "available_at": available_at.isoformat() if available_at is not None else None,
            "availability_semantics": "SOURCE_DATE_PLUS_ONE_LOCAL_DAY_CONSERVATIVE",
            "source_row_hash": _row_hash(out["dataset"], payload),
            "values": values,
            "freshness": _freshness(
                channel="margin_short", available_at=available_at, cutoff=cutoff
            ),
            "unit_semantics": (
                "FINMIND_SCHEMA_DOES_NOT_DECLARE_COUNT_UNIT;"
                "VALUES_PRESERVED_IN_SOURCE_NATIVE_COUNTS"
            ),
        }
    )
    return out


def _securities_lending(
    provider: FinMindProvider,
    symbol: str,
    cutoff: pd.Timestamp,
) -> dict[str, Any]:
    out = _base_channel("TaiwanStockSecuritiesLending", cadence="TRADING_DAILY")
    start = (cutoff - pd.Timedelta(days=45)).strftime("%Y-%m-%d")
    end = _local_date(cutoff)
    try:
        frame = _fetch(provider, out["dataset"], symbol, start, end)
    except Exception as exc:
        out["status"] = "REQUEST_FAILED"
        out["reason"] = type(exc).__name__
        return out
    required = {"date", "transaction_type", "volume", "fee_rate"}
    if frame.empty:
        out["status"] = "EMPTY"
        return out
    missing = sorted(required - set(frame.columns))
    if missing:
        out["status"] = "SCHEMA_INCOMPLETE"
        out["reason"] = f"MISSING_COLUMNS:{','.join(missing)}"
        return out
    latest_date, latest, available_at = _latest_daily_rows(frame, cutoff)
    if latest.empty or latest_date is None:
        out["status"] = "NO_ASOF_ELIGIBLE_ROW"
        return out
    latest["volume"] = pd.to_numeric(latest["volume"], errors="coerce")
    latest["fee_rate"] = pd.to_numeric(latest["fee_rate"], errors="coerce")
    latest = latest[
        latest["transaction_type"].notna() & latest["volume"].notna()
    ].copy()
    if latest.empty:
        out["status"] = "SCHEMA_INCOMPLETE"
        out["reason"] = "NO_VALID_SECURITIES_LENDING_ROWS"
        return out
    rows = [
        {
            "transaction_type": str(rec.get("transaction_type") or ""),
            "volume": float(rec["volume"]),
            "fee_rate": _safe_float(rec.get("fee_rate")),
            "close": _safe_float(rec.get("close")),
            "original_return_date": str(rec.get("original_return_date") or ""),
            "original_lending_period": _safe_float(rec.get("original_lending_period")),
        }
        for rec in latest.sort_values(["transaction_type", "volume"]).to_dict("records")
    ]
    by_type: dict[str, float] = {}
    for row in rows:
        by_type[row["transaction_type"]] = by_type.get(row["transaction_type"], 0.0) + row["volume"]
    total_volume = float(sum(row["volume"] for row in rows))
    out.update(
        {
            "status": "AVAILABLE",
            "pit_usable": True,
            "observation_date": latest_date,
            "available_at": available_at.isoformat() if available_at is not None else None,
            "availability_semantics": "SOURCE_DATE_PLUS_ONE_LOCAL_DAY_CONSERVATIVE",
            "source_row_hash": _row_hash(out["dataset"], rows),
            "values": {
                "total_volume": total_volume,
                "trade_count": len(rows),
                "volume_by_transaction_type": by_type,
                "transactions": rows,
                "fee_rate_aggregation": "NONE_SOURCE_ROWS_PRESERVED",
            },
            "freshness": _freshness(
                channel="securities_lending", available_at=available_at, cutoff=cutoff
            ),
            "unit_semantics": (
                "FINMIND_SCHEMA_LABELS_VOLUME_BUT_DOES_NOT_DECLARE_UNIT;"
                "SOURCE_NATIVE_VOLUME_PRESERVED"
            ),
        }
    )
    return out


def _shareholding(
    provider: FinMindProvider,
    symbol: str,
    cutoff: pd.Timestamp,
) -> dict[str, Any]:
    out = _base_channel("TaiwanStockShareholding", cadence="TRADING_DAILY")
    start = (cutoff - pd.Timedelta(days=45)).strftime("%Y-%m-%d")
    end = _local_date(cutoff)
    try:
        frame = _fetch(provider, out["dataset"], symbol, start, end)
    except Exception as exc:
        out["status"] = "REQUEST_FAILED"
        out["reason"] = type(exc).__name__
        return out
    required = {
        "date",
        "ForeignInvestmentRemainingShares",
        "ForeignInvestmentShares",
        "ForeignInvestmentRemainRatio",
        "ForeignInvestmentSharesRatio",
        "NumberOfSharesIssued",
    }
    if frame.empty:
        out["status"] = "EMPTY"
        return out
    missing = sorted(required - set(frame.columns))
    if missing:
        out["status"] = "SCHEMA_INCOMPLETE"
        out["reason"] = f"MISSING_COLUMNS:{','.join(missing)}"
        return out
    latest_date, latest, available_at = _latest_daily_rows(frame, cutoff)
    if latest.empty or latest_date is None:
        out["status"] = "NO_ASOF_ELIGIBLE_ROW"
        return out
    row = latest.sort_values("date").iloc[-1]
    values = {
        key: _safe_float(row.get(key))
        for key in (
            "ForeignInvestmentRemainingShares",
            "ForeignInvestmentShares",
            "ForeignInvestmentRemainRatio",
            "ForeignInvestmentSharesRatio",
            "ForeignInvestmentUpperLimitRatio",
            "ChineseInvestmentUpperLimitRatio",
            "NumberOfSharesIssued",
        )
    }
    values["RecentlyDeclareDate"] = str(row.get("RecentlyDeclareDate") or "")[:10] or None
    payload = {"date": latest_date, **values}
    out.update(
        {
            "status": "AVAILABLE",
            "pit_usable": True,
            "observation_date": latest_date,
            "available_at": available_at.isoformat() if available_at is not None else None,
            "availability_semantics": "SOURCE_DATE_PLUS_ONE_LOCAL_DAY_CONSERVATIVE",
            "source_row_hash": _row_hash(out["dataset"], payload),
            "values": values,
            "freshness": _freshness(
                channel="shareholding", available_at=available_at, cutoff=cutoff
            ),
        }
    )
    return out


def _shareholding_concentration_channel() -> dict[str, Any]:
    out = _base_channel("TaiwanStockHoldingSharesPer", cadence="WEEKLY_OR_SOURCE_DEFINED")
    out.update(
        {
            "status": "NOT_AVAILABLE_FREE_TIER",
            "source_tier": "BACKER_OR_SPONSOR_REQUIRED",
            "availability_semantics": "NOT_QUERIED_NON_FREE_RESOURCE",
            "reason": "FINMIND_HOLDING_SHARES_PER_REQUIRES_PAID_MEMBERSHIP",
            "values": {"concentration": None},
        }
    )
    return out


def _news_channel() -> dict[str, Any]:
    return {
        "status": "NOT_AVAILABLE",
        "dataset": None,
        "provider": None,
        "source_tier": None,
        "data_grade": None,
        "cadence": "EVENT_DRIVEN",
        "role": CONTEXT_ROLE,
        "pit_usable": False,
        "predictive_feature_eligible": False,
        "observation_date": None,
        "available_at": None,
        "availability_semantics": "NO_VERIFIED_SOURCE",
        "source_row_hash": None,
        "freshness": {
            "status": "UNKNOWN",
            "age_hours": None,
            "policy_version": FRESHNESS_POLICY_VERSION,
        },
        "reason": "NO_VERIFIED_TARGET_SPECIFIC_FREE_NEWS_PROVIDER_IN_REPO",
        "generic_web_news_fallback_allowed": False,
        "news_sentiment_probability_allowed": False,
        "values": {
            "target_news_provider_ready": False,
            "event_provider_ready": False,
        },
    }


def reconcile_context_factor_candidates(
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    """Reconcile already-normalized candidates without averaging semantic conflicts."""
    kept = [dict(candidate) for candidate in candidates if candidate]
    if not kept:
        return {
            "status": "MISSING",
            "reason": "NO_CANDIDATES",
            "selected": None,
            "candidates": [],
            "aggregation": "NONE",
        }
    factor_ids = {str(candidate.get("factor_id") or "") for candidate in kept}
    if len(factor_ids) != 1:
        return {
            "status": "CONFLICT",
            "reason": "FACTOR_ID_MISMATCH",
            "selected": None,
            "candidates": kept,
            "aggregation": "NONE",
        }
    units = {str(candidate.get("units") or "") for candidate in kept}
    if len(units) != 1:
        return {
            "status": "CONFLICT",
            "reason": "UNIT_MISMATCH",
            "selected": None,
            "candidates": kept,
            "aggregation": "NONE",
        }
    periods = {str(candidate.get("observation_period") or "") for candidate in kept}
    if len(periods) != 1:
        return {
            "status": "CONFLICT",
            "reason": "PERIOD_MISMATCH",
            "selected": None,
            "candidates": kept,
            "aggregation": "NONE",
        }
    values = {
        json.dumps(candidate.get("value"), sort_keys=True, default=str)
        for candidate in kept
    }
    if len(values) != 1:
        return {
            "status": "CONFLICT",
            "reason": "SOURCE_DISAGREEMENT",
            "selected": None,
            "candidates": kept,
            "aggregation": "NONE",
        }
    selected = min(
        kept,
        key=lambda candidate: (
            int(candidate.get("source_priority_rank", 9999)),
            str(candidate.get("source") or ""),
        ),
    )
    return {
        "status": "SELECTED",
        "reason": "SEMANTICALLY_COMPATIBLE_EQUAL_VALUE",
        "selected": selected,
        "candidates": kept,
        "aggregation": "NONE",
    }


def _factor_observation_period(channel_name: str, channel: dict[str, Any]) -> str | None:
    values = dict(channel.get("values") or {})
    if channel_name == "monthly_revenue":
        year = values.get("revenue_year")
        month = values.get("revenue_month")
        if year is not None and month is not None:
            return f"{int(year):04d}-{int(month):02d}"
    if channel_name == "eps":
        raw = str(channel.get("observation_date") or "")
        try:
            ts = pd.Timestamp(raw)
        except Exception:
            return raw or None
        return f"{ts.year:04d}-Q{((ts.month - 1) // 3) + 1}"
    return str(channel.get("observation_date") or "") or None


def _decorate_channel(
    channel_name: str,
    channel: dict[str, Any],
    *,
    cutoff: pd.Timestamp,
    retrieved_at: pd.Timestamp,
) -> dict[str, Any]:
    out = dict(channel)
    values = dict(out.get("values") or {})
    available_at_raw = out.get("available_at")
    available_at = pd.Timestamp(available_at_raw) if available_at_raw else None
    if available_at is not None and available_at.tzinfo is None:
        available_at = available_at.tz_localize("UTC")
    if available_at is not None:
        available_at = available_at.tz_convert("UTC")
    freshness = dict(out.get("freshness") or {})
    age_hours = freshness.get("age_hours")
    age_seconds = float(age_hours) * 3600.0 if age_hours is not None else None
    pit_eligible = bool(
        out.get("pit_usable") is True
        and available_at is not None
        and available_at <= cutoff
    )
    missing_reason = None
    if not str(out.get("status") or "").startswith("AVAILABLE"):
        missing_reason = str(out.get("reason") or out.get("status") or "NOT_AVAILABLE")
    elif not pit_eligible:
        missing_reason = str(out.get("reason") or "PUBLICATION_TIME_NOT_PIT_VERIFIED")
    out.update(
        {
            "source": out.get("provider"),
            "source_dataset": out.get("dataset"),
            "source_endpoint": _FINMIND_ENDPOINT if out.get("provider") == "FinMind" else None,
            "published_at": out.get("published_at"),
            "retrieved_at": retrieved_at.isoformat(),
            "cutoff": cutoff.isoformat(),
            "freshness_seconds": age_seconds,
            "freshness_days": age_seconds / 86400.0 if age_seconds is not None else None,
            "freshness_status": freshness.get("status", "UNKNOWN"),
            "PIT_eligible": pit_eligible,
            "predictive_feature_allowed": False,
            "missing_reason": missing_reason,
            "provenance_hash": out.get("source_row_hash"),
        }
    )
    factor_specs = _FACTOR_SPECS.get(channel_name, {})
    observation_period = _factor_observation_period(channel_name, out)
    factors: dict[str, dict[str, Any]] = {}
    for factor_id, (value_key, units, period_semantics) in factor_specs.items():
        value = values.get(value_key)
        factor_missing_reason = missing_reason
        if value is None and factor_missing_reason is None:
            factor_missing_reason = "VALUE_NOT_AVAILABLE_IN_SOURCE_WINDOW"
        factors[factor_id] = {
            "factor_id": factor_id,
            "value": value,
            "units": units,
            "observation_period": observation_period,
            "observation_period_semantics": period_semantics,
            "source": out.get("provider"),
            "source_dataset": out.get("dataset"),
            "source_endpoint": out.get("source_endpoint"),
            "published_at": out.get("published_at"),
            "available_at": out.get("available_at"),
            "retrieved_at": retrieved_at.isoformat(),
            "cutoff": cutoff.isoformat(),
            "freshness_seconds": age_seconds,
            "freshness_days": age_seconds / 86400.0 if age_seconds is not None else None,
            "freshness_status": freshness.get("status", "UNKNOWN"),
            "PIT_eligible": pit_eligible,
            "predictive_feature_allowed": False,
            "missing_reason": factor_missing_reason,
            "provenance_hash": out.get("source_row_hash"),
            "availability_semantics": out.get("availability_semantics"),
            "source_priority_rank": 20 if out.get("provider") == "FinMind" else 9999,
            "reconciliation_status": "SINGLE_SOURCE_NO_AVERAGING",
        }
    out["factors"] = factors
    return out


def build_taiwan_stock_context(
    symbol: str,
    *,
    as_of: datetime | str | pd.Timestamp | None = None,
    finmind: FinMindProvider | None = None,
) -> dict[str, Any]:
    """Build a bounded target-context snapshot without feeding forecast models."""
    stock_id = normalize_taiwan_symbol(symbol)
    cutoff = _cutoff(as_of)
    retrieved_at = pd.Timestamp(datetime.now(timezone.utc)).tz_convert("UTC")
    provider = finmind or FinMindProvider()

    channels = {
        "valuation": _valuation(provider, stock_id, cutoff),
        "monthly_revenue": _monthly_revenue(provider, stock_id, cutoff),
        "eps": _eps(provider, stock_id, cutoff),
        "dividend_ex_right": _dividend_ex_right(provider, stock_id, cutoff),
        "institutional_flow": _institutional_flow(provider, stock_id, cutoff),
        "margin_short": _margin_short(provider, stock_id, cutoff),
        "securities_lending": _securities_lending(provider, stock_id, cutoff),
        "shareholding": _shareholding(provider, stock_id, cutoff),
        "shareholding_concentration": _shareholding_concentration_channel(),
        "news": _news_channel(),
    }
    channels = {
        name: _decorate_channel(
            name,
            channel,
            cutoff=cutoff,
            retrieved_at=retrieved_at,
        )
        for name, channel in channels.items()
    }
    available = [
        name
        for name, channel in channels.items()
        if str(channel.get("status") or "").startswith("AVAILABLE")
    ]
    pit_usable = [
        name for name, channel in channels.items() if channel.get("pit_usable") is True
    ]
    unavailable = [name for name in channels if name not in available]
    nonpit = [
        name for name, channel in channels.items() if channel.get("pit_usable") is not True
    ]
    missing_or_nonpit = sorted(set(unavailable) | set(nonpit))

    return {
        "schema_version": CONTEXT_SCHEMA_VERSION,
        "source_semantics_version": SOURCE_SEMANTICS_VERSION,
        "freshness_policy_version": FRESHNESS_POLICY_VERSION,
        "symbol": symbol,
        "stock_id": stock_id,
        "as_of": cutoff.isoformat(),
        "cutoff": cutoff.isoformat(),
        "retrieved_at": retrieved_at.isoformat(),
        "role": CONTEXT_ROLE,
        "predictive_feature_eligible": False,
        "predictive_feature_allowed": False,
        "historical_revision_safe": False,
        "historical_revision_note": (
            "live vendor retrieval has no immutable historical receipt snapshot; "
            "current context does not authorize backtest/model-feature use"
        ),
        "source_reconciliation": {
            "version": SOURCE_RECONCILIATION_VERSION,
            "policy": "PRESERVE_CONFLICTS_NEVER_AVERAGE",
            "active_context_source": "FinMind",
            "active_context_source_reason": (
                "repo FinMind provider exposes the target-scoped free datasets used here"
            ),
            "twse_official_direct_context_status": (
                "PROVIDER_EXISTS_BUT_CONTEXT_ENDPOINTS_NOT_WIRED_IN_REPO"
            ),
            "research_proxy_fallback_allowed": False,
            "generic_web_fallback_allowed": False,
        },
        "channels": channels,
        "coverage": {
            "status": "AVAILABLE" if len(available) == len(channels) else "PARTIAL",
            "available_channels": available,
            "pit_usable_channels": pit_usable,
            "unavailable_channels": unavailable,
            "nonpit_channels": nonpit,
            "missing_or_nonpit_channels": missing_or_nonpit,
            "channel_count": len(channels),
            "available_count": len(available),
            "pit_usable_count": len(pit_usable),
            "context_data_ready": bool(available),
            "predictive_experiment_data_ready": False,
        },
        "validation_claims": {
            "PREDICTIVE_GAIN": False,
            "CALIBRATED": False,
            "TRADING_EDGE": False,
            "result_role": CONTEXT_ROLE,
        },
    }
