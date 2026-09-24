"""V2-A — As-Of / Timestamp / Data Truth foundation (versioned typed schema).

CORE INVARIANT (machine-enforced):
    feature_information_time <= feature_cutoff_timestamp <= forecast_origin

Point-in-time truth is INFORMATION AVAILABILITY (observed_at), not market event time alone.
A value whose event is early but observed only after the cutoff is unusable.

This module is CPU/lightweight, loads no model weights, and is read-only w.r.t. the data lake.
It does NOT implement state models, labels, distribution fitting, calibration, or order flow.

Separate schema version (not tied to Price/Probability Map 3A.2.x):
    V2_ASOF_SCHEMA_VERSION = "2A.2"
"""
from __future__ import annotations

from dataclasses import dataclass, field as dfield, asdict
from datetime import datetime, timezone, timedelta
from hashlib import sha256
from zoneinfo import ZoneInfo
from typing import Any

V2_ASOF_SCHEMA_VERSION = "2A.2"

# ── canonical enums ──
FREQUENCY_SEMANTICS = ("TICK", "1M", "5M", "15M", "30M", "60M", "DAILY", "IRREGULAR", "STATIC", "UNKNOWN")
STALENESS_STATUS = ("FRESH", "DELAYED", "STALE", "CLOSED_MARKET_REFERENCE", "UNKNOWN", "NOT_AVAILABLE")
CONTEXT_ROLE = ("LIVE", "PREVIOUS_SESSION_REFERENCE", "DELAYED_REFERENCE", "STATIC_MACRO_CONTEXT", "UNAVAILABLE")
AVAILABILITY_STATUS = ("AVAILABLE", "NOT_AVAILABLE", "UNKNOWN")
QUALITY_STATUS = ("GOOD", "DEGRADED", "CRITICAL", "UNKNOWN")
SNAPSHOT_IMMUTABILITY = ("IMMUTABLE", "MUTABLE_CACHE")
REVISION_STATUS = ("REVISION_SAFE", "REVISION_RISK_PRESENT", "VINTAGE_NOT_AVAILABLE", "UNKNOWN")
SESSION_TYPES = ("DAY", "NIGHT", "OVERNIGHT", "HOLIDAY_DAY", "HOLIDAY_NIGHT", "UNKNOWN")

# Temporal leakage result codes (§41)
TEMPORAL_LEAKAGE_OK = "PASS"
TEMPORAL_LEAKAGE_RESULTS = (
    "PASS", "FAIL_FUTURE_EVENT", "FAIL_OBSERVED_AFTER_CUTOFF", "FAIL_RELEASE_AFTER_CUTOFF",
    "FAIL_TIMEZONE", "FAIL_SESSION_MAPPING", "FAIL_STALE_POLICY", "UNKNOWN",
)

# Data capability identifiers (§40/§36)
DATA_CAPABILITIES = ("OHLCV", "TICK", "L1", "L2", "ORDER_EVENT")
FREQUENCY_CAPABILITIES = ("TICK", "1M", "5M", "15M", "30M", "60M", "DAILY")

# Exchange timezone policy (§7) — canonical, MUST be tz-aware.
# calendar_id → IANA tz. XTKS uses Asia/Tokyo for cash; OSE_DERIVATIVES uses Asia/Tokyo for derivatives.
EXCHANGE_TIMEZONES = {
    "XTAI": "Asia/Taipei",
    "XTKS": "Asia/Tokyo",
    "OSE_DERIVATIVES": "Asia/Tokyo",
    "XNYS": "America/New_York",
    "CME": "America/Chicago",
}
CANONICAL_TIMEZONE = "UTC"

# OSE Direct vs Proxy calendar separation (§20) — DIRECT must stay OSE_DERIVATIVES, PROXY must be XTKS.
TARGET_SEMANTICS = {
    "OSAKA_MICRO": {"calendar": "OSE_DERIVATIVES", "role": "DIRECT"},
    "^N225": {"calendar": "XTKS", "role": "PROXY"},
    "TAIEX": {"calendar": "XTAI", "role": "DIRECT", "cash_index_executable": False},
    "TAIWAN_STOCK": {"calendar": "XTAI", "role": "DIRECT"},
}


# ── timezone helpers ──
def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc_aware(dt: datetime, tz: str | None = None) -> datetime:
    """§6/§55: canonical internal timestamp must be tz-aware UTC. Naive requires explicit tz context."""
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc)
    if not tz:
        raise ValueError("naive datetime requires explicit timezone context (tz) — never assume UTC")
    return dt.replace(tzinfo=ZoneInfo(tz)).astimezone(timezone.utc)


def to_exchange_local(dt: datetime, calendar_id: str) -> datetime:
    """Return exchange-local tz-aware timestamp for a calendar."""
    tz = EXCHANGE_TIMEZONES.get(calendar_id)
    if not tz:
        raise ValueError(f"unknown exchange timezone for calendar {calendar_id!r}")
    return ensure_utc_aware(dt).astimezone(ZoneInfo(tz))


def normalize_instrument(s: str) -> str:
    x = (s or "").strip().upper()
    if x.isdigit():
        return f"{x}.TW"
    return x


def normalize_family(s: str) -> str:
    return (s or "").strip().upper()


# ── TemporalContext (§5) ──
@dataclass
class TemporalContext:
    """Canonical time identity for one market event / observation / forecast."""
    event_timestamp: datetime | None = None
    source_timestamp: datetime | None = None
    observed_at: datetime | None = None
    ingested_at: datetime | None = None
    feature_cutoff_timestamp: datetime | None = None
    forecast_origin: datetime | None = None
    trading_date: str = ""
    session_date: str = ""
    exchange_timezone: str = ""
    source_timezone: str = ""
    canonical_timezone: str = CANONICAL_TIMEZONE
    session_id: str = ""
    calendar_id: str = ""
    market_open_status: str = "UNKNOWN"
    source_frequency: str = "UNKNOWN"
    data_latency_seconds: float | None = None
    data_staleness_seconds: float | None = None

    def __post_init__(self):
        # enforce tz-aware (unless None); a naive timestamp is a contract violation
        for name in ("event_timestamp", "source_timestamp", "observed_at", "ingested_at",
                     "feature_cutoff_timestamp", "forecast_origin"):
            v = getattr(self, name)
            if v is not None and v.tzinfo is None:
                raise ValueError(f"naive timestamp not allowed in TemporalContext.{name} (LEGACY_NAIVE_TIMESTAMP)")
        if self.source_frequency not in FREQUENCY_SEMANTICS:
            raise ValueError(f"unknown source_frequency: {self.source_frequency!r}")

    def validate_ordering(self) -> list[str]:
        """Invariant: feature_information_time <= feature_cutoff_timestamp <= forecast_origin."""
        reasons: list[str] = []
        if self.feature_cutoff_timestamp and self.forecast_origin \
                and self.feature_cutoff_timestamp > self.forecast_origin:
            reasons.append("CUTOFF_AFTER_ORIGIN")
        # any observation timestamp must not exceed cutoff
        for name in ("event_timestamp", "source_timestamp", "observed_at"):
            v = getattr(self, name)
            if v is not None and self.feature_cutoff_timestamp and v > self.feature_cutoff_timestamp:
                reasons.append(f"{name.upper()}_AFTER_CUTOFF")
        return reasons

    def model_dump(self) -> dict:
        return asdict(self)


# ── MarketSessionContext (§19/§21/§22) ──
@dataclass
class MarketSessionContext:
    market: str = ""
    calendar_id: str = ""
    trading_date: str = ""
    session_id: str = ""
    session_type: str = "UNKNOWN"
    session_open: str = ""
    session_close: str = ""
    is_holiday_trading: bool = False
    cash_market_open: bool = False
    derivatives_market_open: bool = False
    us_market_open: bool = False
    overnight_session: bool = False
    special_session_status: str = "NONE"

    def __post_init__(self):
        if self.session_type not in SESSION_TYPES:
            raise ValueError(f"unknown session_type: {self.session_type!r}")

    def model_dump(self) -> dict:
        return asdict(self)


# ── AsOfObservation (§9) ──
@dataclass
class AsOfObservation:
    instrument: str = ""
    target_family: str = ""
    provider: str = ""
    field: str = ""
    value: Any = None
    event_timestamp: datetime | None = None
    observed_at: datetime | None = None
    ingested_at: datetime | None = None
    source_timestamp: datetime | None = None
    release_timestamp: datetime | None = None
    frequency: str = "DAILY"
    calendar_id: str = ""
    session_id: str = ""
    quality_status: str = "UNKNOWN"
    availability_status: str = "AVAILABLE"
    staleness_status: str = "UNKNOWN"
    context_role: str = "UNAVAILABLE"
    snapshot_id: str = ""
    provenance: dict = dfield(default_factory=dict)

    def __post_init__(self):
        if self.frequency not in FREQUENCY_SEMANTICS:
            raise ValueError(f"unknown frequency: {self.frequency!r}")
        if self.availability_status not in AVAILABILITY_STATUS:
            raise ValueError(f"unknown availability_status: {self.availability_status!r}")
        if self.staleness_status not in STALENESS_STATUS:
            raise ValueError(f"unknown staleness_status: {self.staleness_status!r}")
        if self.context_role not in CONTEXT_ROLE:
            raise ValueError(f"unknown context_role: {self.context_role!r}")

    def is_available(self) -> bool:
        return self.availability_status == "AVAILABLE" and self.value is not None

    def model_dump(self) -> dict:
        return asdict(self)


# ── future-data hard rejection (§11) ──
def reject_future_information(obs: AsOfObservation, cutoff: datetime) -> list[str]:
    """Return reason codes if the observation is not usable as-of `cutoff`."""
    cutoff = ensure_utc_aware(cutoff)
    reasons: list[str] = []
    # information availability is the core: if not observed by cutoff → unusable
    if obs.observed_at is not None and ensure_utc_aware(obs.observed_at) > cutoff:
        reasons.append("FAIL_OBSERVED_AFTER_CUTOFF")
    if obs.event_timestamp is not None and ensure_utc_aware(obs.event_timestamp) > cutoff:
        reasons.append("FAIL_FUTURE_EVENT")
    if obs.release_timestamp is not None and ensure_utc_aware(obs.release_timestamp) > cutoff:
        reasons.append("FAIL_RELEASE_AFTER_CUTOFF")
    return reasons


# ── point-in-time query (§10) ──
def get_asof(observations: list[AsOfObservation], instrument: str, fields: list[str] | None = None,
             cutoff: datetime | None = None, session_id: str | None = None,
             calendar_id: str | None = None) -> list[AsOfObservation]:
    """Return only observations whose information was available at or before `cutoff`.

    Any observed_at > cutoff is excluded. Additionally the future-data guard is applied.
    """
    cutoff = cutoff or utc_now()
    cutoff = ensure_utc_aware(cutoff)
    out: list[AsOfObservation] = []
    for o in observations:
        if normalize_instrument(o.instrument) != normalize_instrument(instrument):
            continue
        if fields and o.field not in fields:
            continue
        if session_id and o.session_id and o.session_id != session_id:
            continue
        if calendar_id and o.calendar_id and normalize_family(o.calendar_id) != normalize_family(calendar_id):
            continue
        if o.observed_at is not None and ensure_utc_aware(o.observed_at) > cutoff:
            continue
        if reject_future_information(o, cutoff):
            continue
        out.append(o)
    return out


def latest_observation(observations: list[AsOfObservation], key: str = "observed_at") -> AsOfObservation | None:
    """Return the latest observation by `key` (point-in-time valid set only)."""
    valid = [o for o in observations if getattr(o, key) is not None]
    if not valid:
        return None
    return max(valid, key=lambda o: ensure_utc_aware(getattr(o, key)))


# ── point-in-time join (§31) ──
@dataclass
class JoinRow:
    forecast_origin: datetime
    feature_cutoff_timestamp: datetime
    field: str
    value: Any = None
    source_observed_at: datetime | None = None
    source_event_timestamp: datetime | None = None
    age_seconds: float | None = None
    staleness_status: str = "NOT_AVAILABLE"
    snapshot_id: str = ""
    forward_filled: bool = False


def point_in_time_join(
    left_cutoffs: list[datetime],
    right: list[AsOfObservation],
    field: str,
    instrument: str,
    max_age_seconds: float | None = None,
    calendar_id: str | None = None,
    session_id: str | None = None,
    allow_forward_fill: bool = False,
    illegal_boundary_guard: bool = True,
) -> list[JoinRow]:
    """Join a left series of forecast/feature cutoffs to the right as-of observations.

    For each cutoff, only observations with observed_at <= cutoff qualify; we take the latest.
    Forward fill may only carry a prior observation forward if allow_forward_fill; the original
    event/observed timestamp and staleness are preserved (never rewritten).
    """
    rows: list[JoinRow] = []
    sorted_obs = sorted(right, key=lambda o: ensure_utc_aware(o.observed_at) if o.observed_at else datetime.min.replace(tzinfo=timezone.utc))
    last_valid: AsOfObservation | None = None
    for cutoff in sorted(left_cutoffs, key=lambda d: ensure_utc_aware(d)):
        cutoff = ensure_utc_aware(cutoff)
        # qualify observations observed at/before cutoff for this field+instrument
        window = [o for o in sorted_obs
                  if normalize_instrument(o.instrument) == normalize_instrument(instrument)
                  and o.field == field
                  and o.observed_at is not None
                  and ensure_utc_aware(o.observed_at) <= cutoff
                  and not reject_future_information(o, cutoff)]
        if calendar_id:
            window = [o for o in window if not o.calendar_id or normalize_family(o.calendar_id) == normalize_family(calendar_id)]
        if session_id:
            window = [o for o in window if not o.session_id or o.session_id == session_id]
        best = latest_observation(window, "observed_at") if window else None
        matched = best is not None
        # max-age cap
        if best is not None and max_age_seconds is not None:
            age = (cutoff - ensure_utc_aware(best.observed_at)).total_seconds()
            if age > max_age_seconds:
                best = None
                matched = False
        filled = False
        if best is None and allow_forward_fill and last_valid is not None:
            # forward fill — preserve original metadata; block illegal boundaries
            boundary_ok = True
            if illegal_boundary_guard and last_valid.session_id and \
                    any(o.session_id and o.session_id != last_valid.session_id for o in window):
                boundary_ok = False
            if boundary_ok:
                best = last_valid
                filled = True
        if best is not None:
            age = (cutoff - ensure_utc_aware(best.observed_at)).total_seconds() if best.observed_at else None
            stale = staleness_for(best.observed_at, now=cutoff) if best.observed_at else "NOT_AVAILABLE"
            rows.append(JoinRow(
                forecast_origin=cutoff, feature_cutoff_timestamp=cutoff, field=field,
                value=best.value, source_observed_at=best.observed_at,
                source_event_timestamp=best.event_timestamp, age_seconds=age,
                staleness_status=stale, snapshot_id=best.snapshot_id,
                forward_filled=filled,
            ))
            if matched:
                last_valid = best
        else:
            rows.append(JoinRow(forecast_origin=cutoff, feature_cutoff_timestamp=cutoff, field=field,
                                staleness_status="NOT_AVAILABLE"))
    return rows


# ── staleness (§14/§15/§16/§33/§34) ──
def staleness_for(observed_at: datetime, now: datetime | None = None,
                  soft_seconds: float | None = None, hard_seconds: float | None = None,
                  market_open: bool | None = None) -> str:
    """Compute StalenessStatus. When market closed, a previous-session reference is
    CLOSED_MARKET_REFERENCE, not FRESH."""
    observed_at = ensure_utc_aware(observed_at)
    now = ensure_utc_aware(now) if now else utc_now()
    age = (now - observed_at).total_seconds()
    if market_open is False:
        return "CLOSED_MARKET_REFERENCE"
    if soft_seconds is None or hard_seconds is None:
        return "UNKNOWN"
    if age <= soft_seconds:
        return "FRESH"
    if age <= hard_seconds:
        return "DELAYED"
    return "STALE"


def context_role_for(staleness: str, market_open: bool | None, is_macro: bool = False,
                     is_live_market: bool = False) -> str:
    """Map staleness + market context to CONTEXT_ROLE. A prior-session US close in an Asian
    session is PREVIOUS_SESSION_REFERENCE, not LIVE."""
    if staleness == "NOT_AVAILABLE":
        return "UNAVAILABLE"
    if is_macro:
        return "STATIC_MACRO_CONTEXT"
    if market_open is False:
        return "PREVIOUS_SESSION_REFERENCE"
    if not is_live_market:
        return "DELAYED_REFERENCE"
    if staleness in ("FRESH",):
        return "LIVE"
    if staleness in ("DELAYED",):
        return "DELAYED_REFERENCE"
    return "PREVIOUS_SESSION_REFERENCE"


def unavailable_observation(field: str, instrument: str = "", provider: str = "") -> AsOfObservation:
    """§18: a missing context is null + NOT_AVAILABLE, never a zero-fill."""
    return AsOfObservation(instrument=instrument, provider=provider, field=field, value=None,
                           availability_status="NOT_AVAILABLE", staleness_status="NOT_AVAILABLE",
                           context_role="UNAVAILABLE")


# ── MarketContextQuality (§17) ──
@dataclass
class MarketContextQuality:
    source_coverage: dict = dfield(default_factory=dict)
    fresh_source_count: int = 0
    stale_source_count: int = 0
    missing_source_count: int = 0
    market_open_alignment: bool = False
    overall_status: str = "UNKNOWN"

    def __post_init__(self):
        if self.overall_status not in QUALITY_STATUS:
            raise ValueError(f"unknown overall_status: {self.overall_status!r}")

    def model_dump(self) -> dict:
        return asdict(self)


def market_context_quality(obs_by_source: dict[str, list[AsOfObservation]],
                           cutoff: datetime | None = None,
                           expected_sources: list[str] | None = None) -> MarketContextQuality:
    """Rule-based metadata summary (no score model)."""
    cutoff = ensure_utc_aware(cutoff) if cutoff else utc_now()
    expected = expected_sources or list(obs_by_source.keys())
    fresh = stale = 0
    coverage: dict[str, str] = {}
    for src in expected:
        items = obs_by_source.get(src) or []
        avail = [o for o in items if o.is_available() and o.observed_at is not None
                 and ensure_utc_aware(o.observed_at) <= cutoff]
        if not items:
            coverage[src] = "MISSING"
            continue
        if not avail:
            coverage[src] = "NOT_AVAILABLE"
            continue
        s = staleness_for(avail[0].observed_at, now=cutoff)
        coverage[src] = s
        if s == "FRESH":
            fresh += 1
        else:
            stale += 1
    # missing = sources whose coverage resolved to MISSING / NOT_AVAILABLE (NOT string search on names)
    missing = sum(1 for v in coverage.values() if v in ("MISSING", "NOT_AVAILABLE"))
    aligned = fresh >= 1 and stale == 0
    if missing and not fresh:
        overall = "CRITICAL"
    elif stale:
        overall = "DEGRADED"
    elif missing:
        overall = "DEGRADED"
    else:
        overall = "GOOD"
    return MarketContextQuality(source_coverage=coverage, fresh_source_count=fresh,
                                stale_source_count=stale, missing_source_count=missing,
                                market_open_alignment=aligned, overall_status=overall)


# ── DataSnapshot / lineage (§25/§26/§56) ──
@dataclass
class DataSnapshot:
    snapshot_id: str = ""
    provider: str = ""
    instrument: str = ""
    retrieved_at: datetime | None = None
    source_timestamp_start: datetime | None = None
    source_timestamp_end: datetime | None = None
    observed_at_start: datetime | None = None
    observed_at_end: datetime | None = None
    row_count: int = 0
    schema_version: str = ""
    content_hash: str = ""
    local_path_or_table: str = ""
    data_license_class: str = ""
    local_only: bool = False
    immutability: str = "MUTABLE_CACHE"  # honest default; set IMMUTABLE only when verified

    def __post_init__(self):
        if self.immutability not in SNAPSHOT_IMMUTABILITY:
            raise ValueError(f"unknown immutability: {self.immutability!r}")

    def identity_key(self) -> str:
        """§56: stable identity from canonical metadata + content. Any change → new identity."""
        payload = "|".join([
            self.provider, normalize_instrument(self.instrument), self.schema_version,
            self.content_hash, self.immutability,
            self.retrieved_at.isoformat() if self.retrieved_at else "",
        ])
        return sha256(payload.encode("utf-8")).hexdigest()[:16]

    def model_dump(self) -> dict:
        return asdict(self)


def make_snapshot_id(provider: str, instrument: str, schema_version: str,
                     content_hash: str, retrieved_at: datetime) -> str:
    return sha256(f"{provider}|{normalize_instrument(instrument)}|{schema_version}|{content_hash}|{ensure_utc_aware(retrieved_at).isoformat()}".encode("utf-8")).hexdigest()[:24]


# ── FeatureComputationContext (§27) ──
@dataclass
class FeatureComputationContext:
    feature_name: str = ""
    feature_version: str = ""
    instrument: str = ""
    target_family: str = ""
    feature_cutoff_timestamp: datetime | None = None
    forecast_origin: datetime | None = None
    source_snapshot_ids: list[str] = dfield(default_factory=list)
    calendar_id: str = ""
    session_id: str = ""
    asof_enforced: bool = True
    leakage_check_status: str = TEMPORAL_LEAKAGE_OK

    def __post_init__(self):
        if self.leakage_check_status not in TEMPORAL_LEAKAGE_RESULTS:
            raise ValueError(f"unknown leakage_check_status: {self.leakage_check_status!r}")

    def model_dump(self) -> dict:
        return asdict(self)


# ── Temporal leakage checker (§41/§42) ──
def temporal_leakage_check(ctx: TemporalContext, obs: AsOfObservation | None = None) -> str:
    """Return one TemporalLeakageCheckResult code. Dev/test raises on FAIL_* when raise_on_fail."""
    if any((getattr(ctx, n) is not None and getattr(ctx, n).tzinfo is None)
           for n in ("event_timestamp", "source_timestamp", "observed_at", "ingested_at",
                     "feature_cutoff_timestamp", "forecast_origin")):
        return "FAIL_TIMEZONE"
    if ctx.validate_ordering():
        return "FAIL_SESSION_MAPPING"
    if obs is not None:
        reasons = reject_future_information(obs, ctx.feature_cutoff_timestamp or utc_now())
        if reasons:
            return reasons[0]
    return TEMPORAL_LEAKAGE_OK


def assert_no_future(obs: AsOfObservation, cutoff: datetime) -> None:
    """Dev/test assertion: raise on explicit future leakage (fail closed)."""
    reasons = reject_future_information(obs, cutoff)
    if reasons:
        raise TemporalLeakageError(reasons[0])


class TemporalLeakageError(Exception):
    """Future information would be used. Fail closed in dev/research."""


# ── Data capability registry (§36/§37/§38/§39) ──
# Truthful initial content — based on the V2 AUDIT actual findings (daily only, no 1m/tick/L1/L2).
_CAPABILITY_REGISTRY: dict[str, dict] = {
    "OSAKA_MICRO": {
        "calendar": "OSE_DERIVATIVES", "role": "DIRECT",
        "frequencies": {"TICK": "NO", "1M": "NO", "5M": "NO", "15M": "NO", "30M": "NO", "60M": "NO", "DAILY": "YES"},
        "capabilities": {"OHLCV": "YES(daily)", "TICK": "NO", "L1": "NO", "L2": "NO", "ORDER_EVENT": "NO"},
        "point_in_time_safe": False, "revision_safe": "VINTAGE_NOT_AVAILABLE",
        "availability": "AVAILABLE",
    },
    "TAIWAN_STOCK": {
        "calendar": "XTAI", "role": "DIRECT",
        "frequencies": {"TICK": "NO", "1M": "NO", "5M": "NO", "15M": "NO", "30M": "NO", "60M": "NO", "DAILY": "YES"},
        "capabilities": {"OHLCV": "YES(daily)", "TICK": "NO", "L1": "NO", "L2": "NO", "ORDER_EVENT": "NO"},
        "point_in_time_safe": False, "revision_safe": "REVISION_RISK_PRESENT",
        "availability": "AVAILABLE",
    },
    "TAIWAN_INDEX": {
        "calendar": "XTAI", "role": "DIRECT", "cash_index_executable": False,
        "frequencies": {"TICK": "NO", "1M": "NO", "5M": "NO", "15M": "NO", "30M": "NO", "60M": "NO", "DAILY": "YES"},
        "capabilities": {"OHLCV": "YES(daily)", "TICK": "NO", "L1": "NO", "L2": "NO", "ORDER_EVENT": "NO"},
        "point_in_time_safe": False, "revision_safe": "VINTAGE_NOT_AVAILABLE",
        "availability": "AVAILABLE",
    },
    "^N225": {
        "calendar": "XTKS", "role": "PROXY",
        "frequencies": {"TICK": "NO", "1M": "NO", "5M": "NO", "15M": "NO", "30M": "NO", "60M": "NO", "DAILY": "YES"},
        "capabilities": {"OHLCV": "YES(daily)", "TICK": "NO", "L1": "NO", "L2": "NO", "ORDER_EVENT": "NO"},
        "point_in_time_safe": False, "revision_safe": "VINTAGE_NOT_AVAILABLE",
        "availability": "AVAILABLE",
    },
    # external factors — schema supported, dataset currently NOT_AVAILABLE (§35/§37)
    "NQ": {"frequencies": {f: "NO" for f in FREQUENCY_CAPABILITIES}, "capabilities": {"OHLCV": "NO", "TICK": "NO", "L1": "NO", "L2": "NO", "ORDER_EVENT": "NO"}, "availability": "NOT_AVAILABLE", "point_in_time_safe": False, "revision_safe": "VINTAGE_NOT_AVAILABLE"},
    "ES": {"frequencies": {f: "NO" for f in FREQUENCY_CAPABILITIES}, "capabilities": {"OHLCV": "NO", "TICK": "NO", "L1": "NO", "L2": "NO", "ORDER_EVENT": "NO"}, "availability": "NOT_AVAILABLE", "point_in_time_safe": False, "revision_safe": "VINTAGE_NOT_AVAILABLE"},
    "USDJPY": {"frequencies": {f: "NO" for f in FREQUENCY_CAPABILITIES}, "capabilities": {"OHLCV": "NO", "TICK": "NO", "L1": "NO", "L2": "NO", "ORDER_EVENT": "NO"}, "availability": "NOT_AVAILABLE", "point_in_time_safe": False, "revision_safe": "VINTAGE_NOT_AVAILABLE"},
    "SOX": {"frequencies": {f: "NO" for f in FREQUENCY_CAPABILITIES}, "capabilities": {"OHLCV": "NO", "TICK": "NO", "L1": "NO", "L2": "NO", "ORDER_EVENT": "NO"}, "availability": "NOT_AVAILABLE", "point_in_time_safe": False, "revision_safe": "VINTAGE_NOT_AVAILABLE"},
    "VIX": {"frequencies": {f: "NO" for f in FREQUENCY_CAPABILITIES}, "capabilities": {"OHLCV": "NO", "TICK": "NO", "L1": "NO", "L2": "NO", "ORDER_EVENT": "NO"}, "availability": "NOT_AVAILABLE", "point_in_time_safe": False, "revision_safe": "VINTAGE_NOT_AVAILABLE"},
    "WTI": {"frequencies": {f: "NO" for f in FREQUENCY_CAPABILITIES}, "capabilities": {"OHLCV": "NO", "TICK": "NO", "L1": "NO", "L2": "NO", "ORDER_EVENT": "NO"}, "availability": "NOT_AVAILABLE", "point_in_time_safe": False, "revision_safe": "VINTAGE_NOT_AVAILABLE"},
    "BRENT": {"frequencies": {f: "NO" for f in FREQUENCY_CAPABILITIES}, "capabilities": {"OHLCV": "NO", "TICK": "NO", "L1": "NO", "L2": "NO", "ORDER_EVENT": "NO"}, "availability": "NOT_AVAILABLE", "point_in_time_safe": False, "revision_safe": "VINTAGE_NOT_AVAILABLE"},
    "USTREASURY": {"frequencies": {f: "NO" for f in FREQUENCY_CAPABILITIES}, "capabilities": {"OHLCV": "NO", "TICK": "NO", "L1": "NO", "L2": "NO", "ORDER_EVENT": "NO"}, "availability": "AVAILABLE(daily)", "point_in_time_safe": False, "revision_safe": "VINTAGE_NOT_AVAILABLE"},
    "FRED_MACRO": {"frequencies": {f: "NO" for f in FREQUENCY_CAPABILITIES}, "capabilities": {"OHLCV": "NO", "TICK": "NO", "L1": "NO", "L2": "NO", "ORDER_EVENT": "NO"}, "availability": "AVAILABLE(periodic)", "point_in_time_safe": False, "revision_safe": "REVISION_RISK_PRESENT"},
}

DATA_CAPABILITY_REGISTRY_VERSION = "2A.1"


def data_capability_registry() -> dict:
    return {"version": DATA_CAPABILITY_REGISTRY_VERSION, "targets": _CAPABILITY_REGISTRY}


def supports_capability(target: str, capability: str) -> tuple[bool, str]:
    """§38/§39/§57: return (supported, reason). Capability may be a frequency (1M/DAILY) or a
    data capability (OHLCV/TICK/L1/L2/ORDER_EVENT). Fail closed on missing data."""
    entry = _CAPABILITY_REGISTRY.get(normalize_family(target))
    if entry is None:
        return False, "UNKNOWN_TARGET"
    cap = capability.upper()
    if cap in FREQUENCY_CAPABILITIES:
        v = entry.get("frequencies", {}).get(cap, "NO")
        return (v == "YES"), ("MISSING_DATA_CAPABILITY" if v != "YES" else "OK")
    if cap in DATA_CAPABILITIES:
        v = str(entry.get("capabilities", {}).get(cap, "NO"))
        if v.startswith("YES"):
            return True, "OK"
        return False, "MISSING_DATA_CAPABILITY"
    return False, "UNKNOWN_CAPABILITY"


def require_capability(target: str, capability: str) -> None:
    """§39: fail closed — do NOT auto-downsample/upsample to fake an unavailable capability."""
    ok, reason = supports_capability(target, capability)
    if not ok:
        raise MissingDataCapabilityError(f"{target}/{capability}: {reason} — BLOCKED_MISSING_DATA_CAPABILITY")


class MissingDataCapabilityError(Exception):
    pass


# ── release-time truth (§12/§13) ──
@dataclass
class ReleaseTimeContext:
    release_timestamp: datetime | None = None
    release_status: str = "UNKNOWN"
    revision_status: str = "VINTAGE_NOT_AVAILABLE"
    vintage_status: str = "VINTAGE_NOT_AVAILABLE"

    def __post_init__(self):
        if self.revision_status not in REVISION_STATUS:
            raise ValueError(f"unknown revision_status: {self.revision_status!r}")

    def model_dump(self) -> dict:
        return asdict(self)


def macro_asof_safe(release: ReleaseTimeContext, cutoff: datetime) -> tuple[bool, str]:
    """§12/§13/§50: a macro value whose release is after the cutoff is unusable, and without
    vintage the historical value carries REVISION_RISK_PRESENT."""
    cutoff = ensure_utc_aware(cutoff)
    if release.release_timestamp is not None and ensure_utc_aware(release.release_timestamp) > cutoff:
        return False, "FAIL_RELEASE_AFTER_CUTOFF"
    if release.revision_status in ("VINTAGE_NOT_AVAILABLE", "REVISION_RISK_PRESENT"):
        return True, "REVISION_RISK_PRESENT"
    return True, "OK"


# ── OSE holiday trading / session context helpers (§21) ──
def ose_holiday_session_context(trading_date: str, cash_open: bool, derivatives_open: bool,
                                is_holiday: bool) -> MarketSessionContext:
    """Explicit representation of TSE-cash-closed / OSE-derivatives-open holiday trading."""
    return MarketSessionContext(
        market="OSE_DERIVATIVES", calendar_id="OSE_DERIVATIVES", trading_date=trading_date,
        session_type="HOLIDAY_DAY" if is_holiday else "DAY",
        is_holiday_trading=is_holiday, cash_market_open=cash_open,
        derivatives_market_open=derivatives_open, overnight_session=False,
    )


# ── §29/§30: legacy feature-store as-of bridge (read-only) ──
# Reads the existing DuckDB feature store and wraps rows into AsOfObservation.
# Legacy rows carry LEGACY_TEMPORAL_UNVERIFIED — they are NOT automatically ASOF_VERIFIED.
LEGACY_TEMPORAL_UNVERIFIED = "LEGACY_TEMPORAL_UNVERIFIED"


def read_feature_store_asof(db_path: str | None = None) -> list[AsOfObservation]:
    """Read-only bridge from the existing DuckDB feature store (features table) to AsOfObservation.

    Columns: feature_name, symbol, event_time, available_at, feature_version, source, data_grade, value.
    Rows are tagged LEGACY_TEMPORAL_UNVERIFIED (§29) because they lack full V2 as-of metadata
    (snapshot_id, session_id, staleness, release time). No data is written.
    """
    try:
        import duckdb
    except ImportError:
        return []
    from pathlib import Path
    from market_ai_hub.config.runtime_paths import data_root
    path = db_path or str(data_root() / "feature_store" / "features.duckdb")
    if not Path(path).exists():
        return []
    con = duckdb.connect(path, read_only=True)
    try:
        rows = con.execute(
            "SELECT feature_name, symbol, event_time, available_at, feature_version, source, data_grade, value "
            "FROM features").fetchall()
    finally:
        con.close()
    out: list[AsOfObservation] = []
    for feature_name, symbol, event_time, available_at, fver, source, data_grade, value in rows:
        et = event_time
        if et is not None and et.tzinfo is None:
            et = et.replace(tzinfo=timezone.utc)
        at = available_at
        if at is not None and at.tzinfo is None:
            at = at.replace(tzinfo=timezone.utc)
        out.append(AsOfObservation(
            instrument=str(symbol), provider=str(source), field=str(feature_name), value=value,
            event_timestamp=et, observed_at=at, ingested_at=at, source_timestamp=et,
            frequency="DAILY", availability_status="AVAILABLE",
            quality_status="UNKNOWN",
            provenance={"legacy_status": LEGACY_TEMPORAL_UNVERIFIED,
                        "feature_version": str(fver), "data_grade": str(data_grade)},
        ))
    return out