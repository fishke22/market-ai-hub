"""V2-C — Daily Multi-Target Label Engine (Touch / Break / Acceptance).

RESEARCH ONLY. Typed daily-barrier label schema + deterministic label generator.

Definitions (DAILY scope, HYPOTHESIS_ONLY, NOT_CALIBRATED, NOT_PUBLIC_PROBABILITY):
- DAILY_TOUCH        : low <= L <= high in some outcome bar (daily OHLC covers L).
- DAILY_CLOSE_BREAK  : close strictly beyond L (UP: close > L, DOWN: close < L).
- DAILY_CLOSE_ACCEPTANCE : N consecutive daily closes beyond L (N=2 research parameter).

Daily OHLC resolution does NOT reconstruct the intraday event chain. No first-passage,
no intraday ordering, no probability, no calibration, no trade signal.
DAILY_OBSERVATION_CHAIN_NOT_ASSUMED.

Schema: V2_DAILY_LABEL_SCHEMA_VERSION = "2C.1"  (independent from 2A.1 / 2B.1 / 3A.2.3)
"""
from __future__ import annotations

from dataclasses import dataclass, field as dfield, asdict
from datetime import datetime, timezone
from typing import Any

from market_ai_hub.research.v2.asof import normalize_instrument, normalize_family, ensure_utc_aware

V2_DAILY_LABEL_SCHEMA_VERSION = "2C.1"

# ── enums ──
BARRIER_DIRECTIONS = ("UP", "DOWN")
ROLL_STATUSES = ("NONE", "ROLL_BOUNDARY", "UNKNOWN", "NOT_APPLICABLE")
SERIES_SEMANTICS = ("CONTINUOUS", "CONTRACT", "CASH", "INDEX", "UNKNOWN")
# calendar provenance trust (§C): a plain expected_sessions list is NOT authoritative by itself
CALENDAR_PROVENANCE_STATUS = ("AUTHORITATIVE", "VERIFIED_INPUT", "UNKNOWN")
_CALENDAR_TRUSTED = ("AUTHORITATIVE", "VERIFIED_INPUT")

# event-level statuses (§12)
EVENT_STATUSES = (
    "OBSERVED_TRUE", "OBSERVED_FALSE", "UNMATURED", "UNOBSERVABLE_MISSING_DATA",
    "AMBIGUOUS_GAP_CROSS", "INVALID_OHLC", "INVALID_BARRIER",
    "BLOCKED_IDENTITY_MISMATCH", "BLOCKED_ROLL_PROVENANCE",
    "BLOCKED_CALENDAR_PROVENANCE", "BLOCKED_TEMPORAL_CONTRACT",
    "BLOCKED_TEMPORAL_SESSION_BOUNDARY",
)

BLOCKED_IDENTITY_MISMATCH = "BLOCKED_IDENTITY_MISMATCH"
BLOCKED_ROLL_PROVENANCE = "BLOCKED_ROLL_PROVENANCE"
BLOCKED_CALENDAR_PROVENANCE = "BLOCKED_CALENDAR_PROVENANCE"
BLOCKED_TEMPORAL_CONTRACT = "BLOCKED_TEMPORAL_CONTRACT"
BLOCKED_TEMPORAL_SESSION_BOUNDARY = "BLOCKED_TEMPORAL_SESSION_BOUNDARY"

SERIES_BLOCKS = (BLOCKED_IDENTITY_MISMATCH, BLOCKED_ROLL_PROVENANCE,
                 BLOCKED_CALENDAR_PROVENANCE, BLOCKED_TEMPORAL_CONTRACT,
                 BLOCKED_TEMPORAL_SESSION_BOUNDARY)

# ── policy (§20) ──
@dataclass
class DailyLabelPolicy:
    version: str = "2C.1"
    scope: str = "DAILY"
    validation_status: str = "HYPOTHESIS_ONLY"
    acceptance_definition: str = "N_CONSECUTIVE_DAILY_CLOSES_BEYOND_BARRIER"
    acceptance_consecutive_closes: int = 2

    def __post_init__(self):
        if self.acceptance_consecutive_closes < 1:
            raise ValueError("acceptance_consecutive_closes must be >= 1")

    def model_dump(self) -> dict:
        return asdict(self)


# ── barrier spec (§7B) ──
@dataclass
class BarrierSpec:
    barrier_id: str = ""
    level: float | None = None
    direction: str = "UP"
    barrier_source: str = ""
    barrier_available_at: datetime | None = None
    source_snapshot_ids: list[str] = dfield(default_factory=list)
    definition_version: str = "2C.1"

    def __post_init__(self):
        if self.direction not in BARRIER_DIRECTIONS:
            raise ValueError(f"unknown barrier direction: {self.direction!r}")
        if self.level is not None:
            if not _finite_positive(self.level):
                raise ValueError(f"barrier level must be finite and > 0: {self.level!r}")
        if self.barrier_available_at is not None and self.barrier_available_at.tzinfo is None:
            raise ValueError("barrier_available_at must be tz-aware")

    def model_dump(self) -> dict:
        return asdict(self)


# ── label request (§7A) ──
@dataclass
class DailyLabelRequest:
    instrument: str = ""
    target_family: str = ""
    instrument_role: str = "DIRECT"
    calendar_id: str = ""
    feature_cutoff_timestamp: datetime | None = None
    forecast_origin: datetime | None = None
    origin_session_date: str = ""
    horizon_sessions: int = 1
    source_snapshot_ids: list[str] = dfield(default_factory=list)
    asof_status: str = "LEGACY_TEMPORAL_UNVERIFIED"
    label_policy_version: str = "2C.1"
    previous_close: float | None = None

    def __post_init__(self):
        if self.horizon_sessions < 1:
            raise ValueError("horizon_sessions must be >= 1")
        for name in ("feature_cutoff_timestamp", "forecast_origin"):
            v = getattr(self, name)
            if v is not None and v.tzinfo is None:
                raise ValueError(f"{name} must be tz-aware")

    def validate_ordering(self) -> list[str]:
        reasons = []
        if self.feature_cutoff_timestamp and self.forecast_origin \
                and self.feature_cutoff_timestamp > self.forecast_origin:
            reasons.append("CUTOFF_AFTER_ORIGIN")
        return reasons

    def model_dump(self) -> dict:
        return asdict(self)


# ── daily outcome bar (§7C) ──
@dataclass
class DailyOutcomeBar:
    instrument: str = ""
    target_family: str = ""
    instrument_role: str = "DIRECT"
    calendar_id: str = ""
    trading_date: str = ""
    session_open_timestamp: datetime | None = None
    session_close_timestamp: datetime | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    source_snapshot_ids: list[str] = dfield(default_factory=list)
    asof_status: str = "LEGACY_TEMPORAL_UNVERIFIED"
    roll_status: str = "UNKNOWN"
    series_semantics: str = "UNKNOWN"

    def __post_init__(self):
        if self.roll_status not in ROLL_STATUSES:
            raise ValueError(f"unknown roll_status: {self.roll_status!r}")
        if self.series_semantics not in SERIES_SEMANTICS:
            raise ValueError(f"unknown series_semantics: {self.series_semantics!r}")
        for name in ("session_open_timestamp", "session_close_timestamp"):
            v = getattr(self, name)
            if v is not None and v.tzinfo is None:
                raise ValueError(f"{name} must be tz-aware")

    def model_dump(self) -> dict:
        return asdict(self)


# ── event result ──
@dataclass
class EventResult:
    value: bool | None = None
    status: str = "UNMATURED"
    first_session_date: str = ""

    def model_dump(self) -> dict:
        return asdict(self)


# ── canonical result ──
@dataclass
class DailyBarrierLabelResult:
    instrument: str = ""
    target_family: str = ""
    instrument_role: str = "DIRECT"
    calendar_id: str = ""
    frequency: str = "DAILY"
    feature_cutoff_timestamp: datetime | None = None
    forecast_origin: datetime | None = None
    origin_session_date: str = ""
    outcome_window_start: str = ""
    outcome_window_end: str = ""
    horizon_sessions: int = 1
    expected_outcome_sessions: list[str] = dfield(default_factory=list)
    observed_outcome_sessions: list[str] = dfield(default_factory=list)
    missing_outcome_sessions: list[str] = dfield(default_factory=list)
    barrier_id: str = ""
    barrier_level: float | None = None
    barrier_direction: str = "UP"
    barrier_available_at: datetime | None = None
    barrier_source: str = ""
    source_snapshot_ids: list[str] = dfield(default_factory=list)
    asof_status: str = "LEGACY_TEMPORAL_UNVERIFIED"
    roll_status: str = "UNKNOWN"
    series_semantics: str = "UNKNOWN"
    calendar_provenance: str = "UNKNOWN"
    series_block: str = ""
    touch: EventResult = dfield(default_factory=EventResult)
    break_: EventResult = dfield(default_factory=EventResult)
    acceptance: EventResult = dfield(default_factory=EventResult)
    label_schema_version: str = V2_DAILY_LABEL_SCHEMA_VERSION
    label_policy_version: str = "2C.1"
    scope: str = "DAILY"
    validation_status: str = "HYPOTHESIS_ONLY"
    calibration_status: str = "NOT_CALIBRATED"
    public_probability_status: str = "NOT_PUBLIC_PROBABILITY"
    path_order_status: str = "UNKNOWN_WITHIN_DAILY_BAR"

    def model_dump(self) -> dict:
        d = asdict(self)
        d["break"] = d.pop("break_")
        return d


# ── helpers ──
def _finite_positive(x: float) -> bool:
    import math
    return isinstance(x, (int, float)) and math.isfinite(x) and x > 0


def _valid_price(x: float | None) -> bool:
    return x is not None and _finite_positive(x)


# ── validation (§13) ──
def validate_daily_bar(bar: DailyOutcomeBar) -> list[str]:
    """Return OHLC quality reason codes. Empty list == valid."""
    reasons = []
    for name in ("open", "high", "low", "close"):
        v = getattr(bar, name)
        if v is None:
            reasons.append(f"MISSING_{name.upper()}")
        elif not _finite_positive(v):
            reasons.append(f"INVALID_{name.upper()}")
    if not reasons:
        if bar.low > bar.high:
            reasons.append("LOW_GT_HIGH")
        if bar.open is not None and bar.high is not None and bar.low is not None:
            if not (bar.low <= bar.open <= bar.high):
                reasons.append("OPEN_OUTSIDE_RANGE")
        if bar.close is not None and bar.high is not None and bar.low is not None:
            if not (bar.low <= bar.close <= bar.high):
                reasons.append("CLOSE_OUTSIDE_RANGE")
    return reasons


def validate_identity_scope(bars: list[DailyOutcomeBar], request: DailyLabelRequest) -> list[str]:
    """§P4: instrument/family/role/calendar must be consistent across the series and the request."""
    reasons = []
    keys = ("instrument", "target_family", "instrument_role", "calendar_id")
    for b in bars:
        if normalize_instrument(b.instrument) != normalize_instrument(request.instrument):
            reasons.append("INSTRUMENT_MISMATCH")
        if normalize_family(b.target_family) != normalize_family(request.target_family):
            reasons.append("TARGET_FAMILY_MISMATCH")
        if b.instrument_role != request.instrument_role:
            reasons.append("INSTRUMENT_ROLE_MISMATCH")
        if b.calendar_id != request.calendar_id:
            reasons.append("CALENDAR_MISMATCH")
    # cross-bar consistency
    ref = bars[0] if bars else None
    for b in bars:
        if ref is not None:
            if normalize_instrument(b.instrument) != normalize_instrument(ref.instrument):
                reasons.append("SERIES_INSTRUMENT_MIXED")
            if normalize_family(b.target_family) != normalize_family(ref.target_family):
                reasons.append("SERIES_FAMILY_MIXED")
            if b.instrument_role != ref.instrument_role:
                reasons.append("SERIES_ROLE_MIXED")
            if b.calendar_id != ref.calendar_id:
                reasons.append("SERIES_CALENDAR_MIXED")
    return sorted(set(reasons))


def _is_futures(target_family: str, instrument_role: str) -> bool:
    return normalize_family(target_family) == "OSAKA_MICRO" and instrument_role == "DIRECT"


# ── evaluation ──
def _eval_touch(barrier: BarrierSpec, bars: list[DailyOutcomeBar],
                previous_close: float | None) -> EventResult:
    L = barrier.level
    prev = previous_close
    gap_cross = False
    for bar in bars:
        if L is not None and _valid_price(bar.low) and _valid_price(bar.high):
            if bar.low <= L <= bar.high:
                return EventResult(True, "OBSERVED_TRUE", bar.trading_date)
        if prev is not None:
            if barrier.direction == "UP" and prev < L and _valid_price(bar.low) and bar.low > L:
                gap_cross = True
            elif barrier.direction == "DOWN" and prev > L and _valid_price(bar.high) and bar.high < L:
                gap_cross = True
        if _valid_price(bar.close):
            prev = bar.close
    # no positive found — maturity/gap handled by caller via status
    if gap_cross:
        return EventResult(None, "AMBIGUOUS_GAP_CROSS", "")
    return EventResult(None, "UNMATURED", "")  # placeholder; caller overrides to OBSERVED_FALSE when mature


def _eval_break(barrier: BarrierSpec, bars: list[DailyOutcomeBar]) -> EventResult:
    L = barrier.level
    unobservable = False
    for bar in bars:
        if not _valid_price(bar.close):
            unobservable = True
            continue
        if barrier.direction == "UP" and bar.close > L:
            return EventResult(True, "OBSERVED_TRUE", bar.trading_date)
        if barrier.direction == "DOWN" and bar.close < L:
            return EventResult(True, "OBSERVED_TRUE", bar.trading_date)
    if unobservable:
        return EventResult(None, "UNOBSERVABLE_MISSING_DATA", "")
    return EventResult(None, "UNMATURED", "")


def _eval_acceptance(barrier: BarrierSpec, ordered_sessions: list[str],
                     bar_by_date: dict[str, DailyOutcomeBar], n: int) -> EventResult:
    L = barrier.level
    run = 0
    unobservable = False
    for s in ordered_sessions:
        bar = bar_by_date.get(s)
        if bar is None:
            run = 0  # missing session breaks consecutive run
            unobservable = True
            continue
        if not _valid_price(bar.close):
            run = 0
            unobservable = True
            continue
        beyond = (barrier.direction == "UP" and bar.close > L) or \
                 (barrier.direction == "DOWN" and bar.close < L)
        if beyond:
            run += 1
            if run >= n:
                return EventResult(True, "OBSERVED_TRUE", s)
        else:
            run = 0
    if unobservable:
        return EventResult(None, "UNOBSERVABLE_MISSING_DATA", "")
    return EventResult(None, "UNMATURED", "")


def build_daily_barrier_labels(
    request: DailyLabelRequest,
    barrier: BarrierSpec,
    bars: list[DailyOutcomeBar],
    policy: DailyLabelPolicy | None = None,
    expected_sessions: list[str] | None = None,
    calendar_provenance: str = "UNKNOWN",
) -> DailyBarrierLabelResult:
    """Core V2-C engine. Fail closed on any series-level blocker.

    `expected_sessions` alone is NOT authoritative calendar provenance; the caller must also
    declare `calendar_provenance` (AUTHORITATIVE / VERIFIED_INPUT) for negative labels to resolve.
    """
    if calendar_provenance not in CALENDAR_PROVENANCE_STATUS:
        raise ValueError(f"unknown calendar_provenance: {calendar_provenance!r}")
    policy = policy or DailyLabelPolicy()
    res = DailyBarrierLabelResult(
        instrument=request.instrument, target_family=request.target_family,
        instrument_role=request.instrument_role, calendar_id=request.calendar_id,
        feature_cutoff_timestamp=request.feature_cutoff_timestamp,
        forecast_origin=request.forecast_origin, origin_session_date=request.origin_session_date,
        horizon_sessions=request.horizon_sessions, asof_status=request.asof_status,
        source_snapshot_ids=list(request.source_snapshot_ids),
        barrier_id=barrier.barrier_id, barrier_level=barrier.level,
        barrier_direction=barrier.direction, barrier_available_at=barrier.barrier_available_at,
        barrier_source=barrier.barrier_source, label_policy_version=policy.version,
    )

    # 1. temporal contract
    if request.validate_ordering():
        res.series_block = BLOCKED_TEMPORAL_CONTRACT
        return _blocked(res)
    if request.feature_cutoff_timestamp is None or request.forecast_origin is None:
        res.series_block = BLOCKED_TEMPORAL_CONTRACT
        return _blocked(res)

    # 2. barrier frozen as-of (§7B / §16)
    if barrier.level is None or not _valid_price(barrier.level):
        res.series_block = BLOCKED_TEMPORAL_CONTRACT  # invalid barrier
        res.touch = res.break_ = res.acceptance = EventResult(None, "INVALID_BARRIER", "")
        return res
    if barrier.barrier_available_at is not None and \
            ensure_utc_aware(barrier.barrier_available_at) > ensure_utc_aware(request.feature_cutoff_timestamp):
        res.series_block = BLOCKED_TEMPORAL_CONTRACT
        res.touch = res.break_ = res.acceptance = EventResult(None, "INVALID_BARRIER", "")
        return res

    # 3. duplicate trading sessions (§14)
    dates = [b.trading_date for b in bars]
    if len(dates) != len(set(dates)):
        res.series_block = BLOCKED_TEMPORAL_CONTRACT
        return _blocked(res, "DUPLICATE_TRADING_SESSION")

    # 4. identity scope (§P4 / §17)
    ident_reasons = validate_identity_scope(bars, request)
    if ident_reasons:
        res.series_block = BLOCKED_IDENTITY_MISMATCH
        return _blocked(res)

    # 5. roll provenance (§P5 / §21)
    is_fut = _is_futures(request.target_family, request.instrument_role)
    for bar in bars:
        if is_fut:
            if bar.roll_status == "ROLL_BOUNDARY" or bar.roll_status == "UNKNOWN":
                res.roll_status = bar.roll_status
                res.series_block = BLOCKED_ROLL_PROVENANCE
                return _blocked(res)
        # non-futures: NOT_APPLICABLE or NONE acceptable; UNKNOWN on non-futures also blocks (no silent NONE)
        else:
            if bar.roll_status == "UNKNOWN":
                res.roll_status = bar.roll_status
                res.series_block = BLOCKED_ROLL_PROVENANCE
                return _blocked(res)

    # 6. session boundary (§8): exclude mid-session bars; block if boundary unprovable
    cutoff_ts = ensure_utc_aware(request.feature_cutoff_timestamp)
    origin_ts = ensure_utc_aware(request.forecast_origin)
    outcome_bars: list[DailyOutcomeBar] = []
    for bar in bars:
        if bar.session_open_timestamp is not None:
            so = ensure_utc_aware(bar.session_open_timestamp)
            if so <= origin_ts:
                continue  # mid-session bar, exclude
            outcome_bars.append(bar)
        else:
            # cannot prove session open is after forecast_origin
            res.series_block = BLOCKED_TEMPORAL_SESSION_BOUNDARY
            return _blocked(res)
    if not outcome_bars:
        res.series_block = BLOCKED_TEMPORAL_SESSION_BOUNDARY
        return _blocked(res)

    # 7. order validation (§14)
    sorted_bars = sorted(outcome_bars, key=lambda b: b.session_open_timestamp or datetime.min.replace(tzinfo=timezone.utc))
    if [b.trading_date for b in sorted_bars] != [b.trading_date for b in outcome_bars]:
        # caller provided out-of-order; fail closed (no silent sort)
        res.series_block = BLOCKED_TEMPORAL_CONTRACT
        return _blocked(res, "INPUT_OUT_OF_ORDER")
    outcome_bars = sorted_bars

    # 8. maturity + expected sessions
    # Negative labels require BOTH an authoritative expected-session list AND trusted calendar
    # provenance. A plain list with calendar_provenance=UNKNOWN is not authoritative.
    calendar_known = (expected_sessions is not None) and (calendar_provenance in _CALENDAR_TRUSTED)
    if not calendar_known:
        ordered_sessions = [b.trading_date for b in outcome_bars]
        mature = False
        missing: list[str] = []
        horizon_elapsed = False
    else:
        observed = {b.trading_date for b in outcome_bars}
        missing = [s for s in expected_sessions if s not in observed]
        horizon_elapsed = len(expected_sessions) >= request.horizon_sessions
        mature = horizon_elapsed and not missing
        ordered_sessions = expected_sessions

    res.expected_outcome_sessions = list(expected_sessions) if expected_sessions is not None else []
    res.observed_outcome_sessions = [b.trading_date for b in outcome_bars]
    res.missing_outcome_sessions = missing
    res.calendar_provenance = calendar_provenance
    res.outcome_window_start = outcome_bars[0].trading_date
    res.outcome_window_end = outcome_bars[-1].trading_date

    # 9. per-barrier OHLC validation → invalid bars block negative conclusions
    any_invalid = False
    for bar in outcome_bars:
        if validate_daily_bar(bar):
            any_invalid = True
            break

    # 10. evaluate each label independently (no event chain assumed)
    touch = _eval_touch(barrier, outcome_bars, request.previous_close)
    break_ = _eval_break(barrier, outcome_bars)
    bar_by_date = {b.trading_date: b for b in outcome_bars}
    acceptance = _eval_acceptance(barrier, ordered_sessions, bar_by_date, policy.acceptance_consecutive_closes)

    res.touch = _finalize(touch, mature, missing, horizon_elapsed, any_invalid, calendar_known)
    res.break_ = _finalize(break_, mature, missing, horizon_elapsed, any_invalid, calendar_known)
    res.acceptance = _finalize(acceptance, mature, missing, horizon_elapsed, any_invalid, calendar_known)

    return res


def _finalize(ev: EventResult, mature: bool, missing: list[str], horizon_elapsed: bool,
              any_invalid: bool, calendar_known: bool) -> EventResult:
    """Positive events stand; negative only after full horizon + calendar provenance + no missing."""
    if ev.value is True:
        return ev
    # observed issues independent of calendar (missing data / gap ambiguity)
    if ev.status in ("UNOBSERVABLE_MISSING_DATA", "AMBIGUOUS_GAP_CROSS", "INVALID_OHLC"):
        return ev
    # no positive found:
    if any_invalid:
        return EventResult(None, "INVALID_OHLC", ev.first_session_date)
    if not calendar_known:
        return EventResult(None, "BLOCKED_CALENDAR_PROVENANCE", "")
    if not horizon_elapsed:
        return EventResult(None, "UNMATURED", "")
    if missing:
        return EventResult(None, "UNOBSERVABLE_MISSING_DATA", "")
    return EventResult(False, "OBSERVED_FALSE", "")


def _blocked(res: DailyBarrierLabelResult, extra: str = "") -> DailyBarrierLabelResult:
    status = res.series_block or BLOCKED_TEMPORAL_CONTRACT
    res.touch = res.break_ = res.acceptance = EventResult(None, status, "")
    return res