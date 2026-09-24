"""W3.3 — Yuanta SPARK tick-detail source contract for Osaka terminal data.

This module is offline-safe. It parses the official GetStkTickDetail result without
assuming the timezone of StickDetail.TimeStamp. The official contract documents a
full DateTime but does not document the timestamp basis for OSE; therefore the
result is not eligible to become W3.2 terminal_close until runtime cross-check
evidence establishes that basis.

No broker calls live here. No order/account/balance API is used.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
import json
from datetime import datetime, time, timezone
from hashlib import sha256
from math import isfinite
from typing import Any
from zoneinfo import ZoneInfo

from market_ai_hub.services.calendar import is_ose_derivatives_session

W3_TICK_DETAIL_SOURCE_SCHEMA_VERSION = "W3.3"

YUANTA_SPARK_TICK_DETAIL = "YUANTA_SPARK_GET_STK_TICK_DETAIL"
TIMESTAMP_BASIS_UNVERIFIED = "UNVERIFIED_OSE_TIMESTAMP_BASIS"
TIMESTAMP_BASIS_RUNTIME_VERIFIED = "RUNTIME_VERIFIED_OSE_LOCAL"
OSE_MARKET_NO = 207
OSE_TIMEZONE = "Asia/Tokyo"
OSE_DAY_CLOSE = time(15, 45)
OSE_NIGHT_OPEN = time(17, 0)
MAX_LAST_COUNT = 20

STATUS_QUERY_WINDOW_READY = "QUERY_WINDOW_READY"
STATUS_QUERY_WINDOW_BLOCKED = "QUERY_WINDOW_BLOCKED"
STATUS_CANDIDATE_BLOCKED = "CANDIDATE_BLOCKED"
STATUS_CANDIDATE_ONLY = "CANDIDATE_ONLY"


def _aware(dt: datetime) -> datetime:
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    return dt.astimezone(timezone.utc)


def _enum_int(value: Any) -> int:
    try:
        return int(value)
    except Exception:
        raw = getattr(value, "value__", None)
        if raw is not None:
            return int(raw)
        raise ValueError(f"cannot convert enum to int: {value!r}")


def _raw_datetime(value: Any) -> datetime:
    """Extract date/time components but deliberately discard timezone interpretation."""
    if isinstance(value, datetime):
        return value.replace(tzinfo=None)
    attrs = ("Year", "Month", "Day", "Hour", "Minute", "Second")
    if all(hasattr(value, name) for name in attrs):
        return datetime(
            int(value.Year), int(value.Month), int(value.Day),
            int(value.Hour), int(value.Minute), int(value.Second),
            int(getattr(value, "Millisecond", 0)) * 1000,
        )
    text = str(value).strip()
    for fmt in (
        "%Y/%m/%d %H:%M:%S.%f",
        "%Y/%m/%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S.%f",
        "%Y-%m-%d %H:%M:%S",
    ):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise ValueError(f"unsupported tick timestamp: {text!r}")


def _iter_dotnet_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if hasattr(value, "Count") and hasattr(value, "__getitem__"):
        return [value[i] for i in range(int(value.Count))]
    try:
        return list(value)
    except TypeError as exc:
        raise ValueError("StickDetailList is not iterable") from exc


@dataclass(frozen=True)
class TickDetailRow:
    raw_timestamp: datetime
    deal_price: float
    deal_volume: int
    buy_price: float
    sell_price: float
    seq_no: int
    in_out_flag: int

    def __post_init__(self) -> None:
        if self.raw_timestamp.tzinfo is not None:
            raise ValueError("raw_timestamp must remain timezone-naive until basis verification")
        for name in ("deal_price", "buy_price", "sell_price"):
            value = float(getattr(self, name))
            if not isfinite(value):
                raise ValueError(f"{name} must be finite")

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TickDetailBatch:
    market_no: int
    stock_code: str
    rows: list[TickDetailRow]
    received_at: datetime
    timestamp_basis_status: str = TIMESTAMP_BASIS_UNVERIFIED
    provider: str = "YUANTA_SPARK"
    source_type: str = YUANTA_SPARK_TICK_DETAIL
    source_snapshot_id: str = ""

    def __post_init__(self) -> None:
        _aware(self.received_at)
        object.__setattr__(
            self,
            "rows",
            sorted(self.rows, key=lambda r: (r.raw_timestamp, r.seq_no)),
        )
        if not self.stock_code:
            raise ValueError("stock_code required")

    def identity_payload(self) -> dict[str, Any]:
        return {
            "market_no": self.market_no,
            "stock_code": self.stock_code,
            "rows": [
                {
                    **r.model_dump(),
                    "raw_timestamp": r.raw_timestamp.isoformat(timespec="milliseconds"),
                }
                for r in self.rows
            ],
            "received_at": _aware(self.received_at).isoformat(),
            "timestamp_basis_status": self.timestamp_basis_status,
            "provider": self.provider,
            "source_type": self.source_type,
        }

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


def parse_tick_detail_result(obj: Any, *, received_at: datetime) -> TickDetailBatch:
    """Parse official StickDetailResult without interpreting its DateTime timezone."""
    received = _aware(received_at)
    market = _enum_int(getattr(obj, "MarketNo"))
    stock = str(getattr(obj, "StockCode") or "").strip()
    rows: list[TickDetailRow] = []
    for item in _iter_dotnet_list(getattr(obj, "StickDetailList", None)):
        rows.append(TickDetailRow(
            raw_timestamp=_raw_datetime(getattr(item, "TimeStamp")),
            deal_price=float(getattr(item, "DealPrice")),
            deal_volume=int(getattr(item, "DealVol")),
            buy_price=float(getattr(item, "BuyPrice")),
            sell_price=float(getattr(item, "SellPrice")),
            seq_no=int(getattr(item, "SeqNo")),
            in_out_flag=int(getattr(item, "InOutFlag")),
        ))
    batch = TickDetailBatch(
        market_no=market,
        stock_code=stock,
        rows=rows,
        received_at=received,
    )
    encoded = json.dumps(
        batch.identity_payload(),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    ).encode("utf-8")
    digest = sha256(encoded).hexdigest()[:20]
    return replace(batch, source_snapshot_id=f"w33_tick_{digest}")


def ose_close_query_window(request_time: datetime) -> dict[str, Any]:
    """Check the deterministic post-day-close / pre-night-open OSE query window."""
    request_utc = _aware(request_time)
    local = request_utc.astimezone(ZoneInfo(OSE_TIMEZONE))
    trading_date = local.date()
    blockers: list[str] = []
    if not is_ose_derivatives_session(trading_date):
        blockers.append("NOT_OSE_SESSION_DATE")
    if local.time() < OSE_DAY_CLOSE:
        blockers.append("DAY_SESSION_NOT_CLOSED")
    if local.time() >= OSE_NIGHT_OPEN:
        blockers.append("NIGHT_SESSION_ALREADY_STARTED")
    return {
        "status": STATUS_QUERY_WINDOW_READY if not blockers else STATUS_QUERY_WINDOW_BLOCKED,
        "reason": ";".join(blockers),
        "request_time_utc": request_utc.isoformat(),
        "request_time_jst": local.isoformat(),
        "trading_date": trading_date.isoformat(),
        "values_exposed": False,
    }


def assess_ose_terminal_trade_candidate(batch: TickDetailBatch, *, request_time: datetime) -> dict[str, Any]:
    """Metadata-only readiness; never upgrades an unverified timestamp basis."""
    window = ose_close_query_window(request_time)
    blockers: list[str] = []
    if window["status"] != STATUS_QUERY_WINDOW_READY:
        blockers.extend([x for x in str(window["reason"]).split(";") if x])
    if batch.market_no != OSE_MARKET_NO:
        blockers.append("MARKET_NOT_OSE")
    if not batch.stock_code.upper().startswith("JNU"):
        blockers.append("NOT_JNU_CONTRACT")
    valid_trade_rows = [
        r for r in batch.rows
        if isfinite(float(r.deal_price)) and float(r.deal_price) > 0 and int(r.deal_volume) >= 0
    ]
    if not valid_trade_rows:
        blockers.append("NO_VALID_TRADE_ROWS")
    if batch.timestamp_basis_status != TIMESTAMP_BASIS_RUNTIME_VERIFIED:
        blockers.append("TIMESTAMP_BASIS_RUNTIME_VERIFICATION_REQUIRED")
    return {
        "status": STATUS_CANDIDATE_ONLY if not blockers else STATUS_CANDIDATE_BLOCKED,
        "reason": ";".join(sorted(set(blockers))),
        "market_no": batch.market_no,
        "stock_code": batch.stock_code,
        "row_count": len(batch.rows),
        "valid_trade_row_count": len(valid_trade_rows),
        "timestamp_basis_status": batch.timestamp_basis_status,
        "source_snapshot_id": batch.source_snapshot_id,
        "query_window_status": window["status"],
        "trading_date": window["trading_date"],
        "terminal_close_materialization_allowed": False,
        "values_exposed": False,
    }


def runtime_verification_requirements() -> dict[str, Any]:
    """Contract for the future maintenance-window measurement; no broker action."""
    return {
        "schema_version": W3_TICK_DETAIL_SOURCE_SCHEMA_VERSION,
        "provider": "YUANTA_SPARK",
        "market_no": OSE_MARKET_NO,
        "query": "GetStkTickDetail",
        "max_last_count": MAX_LAST_COUNT,
        "required_checks": [
            "same OSE contract query accepted by existing single-owner connection",
            "matching GetStkTickDetail response received",
            "StickDetail.TimeStamp basis cross-checked against verified OSE session/local clock",
            "returned stock_code/market_no match request",
            "query executed after 15:45 JST and before 17:00 JST",
        ],
        "current_timestamp_basis_status": TIMESTAMP_BASIS_UNVERIFIED,
        "terminal_close_materialization_allowed": False,
        "values_exposed": False,
    }
