"""V2-B — Daily Gap / Overnight decomposition + session truth (versioned typed schema).

RESEARCH ONLY. Daily OHLC decomposition, gap classification, calendar-aware previous session,
holiday/roll semantics. No fitting, no intraday fabrication, no public probability, no trade signal.

Daily OHLC limitation (§22): with only open/high/low/close we know high/low happened sometime
during the session, but NOT whether high came before low. Therefore this module NEVER builds
first-passage / touch / acceptance sequences or reversal timing.

Schema: V2_GAP_SESSION_SCHEMA_VERSION = "2B.1"  (independent from V2-A 2A.1 and PPM 3A.2.3)
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, date
from typing import Any

V2_GAP_SESSION_SCHEMA_VERSION = "2B.1"

# ── enums ──
GAP_EVENTS = ("GAP_UP", "GAP_DOWN", "FLAT_GAP", "UNRESOLVED")
GAP_SESSION_OUTCOMES = ("GAP_UP_CONTINUATION", "GAP_UP_FADE", "GAP_DOWN_CONTINUATION",
                        "GAP_DOWN_RECOVERY", "MIXED", "UNRESOLVED")
ASOF_STATUSES = ("ASOF_VERIFIED", "LEGACY_TEMPORAL_UNVERIFIED", "TEMPORAL_UNVERIFIED")
HOLIDAY_STATUSES = ("REGULAR", "HOLIDAY_TRADING", "CASH_CLOSED", "UNKNOWN")
ROLL_STATUSES = ("NONE", "ROLL_BOUNDARY", "UNKNOWN")
GAP_INTERPRETATION = ("COMPARABLE", "NOT_COMPARABLE", "MISSING_OPEN", "MISSING_PREVIOUS_CLOSE")

# ── policy (§8) — all thresholds are RESEARCH_PARAMETER / OOS_VALIDATION_REQUIRED, never "optimal" ──
@dataclass
class GapSessionPolicy:
    version: str = V2_GAP_SESSION_SCHEMA_VERSION
    flat_gap_threshold: float = 0.001        # |overnight gap| below this → FLAT_GAP
    continuation_threshold: float = 0.0       # session return >= this on a gap → continuation
    fade_threshold: float = 0.0               # session return below this on a gap → fade
    validation_status: str = "OOS_VALIDATION_REQUIRED"
    parameter_class: str = "RESEARCH_PARAMETER"

    def model_dump(self) -> dict:
        return asdict(self)


# ── decomposition (§5/§6) ──
@dataclass
class GapDecomposition:
    overnight_gap_return: float | None = None
    session_return: float | None = None
    close_to_close_return: float | None = None
    identity_ok: bool = False
    identity_error: float | None = None

    def model_dump(self) -> dict:
        return asdict(self)


def decompose(previous_close: float | None, open_: float | None,
              close: float | None, tolerance: float = 1e-6) -> GapDecomposition:
    """§5: (1+overnight_gap_return)*(1+session_return) == 1+close_to_close_return (floating tol)."""
    if not previous_close or not open_ or not close:
        return GapDecomposition()
    if previous_close <= 0 or open_ <= 0 or close <= 0:
        return GapDecomposition()
    overnight = open_ / previous_close - 1.0
    session = close / open_ - 1.0
    c2c = close / previous_close - 1.0
    identity_error = abs((1 + overnight) * (1 + session) - (1 + c2c))
    return GapDecomposition(
        overnight_gap_return=overnight, session_return=session, close_to_close_return=c2c,
        identity_ok=identity_error <= tolerance, identity_error=identity_error,
    )


# ── classification (§7) ──
def classify_gap(overnight_gap_return: float | None, policy: GapSessionPolicy) -> str:
    if overnight_gap_return is None:
        return "UNRESOLVED"
    if abs(overnight_gap_return) < policy.flat_gap_threshold:
        return "FLAT_GAP"
    return "GAP_UP" if overnight_gap_return > 0 else "GAP_DOWN"


def classify_session_outcome(gap: str, session_return: float | None,
                             policy: GapSessionPolicy) -> str:
    if gap == "UNRESOLVED" or session_return is None:
        return "UNRESOLVED"
    if gap == "FLAT_GAP":
        return "MIXED"
    if gap == "GAP_UP":
        return "GAP_UP_CONTINUATION" if session_return >= policy.continuation_threshold else "GAP_UP_FADE"
    if gap == "GAP_DOWN":
        return "GAP_DOWN_CONTINUATION" if session_return <= policy.fade_threshold else "GAP_DOWN_RECOVERY"
    return "UNRESOLVED"


# ── calendar-aware previous session (§17) ──
def previous_trading_session(trading_date: str, calendar_id: str) -> str:
    """Previous legal trading session strictly before `trading_date`, via exchange calendar.

    Never `calendar date - 1`. Returns "" if the calendar is unavailable."""
    try:
        import exchange_calendars as xcals
    except Exception:
        return ""
    cal_map = {"XTAI": "XTAI", "XTKS": "XTKS", "OSE_DERIVATIVES": "XTKS"}
    cal_name = cal_map.get(calendar_id)
    if not cal_name:
        return ""
    try:
        cal = xcals.get_calendar(cal_name)
    except Exception:
        return ""
    import pandas as pd
    ts = pd.Timestamp(trading_date)
    end = ts - pd.Timedelta(days=1)
    start = ts - pd.Timedelta(days=30)
    if cal.last_session is not None:
        start = max(start, pd.Timestamp(cal.first_session))
    sched = [d for d in cal.sessions_in_range(start, end)]
    return sched[-1].strftime("%Y-%m-%d") if sched else ""


# ── canonical record (§14/§27) ──
@dataclass
class DailyGapSessionRecord:
    instrument: str = ""
    target_family: str = ""
    instrument_role: str = "DIRECT"
    calendar_id: str = ""
    trading_date: str = ""
    previous_trading_date: str = ""
    session_date: str = ""
    holiday_status: str = "UNKNOWN"
    previous_close: float | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    close: float | None = None
    source_snapshot_ids: list[str] = field(default_factory=list)
    feature_cutoff_timestamp: datetime | None = None
    asof_status: str = "LEGACY_TEMPORAL_UNVERIFIED"
    roll_status: str = "NONE"
    series_semantics: str = ""
    cash_reference_status: str = ""
    basis_comparability: str = ""
    policy_version: str = V2_GAP_SESSION_SCHEMA_VERSION
    created_at: str = ""

    # derived (computed by builder)
    overnight_gap_return: float | None = None
    session_return: float | None = None
    close_to_close_return: float | None = None
    open_to_high: float | None = None
    open_to_low: float | None = None
    close_location_in_range: float | None = None
    range_size: float | None = None
    gap_classification: str = "UNRESOLVED"
    session_outcome: str = "UNRESOLVED"
    gap_interpretation: str = "COMPARABLE"
    missing_open: bool = False
    missing_previous_close: bool = False
    temporal_evidence_status: str = "LEGACY_TEMPORAL_UNVERIFIED"
    public_evidence_status: str = "NOT_VALIDATED"

    def __post_init__(self):
        if self.holiday_status not in HOLIDAY_STATUSES:
            raise ValueError(f"unknown holiday_status: {self.holiday_status!r}")
        if self.asof_status not in ASOF_STATUSES:
            raise ValueError(f"unknown asof_status: {self.asof_status!r}")
        if self.roll_status not in ROLL_STATUSES:
            raise ValueError(f"unknown roll_status: {self.roll_status!r}")
        if self.gap_classification not in GAP_EVENTS:
            raise ValueError(f"unknown gap_classification: {self.gap_classification!r}")
        if self.session_outcome not in GAP_SESSION_OUTCOMES:
            raise ValueError(f"unknown session_outcome: {self.session_outcome!r}")

    @property
    def has_gap(self) -> bool:
        return self.overnight_gap_return is not None and not self.missing_open \
            and not self.missing_previous_close

    def model_dump(self) -> dict:
        return asdict(self)


def _safe_ratio(num: float | None, den: float | None) -> float | None:
    if num is None or den is None or den == 0:
        return None
    return num / den


def build_gap_session_record(
    instrument: str, target_family: str, calendar_id: str,
    trading_date: str, previous_close: float | None, open_: float | None, close: float | None,
    *, high: float | None = None, low: float | None = None,
    previous_trading_date: str = "", instrument_role: str = "DIRECT",
    holiday_status: str = "UNKNOWN", roll_status: str = "NONE",
    asof_status: str = "LEGACY_TEMPORAL_UNVERIFIED",
    cash_reference_status: str = "", basis_comparability: str = "",
    policy: GapSessionPolicy | None = None,
    source_snapshot_ids: list[str] | None = None,
    feature_cutoff_timestamp: datetime | None = None,
) -> DailyGapSessionRecord:
    """Build a daily gap/session record; fail closed on missing open / previous close (§18/§19)."""
    policy = policy or GapSessionPolicy()
    rec = DailyGapSessionRecord(
        instrument=instrument, target_family=target_family, instrument_role=instrument_role,
        calendar_id=calendar_id, trading_date=trading_date,
        previous_trading_date=previous_trading_date, session_date=trading_date,
        holiday_status=holiday_status, previous_close=previous_close, open=open_,
        high=high, low=low, close=close,
        source_snapshot_ids=list(source_snapshot_ids or []),
        feature_cutoff_timestamp=feature_cutoff_timestamp, asof_status=asof_status,
        roll_status=roll_status, policy_version=policy.version,
        cash_reference_status=cash_reference_status, basis_comparability=basis_comparability,
        created_at=datetime.now(timezone.utc).isoformat(),
        temporal_evidence_status=asof_status,
        public_evidence_status="NOT_VALIDATED",
    )
    rec.missing_open = open_ is None or open_ <= 0
    rec.missing_previous_close = previous_close is None or previous_close <= 0

    if rec.missing_open:
        rec.gap_interpretation = "MISSING_OPEN"
        return rec
    if rec.missing_previous_close:
        rec.gap_interpretation = "MISSING_PREVIOUS_CLOSE"
        return rec

    # roll boundary → not a real overnight market gap (§21)
    if roll_status == "ROLL_BOUNDARY":
        rec.gap_interpretation = "NOT_COMPARABLE"
        return rec

    d = decompose(previous_close, open_, close)
    rec.overnight_gap_return = d.overnight_gap_return
    rec.session_return = d.session_return
    rec.close_to_close_return = d.close_to_close_return
    rec.gap_classification = classify_gap(d.overnight_gap_return, policy)
    rec.session_outcome = classify_session_outcome(rec.gap_classification, d.session_return, policy)

    # high/low context (§6) — NOT intraday path, only OHLC location
    if high is not None and low is not None and high >= low and open_ > 0:
        rec.open_to_high = high - open_
        rec.open_to_low = low - open_
        rec.range_size = high - low
        if rec.range_size > 0 and close is not None:
            rec.close_location_in_range = (close - low) / rec.range_size

    return rec


# ── research summary (§24/§25) — descriptive only, never public probability ──
@dataclass
class GapSessionResearchSummary:
    count: int = 0
    mean_overnight_gap: float | None = None
    median_overnight_gap: float | None = None
    std_overnight_gap: float | None = None
    quantiles: dict = field(default_factory=dict)
    gap_up_count: int = 0
    gap_down_count: int = 0
    flat_gap_count: int = 0
    continuation_count: int = 0
    fade_count: int = 0
    recovery_count: int = 0
    evidence_class: str = "DESCRIPTIVE_HISTORICAL_RATE"
    calibration_status: str = "NOT_CALIBRATED"
    public_probability_status: str = "NOT_PUBLIC_PROBABILITY"
    sample_sufficiency: str = "INSUFFICIENT_SAMPLE"

    def model_dump(self) -> dict:
        return asdict(self)


def summarize_gaps(records: list[DailyGapSessionRecord],
                   min_sample: int = 20) -> GapSessionResearchSummary:
    """Descriptive historical summary. Never emits a public probability (§24/§25/§26)."""
    gaps = [r.overnight_gap_return for r in records if r.has_gap and r.overnight_gap_return is not None]
    s = GapSessionResearchSummary(count=len(gaps))
    if not gaps:
        return s
    import statistics
    s.mean_overnight_gap = statistics.mean(gaps)
    s.median_overnight_gap = statistics.median(gaps)
    s.std_overnight_gap = statistics.pstdev(gaps) if len(gaps) > 1 else 0.0
    qs = sorted(gaps)
    s.quantiles = {q: qs[min(len(qs) - 1, int(q * (len(qs) - 1)))] for q in (0.05, 0.25, 0.5, 0.75, 0.95)}
    s.gap_up_count = sum(1 for r in records if r.gap_classification == "GAP_UP")
    s.gap_down_count = sum(1 for r in records if r.gap_classification == "GAP_DOWN")
    s.flat_gap_count = sum(1 for r in records if r.gap_classification == "FLAT_GAP")
    s.continuation_count = sum(1 for r in records if r.session_outcome in ("GAP_UP_CONTINUATION", "GAP_DOWN_CONTINUATION"))
    s.fade_count = sum(1 for r in records if r.session_outcome == "GAP_UP_FADE")
    s.recovery_count = sum(1 for r in records if r.session_outcome == "GAP_DOWN_RECOVERY")
    s.sample_sufficiency = "SUFFICIENT" if len(gaps) >= min_sample else "INSUFFICIENT_SAMPLE"
    return s


def conditional_rate(records: list[DailyGapSessionRecord], *, gap: str, outcome: str,
                     min_sample: int = 20) -> dict:
    """Empirical historical conditional rate (DESCRIPTIVE_HISTORICAL_RATE, NOT_CALIBRATED)."""
    base = [r for r in records if r.gap_classification == gap]
    hit = [r for r in base if r.session_outcome == outcome]
    result = {
        "rate": (len(hit) / len(base)) if base else None,
        "base_count": len(base),
        "hit_count": len(hit),
        "evidence_class": "DESCRIPTIVE_HISTORICAL_RATE",
        "calibration_status": "NOT_CALIBRATED",
        "public_probability_status": "NOT_PUBLIC_PROBABILITY",
        "sample_sufficiency": ("SUFFICIENT" if len(base) >= min_sample else "INSUFFICIENT_SAMPLE"),
    }
    return result