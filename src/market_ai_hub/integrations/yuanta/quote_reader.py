"""Offline field-aware adapter from persisted Yuanta quotes into V2-A.2 observations.

This module never logs in, subscribes, restarts the recorder, or invents exchange
timestamps. A recorder callback receipt is availability evidence, not an exchange
event time. Older snapshots without per-field provenance are explicitly degraded.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any

import pandas as pd
import yaml

from market_ai_hub.integrations.yuanta.live_quote_recorder import CONFIG_PATH
from market_ai_hub.research.v2.asof import ensure_utc_aware
from market_ai_hub.research.v2.factor_representation import (
    FactorRepresentationObservation,
    definition_for,
    observe_factor,
)

SOURCE_SCHEMA_VERSION = "YUANTA_QUOTE_READER_1"

_FIELD_CANDIDATES = {
    "trade": ("DealPrice", "deal"),
    "bid": ("BuyPrice",),
    "ask": ("SellPrice",),
}
_CONTRACT_YYMM = re.compile(r"(\d{4})$")


class QuoteReaderError(ValueError):
    """Typed fail-closed reader rejection."""


@dataclass(frozen=True)
class QuoteField:
    field_kind: str
    source_field: str
    value: float
    received_at: datetime
    event_timestamp: datetime | None
    timestamp_precision: str
    provenance_status: str


def _dt(value: Any, *, field: str) -> datetime:
    if value in (None, ""):
        raise QuoteReaderError(f"MISSING_{field.upper()}")
    try:
        return ensure_utc_aware(datetime.fromisoformat(str(value)))
    except Exception as exc:
        raise QuoteReaderError(f"INVALID_{field.upper()}") from exc


def _finite(value: Any) -> float:
    try:
        out = float(value)
    except Exception as exc:
        raise QuoteReaderError("NON_NUMERIC_QUOTE") from exc
    if not math.isfinite(out) or out <= 0:
        raise QuoteReaderError("INVALID_QUOTE_VALUE")
    return out


def _config(config_path: Path = CONFIG_PATH) -> dict:
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise QuoteReaderError("INVALID_RECORDER_CONFIG")
    return data


def _spec_by_key(config_path: Path = CONFIG_PATH) -> dict[str, dict]:
    cfg = _config(config_path)
    specs = list(cfg.get("subscriptions", [])) + list(cfg.get("daytime_context", []))
    return {str(x["key"]): dict(x) for x in specs if isinstance(x, dict) and x.get("key")}


def _snapshot_id(record: dict, field_kind: str, source_field: str) -> str:
    body = {
        "record": record,
        "field_kind": field_kind,
        "source_field": source_field,
        "schema": SOURCE_SCHEMA_VERSION,
    }
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)
    return "yuanta_quote_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _contract_month(record: dict) -> str:
    explicit = str(record.get("contract_month") or "").strip()
    if explicit:
        if not re.fullmatch(r"20\d{4}", explicit):
            raise QuoteReaderError("INVALID_CONTRACT_MONTH")
        return explicit
    code = str(record.get("instrument_code") or "")
    m = _CONTRACT_YYMM.search(code)
    if not m:
        return ""
    yy, mm = int(m.group(1)[:2]), int(m.group(1)[2:])
    if not 1 <= mm <= 12:
        return ""
    return f"20{yy:02d}{mm:02d}"


def _validate_recorder_status(status: dict | None) -> None:
    if not status:
        return
    if status.get("persistence_error"):
        raise QuoteReaderError("PERSISTENCE_ERROR")
    if int(status.get("dropped_records") or 0) > 0:
        raise QuoteReaderError("BUFFER_OVERFLOW")


def _match_spec(record: dict, *, config_path: Path = CONFIG_PATH) -> dict:
    key = str(record.get("subscription_key") or "")
    spec = _spec_by_key(config_path).get(key)
    if spec is None:
        raise QuoteReaderError("UNKNOWN_SUBSCRIPTION_KEY")
    if int(record.get("market_no", -1)) != int(spec.get("market_no", -2)):
        raise QuoteReaderError("MARKET_MISMATCH")
    code = str(record.get("instrument_code") or "")
    symbol = str(spec.get("symbol") or "")
    prefix = str(spec.get("code_prefix") or "")
    if symbol and code != symbol:
        raise QuoteReaderError("CONTRACT_MISMATCH")
    if prefix and not code.startswith(prefix):
        raise QuoteReaderError("CONTRACT_MISMATCH")
    factor = str(spec.get("factor") or "")
    representation = str(spec.get("representation") or "")
    if definition_for(factor, representation) is None:
        raise QuoteReaderError("UNSUPPORTED_V2_REPRESENTATION")
    return spec


def _validate_session_variant(record: dict, spec: dict, session_status: str) -> None:
    """SPARK PM/day codes must agree with the resolved V2 session when it is knowable."""
    market = int(record.get("market_no", -1))
    if market not in (3, 207):
        return
    variant = str(spec.get("session_variant") or "").upper()
    if variant not in ("BOTH", "AUTO", "TAIFEX_PM", "TAIFEX_DAY", "OSE_PM", "OSE_DAY"):
        return
    code = str(record.get("instrument_code") or "")
    is_pm = "PM" in code.upper()
    if variant in ("TAIFEX_PM", "OSE_PM") and not is_pm:
        raise QuoteReaderError("SESSION_VARIANT_MISMATCH")
    if variant in ("TAIFEX_DAY", "OSE_DAY") and is_pm:
        raise QuoteReaderError("SESSION_VARIANT_MISMATCH")
    if variant in ("BOTH", "AUTO"):
        if session_status in ("NIGHT_SESSION", "AFTER_HOURS_SESSION") and not is_pm:
            raise QuoteReaderError("SESSION_VARIANT_MISMATCH")
        if session_status == "REGULAR_SESSION" and is_pm:
            raise QuoteReaderError("SESSION_VARIANT_MISMATCH")


def extract_field(record: dict, field_kind: str) -> QuoteField:
    kind = str(field_kind).lower()
    candidates = _FIELD_CANDIDATES.get(kind)
    if candidates is None:
        raise QuoteReaderError("UNKNOWN_FIELD_KIND")
    available = [name for name in candidates if record.get(name) is not None]
    if not available:
        raise QuoteReaderError(f"MISSING_{kind.upper()}")

    provenance = record.get("field_provenance")
    source_field = available[0]
    fp = None
    if isinstance(provenance, dict):
        timed: list[tuple[datetime, str, dict]] = []
        field_entries = [provenance.get(name) for name in available if isinstance(provenance.get(name), dict)]
        for name in available:
            item = provenance.get(name)
            if isinstance(item, dict) and item.get("received_at"):
                timed.append((_dt(item.get("received_at"), field=f"{kind}_received_at"), name, item))
        if timed:
            received_at, source_field, fp = max(timed, key=lambda x: x[0])
        elif field_entries:
            raise QuoteReaderError(f"MISSING_{kind.upper()}_RECEIVED_AT")

    if fp is not None:
        timestamp_quality = str(fp.get("timestamp_quality") or "UNKNOWN")
        provenance_status = "PER_FIELD_VERIFIED"
        # source_time_of_day has no date and is deliberately not combined with receipt date.
        event_timestamp = None
    else:
        # Old recorder schema: top-level receipt may be used only as availability receipt,
        # never to claim per-field freshness.
        received_at = _dt(record.get("received_at"), field="received_at")
        timestamp_quality = str(record.get("timestamp_quality") or "UNKNOWN")
        provenance_status = "LEGACY_TOP_LEVEL_RECEIPT_ONLY"
        event_timestamp = None

    explicit_event = ((fp or {}).get("event_timestamp")
                      or record.get(f"{source_field}_event_timestamp")
                      or record.get("event_timestamp"))
    if explicit_event:
        event_timestamp = _dt(explicit_event, field="event_timestamp")

    precision = "TICK_TIMESTAMP" if event_timestamp is not None else "UNKNOWN"
    return QuoteField(
        field_kind=kind,
        source_field=source_field,
        value=_finite(record[source_field]),
        received_at=received_at,
        event_timestamp=event_timestamp,
        timestamp_precision=precision,
        provenance_status=provenance_status,
    )


def quote_to_factor_observation(
    record: dict,
    *,
    field_kind: str,
    asof: datetime,
    recorder_status: dict | None = None,
    config_path: Path = CONFIG_PATH,
) -> FactorRepresentationObservation:
    """Adapt one persisted quote field into the existing V2-A.2 contract."""
    _validate_recorder_status(recorder_status)
    spec = _match_spec(record, config_path=config_path)
    field = extract_field(record, field_kind)

    received_at = field.received_at
    if received_at > ensure_utc_aware(asof):
        raise QuoteReaderError("RECEIPT_AFTER_ASOF")

    factor = str(spec["factor"])
    representation = str(spec["representation"])
    definition = definition_for(factor, representation)
    assert definition is not None

    contract_code = str(record.get("instrument_code") or "")
    contract_month = _contract_month(record) if definition.instrument_type == "FUTURE" else ""
    roll_status = str(record.get("roll_status") or "")
    if definition.instrument_type == "FUTURE" and not roll_status:
        roll_status = "UNKNOWN"

    quality = field.provenance_status
    if definition.instrument_type == "FUTURE" and not contract_month:
        quality += "|CONTRACT_MONTH_UNKNOWN"

    obs = observe_factor(
        factor,
        representation,
        asof=asof,
        value=field.value,
        event_timestamp=field.event_timestamp,
        available_at=received_at,
        received_at=received_at,
        timestamp_precision=field.timestamp_precision,
        availability_status="AVAILABLE",
        quality_status=quality,
        provider=str(record.get("provider") or "YUANTA_SPARK"),
        source_type=f"BROKER_{field.field_kind.upper()}_QUOTE_REPLAY",
        source_schema_version=SOURCE_SCHEMA_VERSION,
        source_version=f"{record.get('callback_type') or ''}:{field.source_field}",
        source_snapshot_ids=[_snapshot_id(record, field_kind, field.source_field)],
        source_frequency="TICK",
        data_grade="BROKER_REALTIME",
        point_in_time_safe=True,
        revision_status="IMMUTABLE_REPLAY",
        contract_code=contract_code if definition.instrument_type == "FUTURE" else "",
        contract_month=contract_month,
        roll_status=roll_status,
        series_semantics="CONTRACT" if definition.instrument_type == "FUTURE" else "",
    )
    _validate_session_variant(record, spec, getattr(obs.session, "session_status", "UNKNOWN"))
    # Receipt-only records are intentionally never promoted to LIVE by observe_factor.
    return obs


def read_latest(
    latest_path: Path,
    *,
    asof: datetime,
    field_kind: str = "trade",
    status_path: Path | None = None,
    config_path: Path = CONFIG_PATH,
) -> list[FactorRepresentationObservation]:
    latest = json.loads(latest_path.read_text(encoding="utf-8"))
    status = json.loads(status_path.read_text(encoding="utf-8")) if status_path and status_path.exists() else None
    out = []
    for record in (latest.get("quotes") or {}).values():
        out.append(quote_to_factor_observation(
            record, field_kind=field_kind, asof=asof, recorder_status=status, config_path=config_path
        ))
    return out


def replay_parquet(
    parquet_path: Path,
    *,
    asof: datetime,
    field_kind: str = "trade",
    recorder_status: dict | None = None,
    config_path: Path = CONFIG_PATH,
) -> list[FactorRepresentationObservation]:
    if parquet_path.suffix.lower() != ".parquet":
        raise QuoteReaderError("PARTIAL_OR_UNSUPPORTED_FILE")
    frame = pd.read_parquet(parquet_path)
    rows = frame.where(pd.notna(frame), None).to_dict("records")
    out: list[FactorRepresentationObservation] = []
    last_receipt: dict[tuple[int, str, str], datetime] = {}
    for record in rows:
        field = extract_field(record, field_kind)
        key = (int(record.get("market_no", -1)), str(record.get("instrument_code") or ""), field_kind)
        previous = last_receipt.get(key)
        if previous is not None and field.received_at < previous:
            raise QuoteReaderError("OUT_OF_ORDER_RECEIPT")
        last_receipt[key] = field.received_at
        out.append(quote_to_factor_observation(
            record, field_kind=field_kind, asof=asof,
            recorder_status=recorder_status, config_path=config_path,
        ))
    return out
