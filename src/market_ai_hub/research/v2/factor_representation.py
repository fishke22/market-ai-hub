"""V2-A.2 — Factor Representation Routing (typed multi-factor contract).

RESEARCH ONLY. An economic factor (e.g. US_TECH_RISK, JP_EQUITY) is represented by one or more
**independent** instrument representations (cash index, future, spot). Machine-enforced invariants:

    CASH != FUTURES
    FUTURES OPEN != LIVE DATA AVAILABLE
    THEORETICAL SESSION OPEN != LIVE QUOTE
    DERIVATIVE PROXY != DIRECT TARGET
    PREVIOUS CLOSE != LIVE
    DELAYED PROXY != LIVE
    SAME ECONOMIC FACTOR != SAME PRICE SERIES

Two orthogonal axes are kept separate:
- representation_relation: DIRECT / CASH_REFERENCE / DERIVATIVE_PROXY / SPOT_PROXY / MACRO_CONTEXT / CONTEXT_ONLY
- temporal_role:          LIVE / PREVIOUS_SESSION_REFERENCE / DELAYED_REFERENCE / STATIC_MACRO_CONTEXT / UNAVAILABLE
and a deterministic display `resolved_role` is derived from them.

Contract presence != runtime data availability. Nothing here fetches data, fits probability, or
creates V2-D StateEvidence / V2-G sequences.

Schema: V2_FACTOR_ROUTING_SCHEMA_VERSION = "2A.2".
"""
from __future__ import annotations

from dataclasses import dataclass, field as dfield, asdict
from datetime import datetime
from typing import Any

from market_ai_hub.research.v2.asof import (
    STALENESS_STATUS, CONTEXT_ROLE, ensure_utc_aware, normalize_family,
)

V2_FACTOR_ROUTING_SCHEMA_VERSION = "2A.2"

REPRESENTATION_RELATIONS = ("DIRECT", "CASH_REFERENCE", "DERIVATIVE_PROXY", "SPOT_PROXY",
                            "MACRO_CONTEXT", "CONTEXT_ONLY")
INSTRUMENT_TYPES = ("CASH_INDEX", "EQUITY", "FUTURE", "FX", "YIELD", "MACRO", "CRYPTO", "OTHER")
RESOLVED_ROLES = ("DIRECT_LIVE", "LIVE_DERIVATIVE_PROXY", "LIVE_SPOT_PROXY",
                  "PREVIOUS_SESSION_REFERENCE", "DELAYED_REFERENCE", "STALE_REFERENCE",
                  "UNVERIFIED", "NOT_AVAILABLE")
TIMESTAMP_PRECISIONS = ("TICK_TIMESTAMP", "INTRADAY_TIMESTAMP", "SESSION_CLOSE_TIMESTAMP",
                        "SESSION_DATE_ONLY", "PERIOD_DATE_ONLY", "UNKNOWN")
RETURN_STATUSES = ("OK", "UNVERIFIED_ROLL", "BLOCKED_CROSS_REPRESENTATION_RETURN", "NOT_AVAILABLE")
AVAILABILITY_STATUSES = ("AVAILABLE", "NOT_AVAILABLE", "UNKNOWN")

RESOLVED_ROLE_ORDER = ("DIRECT_LIVE", "LIVE_DERIVATIVE_PROXY", "LIVE_SPOT_PROXY",
                       "PREVIOUS_SESSION_REFERENCE", "DELAYED_REFERENCE",
                       "STALE_REFERENCE", "UNVERIFIED", "NOT_AVAILABLE")

BLOCKED_CROSS_REPRESENTATION_RETURN = "BLOCKED_CROSS_REPRESENTATION_RETURN"

_LIVE_DATA_GRADES = ("EXCHANGE_REALTIME", "BROKER_REALTIME")
_LIVE_FREQUENCIES = ("TICK", "1M", "5M", "15M", "30M", "60M")
_LIVE_PRECISIONS = ("TICK_TIMESTAMP", "INTRADAY_TIMESTAMP")
_LIVE_SOFT_SECONDS = 60.0
_LIVE_HARD_SECONDS = 300.0


# ── definitions ──
@dataclass
class FactorRepresentationDefinition:
    economic_factor_id: str = ""
    representation_id: str = ""
    instrument: str = ""
    instrument_type: str = "OTHER"
    venue_id: str = ""
    calendar_id: str = ""
    representation_relation: str = "CONTEXT_ONLY"
    source_frequency: str = "DAILY"
    live_capable: bool = False
    provider_capability: str = "NOT_AVAILABLE"
    data_grade: str = "RESEARCH_PROXY"
    point_in_time_safe: bool = False
    schema_version: str = V2_FACTOR_ROUTING_SCHEMA_VERSION

    def __post_init__(self):
        if self.representation_relation not in REPRESENTATION_RELATIONS:
            raise ValueError(f"unknown representation_relation: {self.representation_relation!r}")
        if self.instrument_type not in INSTRUMENT_TYPES:
            raise ValueError(f"unknown instrument_type: {self.instrument_type!r}")

    def model_dump(self) -> dict:
        return asdict(self)


def _d(economic_factor_id, representation_id, instrument, instrument_type, venue_id, calendar_id,
       relation, provider_capability, *, live_capable=False, data_grade="RESEARCH_PROXY",
       frequency="DAILY", pit=False) -> FactorRepresentationDefinition:
    return FactorRepresentationDefinition(
        economic_factor_id=economic_factor_id, representation_id=representation_id,
        instrument=instrument, instrument_type=instrument_type, venue_id=venue_id,
        calendar_id=calendar_id, representation_relation=relation, source_frequency=frequency,
        live_capable=live_capable, provider_capability=provider_capability, data_grade=data_grade,
        point_in_time_safe=pit)


# static registry; presence of a definition != runtime data availability
FACTOR_REPRESENTATIONS: dict[str, list[FactorRepresentationDefinition]] = {
    "JP_EQUITY": [
        _d("JP_EQUITY", "NIKKEI225_CASH", "^N225", "CASH_INDEX", "XTKS", "XTKS", "CASH_REFERENCE",
           "RESEARCH_PROXY_DAILY"),
        _d("JP_EQUITY", "OSE_MICRO_FUTURES", "NK225MC", "FUTURE", "OSE_DERIVATIVES", "OSE_DERIVATIVES",
           "DIRECT", "OFFICIAL_SETTLEMENT_DAILY", live_capable=True, data_grade="OFFICIAL_DAILY"),
        _d("JP_EQUITY", "TOPIX_CASH", "^TPX", "CASH_INDEX", "XTKS", "XTKS", "CASH_REFERENCE",
           "RESEARCH_PROXY_DAILY"),
        _d("JP_EQUITY", "CME_NIKKEI_FUTURES", "NKD=F", "FUTURE", "CME", "CME_GLOBEX",
           "DERIVATIVE_PROXY", "RESEARCH_PROXY_DAILY", live_capable=True),
    ],
    "TW_INDEX": [
        _d("TW_INDEX", "TAIEX_CASH", "^TWII", "CASH_INDEX", "XTAI", "XTAI", "CASH_REFERENCE",
           "RESEARCH_PROXY_DAILY"),
        _d("TW_INDEX", "TX_FUTURES", "TX", "FUTURE", "TAIFEX_DERIVATIVES", "TAIFEX",
           "DERIVATIVE_PROXY", "NOT_AVAILABLE", live_capable=True),
        _d("TW_INDEX", "MTX_FUTURES", "MTX", "FUTURE", "TAIFEX_DERIVATIVES", "TAIFEX",
           "DERIVATIVE_PROXY", "NOT_AVAILABLE", live_capable=True),
        _d("TW_INDEX", "TMF_FUTURES", "TMF", "FUTURE", "TAIFEX_DERIVATIVES", "TAIFEX",
           "DERIVATIVE_PROXY", "NOT_AVAILABLE", live_capable=True),
    ],
    "US_TECH_RISK": [
        _d("US_TECH_RISK", "NASDAQ100_CASH", "NDX", "CASH_INDEX", "XNAS", "XNAS", "CASH_REFERENCE",
           "NOT_AVAILABLE"),
        _d("US_TECH_RISK", "NQ_FUTURES", "NQ=F", "FUTURE", "CME", "CME_GLOBEX", "DERIVATIVE_PROXY",
           "RESEARCH_PROXY_DAILY", live_capable=True),
        _d("US_TECH_RISK", "MNQ_FUTURES", "MNQ=F", "FUTURE", "CME", "CME_GLOBEX", "DERIVATIVE_PROXY",
           "NOT_AVAILABLE", live_capable=True),
        _d("US_TECH_RISK", "TAIFEX_UNF", "UNF", "FUTURE", "TAIFEX_DERIVATIVES", "TAIFEX",
           "DERIVATIVE_PROXY", "NOT_AVAILABLE", live_capable=True),
        _d("US_TECH_RISK", "SOX_PROXY", "^SOX", "CASH_INDEX", "XNAS", "XNAS", "SPOT_PROXY",
           "RESEARCH_PROXY_DAILY"),
    ],
    "US_BROAD_RISK": [
        _d("US_BROAD_RISK", "SP500_CASH", "^GSPC", "CASH_INDEX", "XNYS", "XNYS", "CASH_REFERENCE",
           "NOT_AVAILABLE"),
        _d("US_BROAD_RISK", "ES_FUTURES", "ES=F", "FUTURE", "CME", "CME_GLOBEX", "DERIVATIVE_PROXY",
           "RESEARCH_PROXY_DAILY", live_capable=True),
    ],
    "US_VOLATILITY": [
        _d("US_VOLATILITY", "VIX_CASH", "^VIX", "CASH_INDEX", "CBOE", "XNYS", "SPOT_PROXY",
           "RESEARCH_PROXY_DAILY"),
    ],
    "JPY_FX": [
        _d("JPY_FX", "USDJPY_SPOT", "USDJPY=X", "FX", "FX_OTC", "FX_OTC", "SPOT_PROXY",
           "RESEARCH_PROXY_DAILY", live_capable=True),
    ],
    "US_RATES": [
        _d("US_RATES", "US10Y", "^TNX", "YIELD", "XNYS", "XNYS", "MACRO_CONTEXT",
           "RESEARCH_PROXY_DAILY"),
        _d("US_RATES", "US5Y", "^FVX", "YIELD", "XNYS", "XNYS", "MACRO_CONTEXT",
           "RESEARCH_PROXY_DAILY"),
    ],
    "GOLD": [
        _d("GOLD", "GOLD_FUTURES", "GC=F", "FUTURE", "CME", "CME_GLOBEX", "DERIVATIVE_PROXY",
           "RESEARCH_PROXY_DAILY", live_capable=True),
    ],
    "WTI_OIL": [
        _d("WTI_OIL", "WTI_FUTURES", "CL=F", "FUTURE", "CME", "CME_GLOBEX", "DERIVATIVE_PROXY",
           "RESEARCH_PROXY_DAILY", live_capable=True),
    ],
    "CRYPTO": [
        _d("CRYPTO", "BTC_SPOT", "BTC-USD", "CRYPTO", "CRYPTO_24_7", "CRYPTO_24_7", "SPOT_PROXY",
           "RESEARCH_PROXY_DAILY", live_capable=True),
    ],
    "USD_BROAD": [
        _d("USD_BROAD", "DXY_SPOT", "DX-Y.NYB", "CASH_INDEX", "XNYS", "XNYS", "SPOT_PROXY",
           "RESEARCH_PROXY_DAILY"),
    ],
}

# runtime yfinance/provider symbol -> (economic_factor_id, representation_id)
SYMBOL_REPRESENTATION_MAP = {
    "^N225": ("JP_EQUITY", "NIKKEI225_CASH"),
    "^TPX": ("JP_EQUITY", "TOPIX_CASH"),
    "NKD=F": ("JP_EQUITY", "CME_NIKKEI_FUTURES"),
    "^TWII": ("TW_INDEX", "TAIEX_CASH"),
    "TX": ("TW_INDEX", "TX_FUTURES"),
    "MTX": ("TW_INDEX", "MTX_FUTURES"),
    "TMF": ("TW_INDEX", "TMF_FUTURES"),
    "UNF": ("US_TECH_RISK", "TAIFEX_UNF"),
    "NQ=F": ("US_TECH_RISK", "NQ_FUTURES"),
    "MNQ=F": ("US_TECH_RISK", "MNQ_FUTURES"),
    "^SOX": ("US_TECH_RISK", "SOX_PROXY"),
    "ES=F": ("US_BROAD_RISK", "ES_FUTURES"),
    "^VIX": ("US_VOLATILITY", "VIX_CASH"),
    "USDJPY=X": ("JPY_FX", "USDJPY_SPOT"),
    "JPY=X": ("JPY_FX", "USDJPY_SPOT"),
    "^TNX": ("US_RATES", "US10Y"),
    "^FVX": ("US_RATES", "US5Y"),
    "GC=F": ("GOLD", "GOLD_FUTURES"),
    "CL=F": ("WTI_OIL", "WTI_FUTURES"),
    "BTC-USD": ("CRYPTO", "BTC_SPOT"),
    "DX-Y.NYB": ("USD_BROAD", "DXY_SPOT"),
}


def factor_ids() -> tuple[str, ...]:
    return tuple(FACTOR_REPRESENTATIONS)


def definition_for(economic_factor_id: str, representation_id: str) -> FactorRepresentationDefinition | None:
    for d in FACTOR_REPRESENTATIONS.get(economic_factor_id, []):
        if d.representation_id == representation_id:
            return d
    return None


def definition_for_symbol(symbol: str) -> FactorRepresentationDefinition | None:
    mapped = SYMBOL_REPRESENTATION_MAP.get((symbol or "").strip().upper())
    if mapped is None:
        return None
    return definition_for(*mapped)


# ── observation ──
@dataclass
class FactorRepresentationObservation:
    economic_factor_id: str = ""
    representation_id: str = ""
    instrument: str = ""
    instrument_type: str = "OTHER"
    representation_relation: str = "CONTEXT_ONLY"
    temporal_role: str = "UNAVAILABLE"
    resolved_role: str = "NOT_AVAILABLE"
    venue_id: str = ""
    calendar_id: str = ""
    timezone: str = ""
    session: Any = None
    value: float | None = None
    event_timestamp: datetime | None = None
    available_at: datetime | None = None
    provider_timestamp: datetime | None = None
    received_at: datetime | None = None
    timestamp_precision: str = "UNKNOWN"
    quote_age_seconds: float | None = None
    staleness_status: str = "NOT_AVAILABLE"
    availability_status: str = "NOT_AVAILABLE"
    quality_status: str = "UNKNOWN"
    provider: str = ""
    source_type: str = ""
    source_frequency: str = "DAILY"
    source_schema_version: str = ""
    source_version: str = ""
    source_snapshot_ids: list[str] = dfield(default_factory=list)
    data_grade: str = ""
    point_in_time_safe: bool = False
    revision_status: str = "UNKNOWN"
    contract_code: str = ""
    contract_month: str = ""
    roll_status: str = ""
    series_semantics: str = ""
    days_to_expiry: int | None = None
    return_1d: float | None = None
    return_status: str = "NOT_AVAILABLE"
    schema_version: str = V2_FACTOR_ROUTING_SCHEMA_VERSION

    def model_dump(self) -> dict:
        return asdict(self)


def _staleness(obs: FactorRepresentationObservation, asof: datetime, market_open: bool | None) -> tuple[str, float | None]:
    anchor = obs.available_at or obs.provider_timestamp or obs.event_timestamp
    if anchor is None:
        return ("CLOSED_MARKET_REFERENCE" if market_open is False else "UNKNOWN"), None
    age = (ensure_utc_aware(asof) - ensure_utc_aware(anchor)).total_seconds()
    if market_open is False:
        return "CLOSED_MARKET_REFERENCE", age
    if age <= _LIVE_SOFT_SECONDS:
        return "FRESH", age
    if age <= _LIVE_HARD_SECONDS:
        return "DELAYED", age
    return "STALE", age


def _live_eligible(d: FactorRepresentationDefinition, obs: FactorRepresentationObservation,
                   session: Any, asof: datetime) -> bool:
    if not d.live_capable:
        return False
    if obs.availability_status != "AVAILABLE" or obs.value is None:
        return False
    if obs.data_grade not in _LIVE_DATA_GRADES:
        return False
    if obs.source_frequency not in _LIVE_FREQUENCIES:
        return False
    if obs.timestamp_precision not in _LIVE_PRECISIONS:
        return False
    if obs.event_timestamp is None or obs.available_at is None:
        return False
    if ensure_utc_aware(obs.available_at) > ensure_utc_aware(asof):
        return False
    if obs.staleness_status != "FRESH":
        return False
    if session is None or not session.tradable_now:
        return False
    if session.verification_status not in ("EXCHANGE_CALENDAR_VERIFIED", "SESSION_HOURS_VERIFIED"):
        return False
    if d.instrument_type == "FUTURE":
        if obs.series_semantics != "CONTRACT" or obs.roll_status != "NONE" or not obs.contract_code:
            return False
    return True


def _local_date_iso(dt: datetime, tz: str) -> str:
    if not tz:
        return ensure_utc_aware(dt).date().isoformat()
    try:
        import zoneinfo
        return ensure_utc_aware(dt).astimezone(zoneinfo.ZoneInfo(tz)).date().isoformat()
    except Exception:
        return ensure_utc_aware(dt).date().isoformat()


def _temporal_role(obs: FactorRepresentationObservation, session: Any, asof: datetime) -> tuple[str, str, float | None]:
    market_open = session.market_open if session is not None else None
    staleness, age = _staleness(obs, asof, market_open)
    if obs.availability_status != "AVAILABLE" or obs.value is None:
        return "UNAVAILABLE", staleness, age
    if session is not None and session.market_open is False:
        return "PREVIOUS_SESSION_REFERENCE", staleness, age
    dailyish = (obs.source_frequency in ("DAILY", "IRREGULAR", "STATIC")
                or obs.timestamp_precision in ("SESSION_DATE_ONLY", "PERIOD_DATE_ONLY", "UNKNOWN"))
    if dailyish:
        # a daily/date-only bar can never represent the current live session
        if (session is not None and session.trading_date and obs.event_timestamp is not None
                and _local_date_iso(obs.event_timestamp, session.timezone) < session.trading_date):
            return "PREVIOUS_SESSION_REFERENCE", staleness, age
        return "DELAYED_REFERENCE", staleness, age
    if staleness == "FRESH":
        return "LIVE", staleness, age
    if staleness == "DELAYED":
        return "DELAYED_REFERENCE", staleness, age
    if staleness == "CLOSED_MARKET_REFERENCE":
        return "PREVIOUS_SESSION_REFERENCE", staleness, age
    return "UNVERIFIED", staleness, age


def _resolved_role(relation: str, temporal_role: str, availability: str, staleness: str) -> str:
    if availability != "AVAILABLE" or temporal_role == "UNAVAILABLE":
        return "NOT_AVAILABLE"
    if temporal_role == "LIVE":
        if relation == "DIRECT":
            return "DIRECT_LIVE"
        if relation == "DERIVATIVE_PROXY":
            return "LIVE_DERIVATIVE_PROXY"
        if relation in ("SPOT_PROXY", "CASH_REFERENCE"):
            return "LIVE_SPOT_PROXY"
        return "DELAYED_REFERENCE"  # MACRO_CONTEXT / CONTEXT_ONLY never become a live target
    if temporal_role == "PREVIOUS_SESSION_REFERENCE":
        return "PREVIOUS_SESSION_REFERENCE"
    if temporal_role == "DELAYED_REFERENCE":
        return "DELAYED_REFERENCE"
    if temporal_role == "UNVERIFIED":
        return "STALE_REFERENCE" if staleness in ("STALE",) else "UNVERIFIED"
    return "UNVERIFIED"


def _session_for(d: FactorRepresentationDefinition, asof: datetime, *, is_expiring_contract=None):
    from market_ai_hub.research.v2.session_truth import resolve_venue_session
    if not d.venue_id:
        return None
    return resolve_venue_session(d.venue_id, asof, is_expiring_contract=is_expiring_contract)


def observe_factor(
    economic_factor_id: str,
    representation_id: str,
    *,
    asof: datetime,
    value: float | None = None,
    event_timestamp: datetime | None = None,
    available_at: datetime | None = None,
    provider_timestamp: datetime | None = None,
    received_at: datetime | None = None,
    timestamp_precision: str = "UNKNOWN",
    availability_status: str = "AVAILABLE",
    quality_status: str = "UNKNOWN",
    provider: str = "",
    source_type: str = "",
    source_schema_version: str = "",
    source_version: str = "",
    source_snapshot_ids: list[str] | None = None,
    source_frequency: str = "DAILY",
    data_grade: str = "RESEARCH_PROXY",
    point_in_time_safe: bool = False,
    revision_status: str = "UNKNOWN",
    contract_code: str = "",
    contract_month: str = "",
    roll_status: str = "",
    series_semantics: str = "",
    days_to_expiry: int | None = None,
    return_1d: float | None = None,
    is_expiring_contract: bool | None = None,
) -> FactorRepresentationObservation:
    """Build a resolved factor observation. No network. Never fabricates liveness."""
    d = definition_for(economic_factor_id, representation_id)
    if d is None:
        raise ValueError(f"unknown factor representation: {economic_factor_id}/{representation_id}")
    session = _session_for(d, asof, is_expiring_contract=is_expiring_contract)
    obs = FactorRepresentationObservation(
        economic_factor_id=d.economic_factor_id, representation_id=d.representation_id,
        instrument=d.instrument, instrument_type=d.instrument_type,
        representation_relation=d.representation_relation,
        venue_id=d.venue_id, calendar_id=d.calendar_id,
        timezone=session.timezone if session is not None else "",
        session=session,
        value=value, event_timestamp=event_timestamp, available_at=available_at,
        provider_timestamp=provider_timestamp, received_at=received_at,
        timestamp_precision=timestamp_precision,
        availability_status=availability_status, quality_status=quality_status,
        provider=provider, source_type=source_type, source_schema_version=source_schema_version,
        source_version=source_version, source_snapshot_ids=list(source_snapshot_ids or []),
        data_grade=data_grade, point_in_time_safe=point_in_time_safe,
        revision_status=revision_status,
        contract_code=contract_code, contract_month=contract_month, roll_status=roll_status,
        series_semantics=series_semantics, days_to_expiry=days_to_expiry,
        return_1d=return_1d,
    )
    obs.source_frequency = source_frequency
    temporal, staleness, age = _temporal_role(obs, session, asof)
    obs.staleness_status = staleness
    obs.quote_age_seconds = age
    # a live-capable observation on a trading session still needs full live proof
    if temporal == "LIVE" and not _live_eligible(d, obs, session, asof):
        temporal = "DELAYED_REFERENCE"
    obs.temporal_role = temporal
    obs.resolved_role = _resolved_role(d.representation_relation, temporal, availability_status, staleness)
    if return_1d is not None:
        obs.return_status = ("UNVERIFIED_ROLL"
                             if (d.instrument_type == "FUTURE" and series_semantics == "CONTINUOUS"
                                 and roll_status in ("", "UNKNOWN"))
                             else "OK")
    return obs


def _unavailable_observation(d: FactorRepresentationDefinition, asof: datetime) -> FactorRepresentationObservation:
    session = _session_for(d, asof)
    obs = FactorRepresentationObservation(
        economic_factor_id=d.economic_factor_id, representation_id=d.representation_id,
        instrument=d.instrument, instrument_type=d.instrument_type,
        representation_relation=d.representation_relation,
        venue_id=d.venue_id, calendar_id=d.calendar_id,
        timezone=session.timezone if session is not None else "",
        session=session, availability_status="NOT_AVAILABLE", quality_status="UNKNOWN",
        data_grade=d.data_grade, point_in_time_safe=d.point_in_time_safe,
        temporal_role="UNAVAILABLE", resolved_role="NOT_AVAILABLE",
        staleness_status="NOT_AVAILABLE",
    )
    return obs


def resolve_factor_representations(
    economic_factor_id: str,
    asof: datetime,
    *,
    observations: list[FactorRepresentationObservation] | None = None,
) -> list[FactorRepresentationObservation]:
    """Return every registered representation of the factor, resolved for `asof`.

    Provided observations are resolved; representations without an observation are returned as
    NOT_AVAILABLE placeholders (an open venue without data must NOT become live).
    """
    defs = FACTOR_REPRESENTATIONS.get(economic_factor_id)
    if defs is None:
        raise ValueError(f"unknown economic_factor_id: {economic_factor_id!r}")
    by_rep = {o.representation_id: o for o in (observations or [])}
    out: list[FactorRepresentationObservation] = []
    for d in defs:
        obs = by_rep.get(d.representation_id)
        if obs is None:
            out.append(_unavailable_observation(d, asof))
        else:
            out.append(obs)
    out.sort(key=lambda o: (RESOLVED_ROLE_ORDER.index(o.resolved_role)
                            if o.resolved_role in RESOLVED_ROLE_ORDER else 99, o.representation_id))
    return out


# ── cross-representation return guard ──
def representation_return(previous: FactorRepresentationObservation | None,
                          current: FactorRepresentationObservation | None) -> tuple[float | None, str]:
    """Return a descriptive return ONLY within the same representation.

    Cash close -> futures current (or any representation change) is blocked:
    BLOCKED_CROSS_REPRESENTATION_RETURN (there is no basis/cross-representation-gap model in V2-A.2).
    """
    if previous is None or current is None:
        return None, "NOT_AVAILABLE"
    if previous.representation_id != current.representation_id:
        return None, BLOCKED_CROSS_REPRESENTATION_RETURN
    if previous.value is None or current.value is None or previous.value == 0:
        return None, "NOT_AVAILABLE"
    r = current.value / previous.value - 1.0
    if (current.instrument_type == "FUTURE" and current.series_semantics == "CONTINUOUS"
            and current.roll_status in ("", "UNKNOWN")):
        return r, "UNVERIFIED_ROLL"
    return r, "OK"


# ── runtime entry builder (analysis.cross_market) ──
def build_cross_market_entry(
    symbol: str,
    *,
    value: float | None,
    return_1d: float | None,
    event_timestamp: datetime | None,
    asof: datetime,
    received_at: datetime | None = None,
    provider: str = "yfinance",
    source_frequency: str = "DAILY",
    data_grade: str = "RESEARCH_PROXY",
    timestamp_precision: str = "SESSION_DATE_ONLY",
    point_in_time_safe: bool = False,
    revision_status: str = "UNKNOWN",
) -> dict:
    """Build one truthful `cross_market` entry. Keeps `last`/`return_1d` for backward compatibility."""
    d = definition_for_symbol(symbol)
    if d is None:
        session = None
        base = {
            "economic_factor_id": "", "representation_id": "UNMAPPED",
            "instrument": symbol, "instrument_type": "OTHER",
            "representation_relation": "CONTEXT_ONLY", "temporal_role": "UNVERIFIED",
            "resolved_role": "UNVERIFIED", "venue_id": "", "calendar_id": "",
            "timezone": "", "session": None, "session_status": "UNKNOWN", "trading_date": "",
            "event_timestamp": event_timestamp.isoformat() if event_timestamp else None,
            "available_at": None, "provider_timestamp": None,
            "received_at": received_at.isoformat() if received_at else None,
            "timestamp_precision": timestamp_precision, "quote_age_seconds": None,
            "staleness_status": "UNKNOWN", "availability_status": "UNKNOWN",
            "provider": provider, "data_grade": data_grade, "point_in_time_safe": point_in_time_safe,
            "contract_code": "", "contract_month": "", "roll_status": "", "series_semantics": "",
        }
        return {**base, "last": value, "return_1d": return_1d, "return_status": "NOT_AVAILABLE"}

    obs = observe_factor(
        d.economic_factor_id, d.representation_id, asof=asof, value=value,
        event_timestamp=event_timestamp, received_at=received_at,
        timestamp_precision=timestamp_precision, provider=provider, source_type="yfinance_daily",
        source_frequency=source_frequency, data_grade=data_grade,
        point_in_time_safe=point_in_time_safe, revision_status=revision_status,
        return_1d=return_1d,
    )
    session = obs.session
    entry = obs.model_dump()
    entry["session_status"] = session.session_status if session is not None else "UNKNOWN"
    entry["trading_date"] = session.trading_date if session is not None else ""
    # availability_semantics: received_at is a runtime receipt, not historical availability truth
    entry["availability_semantics"] = "RUNTIME_RECEIPT_ONLY"
    entry["last"] = value
    entry["return_1d"] = return_1d
    return entry
