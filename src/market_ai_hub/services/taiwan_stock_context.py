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

CONTEXT_SCHEMA_VERSION = "TAIWAN_STOCK_CONTEXT_V1"
SOURCE_SEMANTICS_VERSION = "FINMIND_FREE_TARGET_CONTEXT_ASOF_V1"
FRESHNESS_POLICY_VERSION = "TAIWAN_STOCK_CONTEXT_FRESHNESS_V1"
CONTEXT_ROLE = "TARGET_CONTEXT_ONLY_NOT_PREDICTIVE_FEATURE"
DATA_GRADE = "RESEARCH_CONTEXT_VENDOR_AGGREGATE"
_TW_TZ = "Asia/Taipei"

_FRESHNESS_HOURS = {
    "valuation": (96.0, 168.0),
    "monthly_revenue": (45.0 * 24.0, 75.0 * 24.0),
    "institutional_flow": (96.0, 168.0),
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
        out.update(
            {
                "status": "AVAILABLE_NON_PIT_CONTEXT",
                "observation_date": str(row.get("date") or "")[:10],
                "availability_semantics": "CREATE_TIME_MISSING_PUBLICATION_TIME_UNKNOWN",
                "reason": "MONTH_REVENUE_CREATE_TIME_MISSING",
                "values": {"revenue": _safe_float(row.get("revenue"))},
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
    latest_date = work["date"].astype(str).max()
    latest = work[work["date"].astype(str).eq(latest_date)].copy()
    latest["buy"] = pd.to_numeric(latest.get("buy"), errors="coerce").fillna(0.0)
    latest["sell"] = pd.to_numeric(latest.get("sell"), errors="coerce").fillna(0.0)
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
                "by_institution": rows,
                "aggregation_semantics": "SUM_REPORTED_INSTITUTION_ROWS_SAME_DATE",
            },
            "freshness": _freshness(
                channel="institutional_flow",
                available_at=available_at,
                cutoff=cutoff,
            ),
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
    }


def build_taiwan_stock_context(
    symbol: str,
    *,
    as_of: datetime | str | pd.Timestamp | None = None,
    finmind: FinMindProvider | None = None,
) -> dict[str, Any]:
    """Build a bounded target-context snapshot without feeding forecast models."""
    stock_id = normalize_taiwan_symbol(symbol)
    cutoff = _cutoff(as_of)
    provider = finmind or FinMindProvider()

    channels = {
        "valuation": _valuation(provider, stock_id, cutoff),
        "monthly_revenue": _monthly_revenue(provider, stock_id, cutoff),
        "eps": _eps(provider, stock_id, cutoff),
        "institutional_flow": _institutional_flow(provider, stock_id, cutoff),
        "news": _news_channel(),
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
        "role": CONTEXT_ROLE,
        "predictive_feature_eligible": False,
        "historical_revision_safe": False,
        "historical_revision_note": (
            "live vendor retrieval has no immutable historical receipt snapshot; "
            "current context does not authorize backtest/model-feature use"
        ),
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
