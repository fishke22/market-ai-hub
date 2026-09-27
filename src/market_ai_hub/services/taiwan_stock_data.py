"""PIT-safe Taiwan-stock price normalization and model-data identity.

The production/inference contract deliberately does not silently substitute raw
OHLC for an adjusted series.  When vendor adjusted prices are unavailable we
construct a forward-continuity series from raw daily prices plus explicit
reference-reset events.  Applying each factor only from its effective date
forward keeps pre-event features unchanged, while removing the mechanical price
reset from returns/labels.

This is a data-correctness layer, not a predictive feature.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from typing import Any

import numpy as np
import pandas as pd

from market_ai_hub.providers.base import ProviderError, ProviderStatus
from market_ai_hub.providers.finmind import FinMindProvider
from market_ai_hub.providers.twse import TWSEProvider


DATASET_SEMANTICS = "TAIWAN_STOCK_REFERENCE_RESET_CONTINUITY_V1"
ADJUSTMENT_SEMANTICS = "FORWARD_EFFECTIVE_DATE_REFERENCE_RESET_V1"
SOURCE_SEMANTICS = "RAW_DAILY_PLUS_FINMIND_REFERENCE_EVENTS_V1"
FEATURE_VERSION = "base-v1"
ADJUSTMENT_STATUS_OK = "CORPORATE_ACTION_NORMALIZED"
ADJUSTMENT_STATUS_BLOCKED = "CORPORATE_ACTION_ADJUSTMENT_UNAVAILABLE"
_UNEXPLAINED_JUMP_LIMIT = 0.12


class TaiwanStockDataIntegrityError(RuntimeError):
    def __init__(self, reason: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(reason)
        self.reason = reason
        self.details = dict(details or {})


@dataclass
class TaiwanStockModelData:
    frame: pd.DataFrame
    raw_frame: pd.DataFrame
    metadata: dict[str, Any]

    @property
    def current_adjustment_factor(self) -> float:
        return float(self.metadata.get("current_adjustment_factor") or 1.0)


def normalize_taiwan_symbol(symbol: str) -> str:
    text = str(symbol or "").strip().upper()
    if text.endswith(".TW"):
        text = text[:-3]
    return text


def is_taiwan_stock_symbol(symbol: str) -> bool:
    text = str(symbol or "").strip().upper()
    base = normalize_taiwan_symbol(text)
    return text.endswith(".TW") or (base.isdigit() and 4 <= len(base) <= 6)


def period_window(period: str, *, now: datetime | None = None) -> tuple[str, str]:
    """Map common yfinance-like periods to an explicit calendar window."""
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    text = str(period or "1y").strip().lower()
    if text == "ytd":
        start = now.replace(month=1, day=1)
    else:
        units = {"d": 1, "wk": 7, "mo": 31, "y": 366}
        value = None
        unit = None
        for suffix in ("wk", "mo", "y", "d"):
            if text.endswith(suffix):
                try:
                    value = int(text[: -len(suffix)])
                except ValueError:
                    value = None
                unit = suffix
                break
        if value is None or unit is None or value <= 0:
            raise ValueError(f"unsupported period for Taiwan stock data: {period}")
        start = now - timedelta(days=value * units[unit])
    return start.strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d")


def _row_hash(dataset: str, row: dict[str, Any]) -> str:
    payload = json.dumps(
        {"dataset": dataset, "row": row},
        ensure_ascii=False,
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _finite_positive(value: Any) -> float | None:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if math.isfinite(out) and out > 0 else None


def _first_positive(*values: Any) -> float | None:
    for value in values:
        out = _finite_positive(value)
        if out is not None:
            return out
    return None


def _event(
    *,
    dataset: str,
    row: dict[str, Any],
    event_type: str,
    event_date: str,
    before: Any,
    reference: Any,
    announcement_at: str | None = None,
) -> dict[str, Any] | None:
    before_f = _finite_positive(before)
    reference_f = _finite_positive(reference)
    if not event_date or before_f is None or reference_f is None:
        return None
    factor = before_f / reference_f
    if not math.isfinite(factor) or factor <= 0:
        return None
    return {
        "event_type": event_type,
        "event_date": str(event_date)[:10],
        "announcement_at": announcement_at,
        # For normalization only, effective date is a conservative availability
        # boundary when no separate publication timestamp exists.  This field is
        # never exposed as a predictive feature.
        "available_at": announcement_at or str(event_date)[:10],
        "available_at_semantics": (
            "ANNOUNCEMENT_TIME"
            if announcement_at
            else "EFFECTIVE_DATE_BOUNDARY_ONLY_NOT_PREDICTIVE_FEATURE"
        ),
        "before_price": before_f,
        "reference_price": reference_f,
        "adjustment_factor": factor,
        "source": f"FinMind:{dataset}",
        "source_hash": _row_hash(dataset, row),
        "adjustment_method": "FORWARD_MULTIPLY_FROM_EFFECTIVE_DATE",
        "adjustment_status": "VERIFIED_REFERENCE_RESET",
        "usable_as_predictive_feature": False,
    }


def _announcement_map(dividend: pd.DataFrame) -> dict[str, str]:
    out: dict[str, str] = {}
    if dividend is None or dividend.empty:
        return out
    for row in dividend.to_dict("records"):
        date = str(row.get("AnnouncementDate") or "").strip()
        clock = str(row.get("AnnouncementTime") or "").strip()
        announced = date
        if date and clock and clock.lower() not in {"nan", "none"}:
            announced = f"{date}T{clock}"
        for key in ("CashExDividendTradingDate", "StockExDividendTradingDate"):
            ex_date = str(row.get(key) or "").strip()
            if ex_date and ex_date.lower() not in {"nan", "none"} and announced:
                out[ex_date[:10]] = announced
    return out


def _filter_symbol(frame: pd.DataFrame, symbol: str) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()
    if "stock_id" not in frame.columns:
        return frame.copy()
    return frame[frame["stock_id"].astype(str).eq(symbol)].copy()


def _fetch_reference_events(
    provider: FinMindProvider,
    symbol: str,
    start_date: str,
    end_date: str,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Fetch all known free reference-reset channels; any channel error blocks."""
    channel_specs = [
        ("TaiwanStockDividendResult", True),
        ("TaiwanStockCapitalReductionReferencePrice", True),
        ("TaiwanStockSplitPrice", False),
        ("TaiwanStockParValueChange", False),
    ]
    channels: dict[str, Any] = {}
    frames: dict[str, pd.DataFrame] = {}
    errors: dict[str, str] = {}
    for dataset, use_data_id in channel_specs:
        try:
            frame = provider.fetch_dataset(
                dataset,
                symbol if use_data_id else "",
                start_date,
                end_date,
            )
            frame = _filter_symbol(frame, symbol)
            frames[dataset] = frame
            channels[dataset] = {"status": "AVAILABLE", "row_count": int(len(frame))}
        except Exception as exc:
            errors[dataset] = f"{type(exc).__name__}: {str(exc)[:160]}"
            channels[dataset] = {"status": "REQUEST_FAILED", "row_count": None}

    # Dividend policy is metadata only: it improves announcement_at provenance,
    # but a failure does not invalidate the effective-date price normalization.
    try:
        dividend = provider.fetch_dataset(
            "TaiwanStockDividend", symbol, start_date, end_date
        )
        dividend = _filter_symbol(dividend, symbol)
        channels["TaiwanStockDividend"] = {
            "status": "AVAILABLE",
            "row_count": int(len(dividend)),
        }
    except Exception as exc:
        dividend = pd.DataFrame()
        channels["TaiwanStockDividend"] = {
            "status": "REQUEST_FAILED_OPTIONAL_METADATA",
            "row_count": None,
            "error": f"{type(exc).__name__}: {str(exc)[:160]}",
        }

    if errors:
        raise TaiwanStockDataIntegrityError(
            "CORPORATE_ACTION_REFERENCE_CHANNEL_INCOMPLETE",
            details={"channels": channels, "errors": errors},
        )

    announcement_by_ex_date = _announcement_map(dividend)
    events: list[dict[str, Any]] = []

    for row in frames["TaiwanStockDividendResult"].to_dict("records"):
        event_date = str(row.get("date") or "")[:10]
        label = str(row.get("stock_or_cache_dividend") or "DIVIDEND_OR_RIGHTS")
        item = _event(
            dataset="TaiwanStockDividendResult",
            row=row,
            event_type=f"EX_RIGHT_DIVIDEND:{label}",
            event_date=event_date,
            before=row.get("before_price"),
            reference=_first_positive(
                row.get("reference_price"),
                row.get("after_price"),
            ),
            announcement_at=announcement_by_ex_date.get(event_date),
        )
        if item:
            events.append(item)

    for row in frames["TaiwanStockCapitalReductionReferencePrice"].to_dict("records"):
        item = _event(
            dataset="TaiwanStockCapitalReductionReferencePrice",
            row=row,
            event_type=f"CAPITAL_REDUCTION:{row.get('ReasonforCapitalReduction') or ''}",
            event_date=str(row.get("date") or "")[:10],
            before=row.get("ClosingPriceonTheLastTradingDay"),
            reference=_first_positive(
                row.get("OpeningReferencePrice"),
                row.get("PostReductionReferencePrice"),
                row.get("ExrightReferencePrice"),
            ),
        )
        if item:
            events.append(item)

    for row in frames["TaiwanStockSplitPrice"].to_dict("records"):
        item = _event(
            dataset="TaiwanStockSplitPrice",
            row=row,
            event_type=f"STOCK_{str(row.get('type') or 'SPLIT').upper()}",
            event_date=str(row.get("date") or "")[:10],
            before=row.get("before_price"),
            reference=row.get("after_price"),
        )
        if item:
            events.append(item)

    for row in frames["TaiwanStockParValueChange"].to_dict("records"):
        item = _event(
            dataset="TaiwanStockParValueChange",
            row=row,
            event_type="PAR_VALUE_CHANGE",
            event_date=str(row.get("date") or "")[:10],
            before=row.get("before_close"),
            reference=row.get("after_ref_close"),
        )
        if item:
            events.append(item)

    events.sort(key=lambda x: (x["event_date"], x["source"]))
    return events, channels


def apply_reference_resets(
    raw_frame: pd.DataFrame,
    events: list[dict[str, Any]],
) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    """Return a forward-continuity OHLC series and deduplicated event ledger."""
    if raw_frame is None or raw_frame.empty:
        raise TaiwanStockDataIntegrityError("RAW_PRICE_EMPTY")
    work = raw_frame.copy().sort_values("timestamp_utc").reset_index(drop=True)
    local_dates = pd.to_datetime(work["timestamp_local"]).dt.strftime("%Y-%m-%d")

    # Multiple sources on one effective date may describe the same reset.  Never
    # multiply twice.  If their factors disagree materially, fail closed.
    by_date: dict[str, list[dict[str, Any]]] = {}
    for event in events:
        by_date.setdefault(str(event["event_date"]), []).append(event)

    ledger: list[dict[str, Any]] = []
    scale_by_date: dict[str, float] = {}
    for event_date, rows in sorted(by_date.items()):
        factors = [float(r["adjustment_factor"]) for r in rows]
        if max(factors) - min(factors) > 1e-6:
            raise TaiwanStockDataIntegrityError(
                "AMBIGUOUS_MULTIPLE_REFERENCE_RESETS",
                details={"event_date": event_date, "events": rows},
            )
        merged = dict(rows[0])
        merged["source_records"] = [
            {"source": r["source"], "source_hash": r["source_hash"], "event_type": r["event_type"]}
            for r in rows
        ]
        merged["event_types"] = sorted({r["event_type"] for r in rows})
        ledger.append(merged)
        scale_by_date[event_date] = factors[0]

    cumulative = 1.0
    factors: list[float] = []
    known_event_dates = set(scale_by_date)
    for date in local_dates:
        if date in scale_by_date:
            cumulative *= scale_by_date[date]
        factors.append(cumulative)

    for col in ("open", "high", "low", "close"):
        work[f"raw_{col}"] = pd.to_numeric(work[col], errors="coerce")
        work[col] = work[f"raw_{col}"] * np.asarray(factors, dtype=float)
    work["adjustment_factor"] = factors
    work["corporate_action_event"] = local_dates.isin(known_event_dates)

    # An unexplained >12% one-session discontinuity is not silently treated as
    # ordinary economics.  The threshold is above the normal Taiwan ±10% band;
    # special/no-limit cases therefore require an explicit reference event.
    raw_ret = pd.to_numeric(work["raw_close"], errors="coerce").pct_change()
    unexplained = (
        raw_ret.abs().gt(_UNEXPLAINED_JUMP_LIMIT)
        & ~work["corporate_action_event"].astype(bool)
    )
    if bool(unexplained.any()):
        rows = work.loc[
            unexplained,
            ["timestamp_local", "raw_close", "adjustment_factor"],
        ].head(5)
        raise TaiwanStockDataIntegrityError(
            "UNEXPLAINED_PRICE_DISCONTINUITY",
            details={"rows": rows.astype(str).to_dict("records")},
        )
    return work, ledger


def load_taiwan_stock_model_data(
    symbol: str,
    start_date: str,
    end_date: str,
    *,
    min_rows: int = 60,
    finmind: FinMindProvider | None = None,
    twse: TWSEProvider | None = None,
) -> TaiwanStockModelData:
    """Load raw daily prices + all known reference-reset channels, or fail closed."""
    code = normalize_taiwan_symbol(symbol)
    finmind = finmind or FinMindProvider()
    twse = twse or TWSEProvider()
    warnings: list[str] = []

    raw: pd.DataFrame | None = None
    raw_source = ""
    if finmind.status().status in {ProviderStatus.OK, ProviderStatus.NEEDS_CONFIG}:
        try:
            raw = finmind.fetch_price(code, start_date, end_date, adjusted=False)
            raw_source = "finmind:TaiwanStockPrice"
        except Exception as exc:
            warnings.append(f"finmind_raw: {type(exc).__name__}: {str(exc)[:160]}")

    if raw is None or raw.empty:
        try:
            raw = twse.fetch_symbol_daily(
                code,
                start_date.replace("-", ""),
                end_date.replace("-", ""),
            )
            raw_source = "twse:STOCK_DAY"
        except Exception as exc:
            raise TaiwanStockDataIntegrityError(
                "RAW_PRICE_UNAVAILABLE",
                details={
                    "finmind_warning": warnings,
                    "twse_error": f"{type(exc).__name__}: {str(exc)[:160]}",
                },
            ) from exc

    raw = raw.sort_values("timestamp_utc").reset_index(drop=True)
    if len(raw) < int(min_rows):
        raise TaiwanStockDataIntegrityError(
            "INSUFFICIENT_HISTORY",
            details={"actual_rows": int(len(raw)), "minimum_rows": int(min_rows)},
        )

    if finmind.status().status != ProviderStatus.OK:
        raise TaiwanStockDataIntegrityError(
            "CORPORATE_ACTION_SOURCE_UNAVAILABLE",
            details={"finmind_status": finmind.status().status.value},
        )

    events, channels = _fetch_reference_events(finmind, code, start_date, end_date)
    adjusted, ledger = apply_reference_resets(raw, events)
    current_factor = float(adjusted["adjustment_factor"].iloc[-1])
    model_data_grade = (
        "OFFICIAL_DAILY"
        if raw_source.startswith("twse:")
        else "RESEARCH_PROXY"
    )

    metadata = {
        "status": "OK",
        "corporate_action_integrity": ADJUSTMENT_STATUS_OK,
        "dataset_semantics": DATASET_SEMANTICS,
        "adjustment_semantics": ADJUSTMENT_SEMANTICS,
        "source_semantics": SOURCE_SEMANTICS,
        "feature_version": FEATURE_VERSION,
        "raw_price_source": raw_source,
        "model_data_grade": model_data_grade,
        "raw_source_is_exchange_official": raw_source.startswith("twse:"),
        "corporate_action_source": "FinMind reference-reset datasets",
        "requested_start_date": start_date,
        "requested_end_date": end_date,
        "actual_start_date": pd.Timestamp(adjusted["timestamp_local"].iloc[0]).strftime("%Y-%m-%d"),
        "actual_end_date": pd.Timestamp(adjusted["timestamp_local"].iloc[-1]).strftime("%Y-%m-%d"),
        "actual_rows": int(len(adjusted)),
        "current_adjustment_factor": current_factor,
        "raw_latest_close": float(adjusted["raw_close"].iloc[-1]),
        "continuity_latest_close": float(adjusted["close"].iloc[-1]),
        "event_count": int(len(ledger)),
        "events": ledger,
        "event_channels": channels,
        "warnings": warnings,
        "pit_guards": {
            "pre_event_prices_mutated_by_future_event": False,
            "reference_factor_applies_from_effective_date_forward": True,
            "events_used_as_predictive_features": False,
        },
    }
    return TaiwanStockModelData(frame=adjusted, raw_frame=raw, metadata=metadata)


def restore_forecast_to_raw_basis(forecast: Any, adjustment_factor: float) -> Any:
    """Map absolute forecast prices from continuity basis back to current raw basis."""
    scale = float(adjustment_factor or 1.0)
    if not math.isfinite(scale) or scale <= 0:
        raise ValueError("adjustment_factor must be finite and positive")
    out = forecast.model_copy(deep=True) if hasattr(forecast, "model_copy") else forecast
    if abs(scale - 1.0) < 1e-12:
        meta = dict(getattr(out, "model_metadata", {}) or {})
        meta.update({
            "price_basis": "RAW_CURRENT_BASIS",
            "continuity_adjustment_factor": scale,
            "adjustment_semantics": ADJUSTMENT_SEMANTICS,
        })
        out.model_metadata = meta
        return out

    def _rescale(value: Any) -> Any:
        return None if value is None else float(value) / scale

    out.point_forecast = _rescale(out.point_forecast)
    out.terminal_forecast = _rescale(out.terminal_forecast)
    out.quantiles = {k: _rescale(v) for k, v in dict(out.quantiles or {}).items()}
    out.lower_reference = _rescale(getattr(out, "lower_reference", None))
    out.upper_reference = _rescale(getattr(out, "upper_reference", None))
    path = []
    for row in list(getattr(out, "forecast_path", []) or []):
        item = dict(row)
        for key in ("p10", "p50", "p90"):
            if key in item:
                item[key] = _rescale(item[key])
        path.append(item)
    out.forecast_path = path
    meta = dict(getattr(out, "model_metadata", {}) or {})
    meta.update({
        "price_basis": "RAW_CURRENT_BASIS",
        "continuity_adjustment_factor": scale,
        "adjustment_semantics": ADJUSTMENT_SEMANTICS,
    })
    out.model_metadata = meta
    return out
