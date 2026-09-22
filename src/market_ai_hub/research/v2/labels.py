"""V2-C — Daily Multi-Target Label Engine (Touch / Break / Acceptance).

RESEARCH ONLY. Typed daily-barrier label schema + deterministic label generator.

Definitions (DAILY scope, HYPOTHESIS_ONLY, NOT_CALIBRATED, NOT_PUBLIC_PROBABILITY):
- DAILY_TOUCH        : low <= L <= high in some outcome bar (daily OHLC covers L).
- DAILY_CLOSE_BREAK  : close strictly beyond L (UP: close > L, DOWN: close < L).
- DAILY_CLOSE_ACCEPTANCE : N consecutive daily closes beyond L (N=2 research parameter).

Daily OHLC resolution does NOT reconstruct the intraday event chain. No first-passage,
no intraday ordering, no probability, no calibration, no trade signal.
DAILY_OBSERVATION_CHAIN_NOT_ASSUMED.

Schema: V2_DAILY_LABEL_SCHEMA_VERSION = "2C.2"  (independent from 2A.1 / 2B.1 / 3A.2.3)
"""
from __future__ import annotations

from dataclasses import dataclass, field as dfield, asdict
from datetime import datetime
from typing import Any

from market_ai_hub.research.v2.asof import normalize_instrument, normalize_family, ensure_utc_aware

V2_DAILY_LABEL_SCHEMA_VERSION = "2C.2"

# ── enums ──
BARRIER_DIRECTIONS = ("UP", "DOWN")
ROLL_STATUSES = ("NONE", "ROLL_BOUNDARY", "UNKNOWN", "NOT_APPLICABLE")
SERIES_SEMANTICS = ("CONTINUOUS", "CONTRACT", "CASH", "INDEX", "UNKNOWN")
# provenance trust: a plain list / naked float is NOT authoritative by itself
PROVENANCE_STATUS = ("AUTHORITATIVE", "VERIFIED_INPUT", "UNKNOWN")
CALENDAR_PROVENANCE_STATUS = PROVENANCE_STATUS
_PROVENANCE_TRUSTED = ("AUTHORITATIVE", "VERIFIED_INPUT")

# event-level statuses (§12)
EVENT_STATUSES = (
    "OBSERVED_TRUE", "OBSERVED_FALSE", "UNMATURED", "UNOBSERVABLE_MISSING_DATA",
    "AMBIGUOUS_GAP_CROSS", "INVALID_OHLC", "INVALID_BARRIER",
    "BLOCKED_IDENTITY_MISMATCH", "BLOCKED_ROLL_PROVENANCE",
    "BLOCKED_CALENDAR_PROVENANCE", "BLOCKED_TEMPORAL_CONTRACT",
    "BLOCKED_TEMPORAL_SESSION_BOUNDARY", "BLOCKED_BARRIER_PROVENANCE",
    "BLOCKED_PREWINDOW_REFERENCE_PROVENANCE", "BLOCKED_SERIES_SEMANTICS_MISMATCH",
)

BLOCKED_IDENTITY_MISMATCH = "BLOCKED_IDENTITY_MISMATCH"
BLOCKED_ROLL_PROVENANCE = "BLOCKED_ROLL_PROVENANCE"
BLOCKED_CALENDAR_PROVENANCE = "BLOCKED_CALENDAR_PROVENANCE"
BLOCKED_TEMPORAL_CONTRACT = "BLOCKED_TEMPORAL_CONTRACT"
BLOCKED_TEMPORAL_SESSION_BOUNDARY = "BLOCKED_TEMPORAL_SESSION_BOUNDARY"
BLOCKED_BARRIER_PROVENANCE = "BLOCKED_BARRIER_PROVENANCE"
BLOCKED_PREWINDOW_REFERENCE_PROVENANCE = "BLOCKED_PREWINDOW_REFERENCE_PROVENANCE"
BLOCKED_SERIES_SEMANTICS_MISMATCH = "BLOCKED_SERIES_SEMANTICS_MISMATCH"

SERIES_BLOCKS = (BLOCKED_IDENTITY_MISMATCH, BLOCKED_ROLL_PROVENANCE,
                 BLOCKED_CALENDAR_PROVENANCE, BLOCKED_TEMPORAL_CONTRACT,
                 BLOCKED_TEMPORAL_SESSION_BOUNDARY, BLOCKED_BARRIER_PROVENANCE,
                 BLOCKED_SERIES_SEMANTICS_MISMATCH)

# ASOF conservativeness rank (higher = more verified); the summary takes the least-verified
_ASOF_RANK = {"ASOF_VERIFIED": 2, "TEMPORAL_UNVERIFIED": 1, "LEGACY_TEMPORAL_UNVERIFIED": 0}

# ── policy (§20) ──
@dataclass
class DailyLabelPolicy:
    version: str = "2C.2"
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
    label_policy_version: str = "2C.2"
    # previous-window reference (required for Touch-negative gap ruling) — NOT a naked float
    previous_close: float | None = None
    previous_close_available_at: datetime | None = None
    previous_close_source_snapshot_ids: list[str] = dfield(default_factory=list)
    previous_close_provenance: str = "UNKNOWN"

    def __post_init__(self):
        if self.horizon_sessions < 1:
            raise ValueError("horizon_sessions must be >= 1")
        for name in ("feature_cutoff_timestamp", "forecast_origin", "previous_close_available_at"):
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
    eligible_elapsed_sessions: list[str] = dfield(default_factory=list)
    window_sessions: list[str] = dfield(default_factory=list)
    observed_outcome_sessions: list[str] = dfield(default_factory=list)
    missing_outcome_sessions: list[str] = dfield(default_factory=list)
    ignored_out_of_window_sessions: list[str] = dfield(default_factory=list)
    barrier_id: str = ""
    barrier_level: float | None = None
    barrier_direction: str = "UP"
    barrier_available_at: datetime | None = None
    barrier_source: str = ""
    source_snapshot_ids: list[str] = dfield(default_factory=list)
    forecast_source_snapshot_ids: list[str] = dfield(default_factory=list)
    barrier_source_snapshot_ids: list[str] = dfield(default_factory=list)
    outcome_source_snapshot_ids: list[str] = dfield(default_factory=list)
    asof_status: str = "LEGACY_TEMPORAL_UNVERIFIED"
    forecast_asof_status: str = "LEGACY_TEMPORAL_UNVERIFIED"
    barrier_provenance_status: str = "UNKNOWN"
    outcome_asof_status: str = "LEGACY_TEMPORAL_UNVERIFIED"
    roll_status: str = "UNKNOWN"
    series_semantics: str = "UNKNOWN"
    calendar_provenance: str = "UNKNOWN"
    series_block: str = ""
    touch: EventResult = dfield(default_factory=EventResult)
    break_: EventResult = dfield(default_factory=EventResult)
    acceptance: EventResult = dfield(default_factory=EventResult)
    label_schema_version: str = V2_DAILY_LABEL_SCHEMA_VERSION
    label_policy_version: str = "2C.2"
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


def _trusted_previous_close(request: DailyLabelRequest) -> float | None:
    """Trusted pre-window reference requires value + availability + provenance. Naked float ≠ trusted."""
    pc = request.previous_close
    if pc is None or not _finite_positive(pc):
        return None
    if request.previous_close_available_at is None:
        return None
    if request.feature_cutoff_timestamp is not None and \
            ensure_utc_aware(request.previous_close_available_at) > ensure_utc_aware(request.feature_cutoff_timestamp):
        return None
    if request.previous_close_provenance not in _PROVENANCE_TRUSTED:
        return None
    return pc


def _valid_session_list(sessions: list[str]) -> bool:
    """Trusted session list must be unique, strict-chronological ISO dates. No silent sort."""
    import re
    prev = ""
    for s in sessions:
        if not isinstance(s, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
            return False
        if s <= prev:  # duplicate or out-of-order
            return False
        prev = s
    return True


def _least_verified_asof(statuses: list[str]) -> str:
    if not statuses:
        return "LEGACY_TEMPORAL_UNVERIFIED"
    return min(statuses, key=lambda s: _ASOF_RANK.get(s, 0))


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

    Processing order (§20): request timestamps → barrier provenance → trusted session-window →
    expected_sessions validity → H-scoped window → scope bars → empty-elapsed → in-window
    duplicates/identity/series → in-window roll → in-window session boundary → data → evaluate →
    finalize → provenance summaries → snapshot lineage.
    """
    if calendar_provenance not in CALENDAR_PROVENANCE_STATUS:
        raise ValueError(f"unknown calendar_provenance: {calendar_provenance!r}")
    policy = policy or DailyLabelPolicy()
    H = request.horizon_sessions
    res = DailyBarrierLabelResult(
        instrument=request.instrument, target_family=request.target_family,
        instrument_role=request.instrument_role, calendar_id=request.calendar_id,
        feature_cutoff_timestamp=request.feature_cutoff_timestamp,
        forecast_origin=request.forecast_origin, origin_session_date=request.origin_session_date,
        horizon_sessions=H,
        barrier_id=barrier.barrier_id, barrier_level=barrier.level,
        barrier_direction=barrier.direction, barrier_available_at=barrier.barrier_available_at,
        barrier_source=barrier.barrier_source, label_policy_version=policy.version,
        label_schema_version=V2_DAILY_LABEL_SCHEMA_VERSION,
    )

    # 1. temporal contract
    if request.validate_ordering() or request.feature_cutoff_timestamp is None or request.forecast_origin is None:
        res.series_block = BLOCKED_TEMPORAL_CONTRACT
        return _blocked(res)

    # 2. barrier numeric + frozen provenance (§11/§15). barrier_available_at is MANDATORY.
    if barrier.level is None or not _valid_price(barrier.level):
        res.series_block = BLOCKED_BARRIER_PROVENANCE
        res.touch = res.break_ = res.acceptance = EventResult(None, "INVALID_BARRIER", "")
        return res
    if barrier.barrier_available_at is None:
        res.series_block = BLOCKED_BARRIER_PROVENANCE
        return _blocked(res)
    if ensure_utc_aware(barrier.barrier_available_at) > ensure_utc_aware(request.feature_cutoff_timestamp):
        res.series_block = BLOCKED_BARRIER_PROVENANCE
        return _blocked(res)

    # 3. trusted calendar/session-window provenance (REQUIRED for ALL labels incl. positive)
    if calendar_provenance not in _PROVENANCE_TRUSTED or expected_sessions is None:
        res.series_block = BLOCKED_CALENDAR_PROVENANCE
        return _blocked(res)

    # 4. expected_sessions validity (unique, strict-chronological ISO)
    if not _valid_session_list(expected_sessions):
        res.series_block = BLOCKED_CALENDAR_PROVENANCE
        return _blocked(res)

    # 5. canonical window = first H eligible elapsed sessions
    window_sessions = list(expected_sessions)[:H]
    window_set = set(window_sessions)

    # 6. scope input bars to window; everything else is out-of-window (ignored)
    in_window_bars = [b for b in bars if b.trading_date in window_set]
    out_of_window_bars = [b for b in bars if b.trading_date not in window_set]

    res.eligible_elapsed_sessions = list(expected_sessions)
    res.window_sessions = list(window_sessions)
    res.ignored_out_of_window_sessions = [b.trading_date for b in out_of_window_bars]

    # 7. empty elapsed sessions → UNMATURED (NOT session-boundary block)
    if not window_sessions:
        res.touch = res.break_ = res.acceptance = EventResult(None, "UNMATURED", "")
        return res

    # 8. in-window duplicates / identity / series semantics
    in_dates = [b.trading_date for b in in_window_bars]
    if len(in_dates) != len(set(in_dates)):
        res.series_block = BLOCKED_TEMPORAL_CONTRACT
        return _blocked(res, "DUPLICATE_TRADING_SESSION")
    ident_reasons = validate_identity_scope(in_window_bars, request)
    if ident_reasons:
        res.series_block = BLOCKED_IDENTITY_MISMATCH
        return _blocked(res)
    sems = {b.series_semantics for b in in_window_bars}
    if len(sems) > 1:
        res.series_block = BLOCKED_SERIES_SEMANTICS_MISMATCH
        return _blocked(res)
    res.series_semantics = next(iter(sems)) if sems else "UNKNOWN"

    # 9. in-window roll provenance
    is_fut = _is_futures(request.target_family, request.instrument_role)
    for bar in in_window_bars:
        if is_fut:
            if bar.roll_status in ("ROLL_BOUNDARY", "UNKNOWN"):
                res.roll_status = bar.roll_status
                res.series_block = BLOCKED_ROLL_PROVENANCE
                return _blocked(res)
        else:
            if bar.roll_status == "UNKNOWN":
                res.roll_status = bar.roll_status
                res.series_block = BLOCKED_ROLL_PROVENANCE
                return _blocked(res)
    rolls = {b.roll_status for b in in_window_bars}
    res.roll_status = next(iter(rolls)) if len(rolls) == 1 else "UNKNOWN"

    # 10. in-window session boundary (exclude mid-session bars; block if unprovable)
    origin_ts = ensure_utc_aware(request.forecast_origin)
    valid_in_window: list[DailyOutcomeBar] = []
    for bar in in_window_bars:
        if bar.session_open_timestamp is None:
            res.series_block = BLOCKED_TEMPORAL_SESSION_BOUNDARY
            return _blocked(res)
        if ensure_utc_aware(bar.session_open_timestamp) <= origin_ts:
            continue  # mid-session full bar → excluded (never labels a mid-session forecast)
        valid_in_window.append(bar)
    # order validation (in-window, by session open)
    sorted_valid = sorted(valid_in_window, key=lambda b: ensure_utc_aware(b.session_open_timestamp))
    if [b.trading_date for b in sorted_valid] != [b.trading_date for b in valid_in_window]:
        res.series_block = BLOCKED_TEMPORAL_CONTRACT
        return _blocked(res, "INPUT_OUT_OF_ORDER")
    in_window_bars = sorted_valid

    # 11. data quality (in-window)
    any_invalid = any(validate_daily_bar(b) for b in in_window_bars)

    # maturity: H sessions elapsed + no missing in-window session
    observed = {b.trading_date for b in in_window_bars}
    missing = [s for s in window_sessions if s not in observed]
    horizon_elapsed = len(expected_sessions) >= H
    mature = horizon_elapsed and not missing

    res.observed_outcome_sessions = [b.trading_date for b in in_window_bars]
    res.missing_outcome_sessions = missing
    res.outcome_window_start = window_sessions[0]
    res.outcome_window_end = window_sessions[-1]

    # 12. evaluate independently (no event chain assumed)
    trusted_pc = _trusted_previous_close(request)
    touch = _eval_touch(barrier, in_window_bars, trusted_pc)
    break_ = _eval_break(barrier, in_window_bars)
    bar_by_date = {b.trading_date: b for b in in_window_bars}
    acceptance = _eval_acceptance(barrier, window_sessions, bar_by_date, policy.acceptance_consecutive_closes)

    # 13. finalize (touch needs trusted pre-window reference for negative)
    res.touch = _finalize_touch(touch, mature, missing, horizon_elapsed, any_invalid, trusted_pc is not None)
    res.break_ = _finalize(break_, mature, missing, horizon_elapsed, any_invalid)
    res.acceptance = _finalize(acceptance, mature, missing, horizon_elapsed, any_invalid)

    # 14. conservative provenance summaries (§12/§13/§14)
    res.calendar_provenance = calendar_provenance
    res.forecast_asof_status = request.asof_status
    res.barrier_provenance_status = "VERIFIED" if (barrier.barrier_source and barrier.barrier_available_at is not None) else "UNKNOWN"
    res.outcome_asof_status = _least_verified_asof([b.asof_status for b in in_window_bars])
    res.asof_status = _least_verified_asof([res.forecast_asof_status, res.outcome_asof_status])
    res.forecast_source_snapshot_ids = list(request.source_snapshot_ids)
    res.barrier_source_snapshot_ids = list(barrier.source_snapshot_ids)
    res.outcome_source_snapshot_ids = sorted({sid for b in in_window_bars for sid in b.source_snapshot_ids})
    res.source_snapshot_ids = sorted(set(res.forecast_source_snapshot_ids)
                                     | set(res.barrier_source_snapshot_ids)
                                     | set(res.outcome_source_snapshot_ids))

    return res


def _blocked(res: DailyBarrierLabelResult, extra: str = "") -> DailyBarrierLabelResult:
    status = res.series_block or BLOCKED_TEMPORAL_CONTRACT
    res.touch = res.break_ = res.acceptance = EventResult(None, status, "")
    return res


def _finalize(ev: EventResult, mature: bool, missing: list[str], horizon_elapsed: bool,
              any_invalid: bool) -> EventResult:
    """Positive stands; negative only after full horizon + no missing + no invalid (break/acceptance)."""
    if ev.value is True:
        return ev
    if ev.status == "UNOBSERVABLE_MISSING_DATA":
        return ev
    if any_invalid:
        return EventResult(None, "INVALID_OHLC", ev.first_session_date)
    if not horizon_elapsed:
        return EventResult(None, "UNMATURED", "")
    if missing:
        return EventResult(None, "UNOBSERVABLE_MISSING_DATA", "")
    return EventResult(False, "OBSERVED_FALSE", "")


def _finalize_touch(ev: EventResult, mature: bool, missing: list[str], horizon_elapsed: bool,
                    any_invalid: bool, trusted_prev_close: bool) -> EventResult:
    """Touch negative additionally requires a trusted pre-window reference (to rule out gap cross)."""
    if ev.value is True:
        return ev
    if ev.status in ("UNOBSERVABLE_MISSING_DATA", "AMBIGUOUS_GAP_CROSS"):
        return ev
    if any_invalid:
        return EventResult(None, "INVALID_OHLC", ev.first_session_date)
    if not trusted_prev_close:
        return EventResult(None, "BLOCKED_PREWINDOW_REFERENCE_PROVENANCE", "")
    if not horizon_elapsed:
        return EventResult(None, "UNMATURED", "")
    if missing:
        return EventResult(None, "UNOBSERVABLE_MISSING_DATA", "")
    return EventResult(False, "OBSERVED_FALSE", "")