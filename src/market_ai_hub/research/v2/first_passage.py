"""W5.1 daily first-passage label engine.

Research only. Composes the existing V2-C daily barrier engine for an upper and
lower frozen barrier. Daily OHLC cannot recover intraday order when both sides
are touched in the same session, so that case is explicitly AMBIGUOUS.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from market_ai_hub.research.v2.labels import (
    BarrierSpec,
    DailyLabelPolicy,
    DailyLabelRequest,
    DailyOutcomeBar,
    EventResult,
    build_daily_barrier_labels,
)

W5_FIRST_PASSAGE_SCHEMA_VERSION = "W5.1"

OUTCOMES = ("UPPER_FIRST", "LOWER_FIRST", "NEITHER", "AMBIGUOUS_WITHIN_DAILY_BAR")
OBSERVED = "OBSERVED"
AMBIGUOUS_WITHIN_DAILY_BAR = "AMBIGUOUS_WITHIN_DAILY_BAR"


@dataclass(frozen=True)
class DailyFirstPassageResult:
    outcome: str = ""
    status: str = "UNMATURED"
    first_session_date: str = ""
    upper_barrier_id: str = ""
    lower_barrier_id: str = ""
    upper_touch_status: str = ""
    lower_touch_status: str = ""
    schema_version: str = W5_FIRST_PASSAGE_SCHEMA_VERSION
    resolution: str = "DAILY_OHLC"

    def model_dump(self) -> dict:
        return asdict(self)


def _invalid(upper: BarrierSpec, lower: BarrierSpec, reason: str) -> DailyFirstPassageResult:
    return DailyFirstPassageResult(
        status=reason,
        upper_barrier_id=upper.barrier_id,
        lower_barrier_id=lower.barrier_id,
    )


def build_daily_first_passage_label(
    request: DailyLabelRequest,
    upper: BarrierSpec,
    lower: BarrierSpec,
    bars: list[DailyOutcomeBar],
    *,
    policy: DailyLabelPolicy | None = None,
    expected_sessions: list[str] | None = None,
    calendar_provenance: str = "UNKNOWN",
) -> DailyFirstPassageResult:
    """Return UPPER_FIRST / LOWER_FIRST / NEITHER, or fail closed.

    Both underlying touch labels must be fully observed (TRUE/FALSE) before a
    first-passage category is released. Same-session double touch is ambiguous
    because daily OHLC has no within-bar ordering.
    """
    if upper.direction != "UP" or lower.direction != "DOWN":
        return _invalid(upper, lower, "INVALID_BARRIER_DIRECTION")
    if upper.level is None or lower.level is None or upper.level <= lower.level:
        return _invalid(upper, lower, "INVALID_BARRIER_ORDER")

    upper_label = build_daily_barrier_labels(
        request, upper, bars, policy=policy,
        expected_sessions=expected_sessions,
        calendar_provenance=calendar_provenance,
    )
    lower_label = build_daily_barrier_labels(
        request, lower, bars, policy=policy,
        expected_sessions=expected_sessions,
        calendar_provenance=calendar_provenance,
    )

    if upper_label.series_block:
        return _invalid(upper, lower, upper_label.series_block)
    if lower_label.series_block:
        return _invalid(upper, lower, lower_label.series_block)

    ut = upper_label.touch
    lt = lower_label.touch
    base = dict(
        upper_barrier_id=upper.barrier_id,
        lower_barrier_id=lower.barrier_id,
        upper_touch_status=ut.status,
        lower_touch_status=lt.status,
    )

    if ut.value is None or lt.value is None:
        priorities = (
            "AMBIGUOUS_GAP_CROSS",
            "INVALID_OHLC",
            "UNOBSERVABLE_MISSING_DATA",
            "BLOCKED_PREWINDOW_REFERENCE_PROVENANCE",
            "UNMATURED",
        )
        statuses = {ut.status, lt.status}
        status = next((x for x in priorities if x in statuses), sorted(statuses)[0])
        return DailyFirstPassageResult(status=status, **base)

    if ut.value is False and lt.value is False:
        return DailyFirstPassageResult(outcome="NEITHER", status=OBSERVED, **base)

    if ut.value is True and lt.value is False:
        return DailyFirstPassageResult(
            outcome="UPPER_FIRST", status=OBSERVED,
            first_session_date=ut.first_session_date, **base,
        )

    if lt.value is True and ut.value is False:
        return DailyFirstPassageResult(
            outcome="LOWER_FIRST", status=OBSERVED,
            first_session_date=lt.first_session_date, **base,
        )

    # Both touched within the mature horizon.
    if ut.first_session_date == lt.first_session_date:
        return DailyFirstPassageResult(
            outcome="AMBIGUOUS_WITHIN_DAILY_BAR",
            status=AMBIGUOUS_WITHIN_DAILY_BAR,
            first_session_date=ut.first_session_date,
            **base,
        )
    if ut.first_session_date < lt.first_session_date:
        return DailyFirstPassageResult(
            outcome="UPPER_FIRST", status=OBSERVED,
            first_session_date=ut.first_session_date, **base,
        )
    return DailyFirstPassageResult(
        outcome="LOWER_FIRST", status=OBSERVED,
        first_session_date=lt.first_session_date, **base,
    )


def binary_first_passage_outcome(
    result: DailyFirstPassageResult,
    target: str,
) -> EventResult:
    """Convert one categorical result into a binary audit label.

    target may be UPPER_FIRST / LOWER_FIRST / NEITHER. Ambiguous or otherwise
    unobservable categorical results remain value=None and are never guessed.
    """
    if target not in ("UPPER_FIRST", "LOWER_FIRST", "NEITHER"):
        raise ValueError(f"unsupported first-passage target: {target!r}")
    if result.status != OBSERVED:
        return EventResult(None, result.status, result.first_session_date)
    return EventResult(
        result.outcome == target,
        "OBSERVED_TRUE" if result.outcome == target else "OBSERVED_FALSE",
        result.first_session_date,
    )
