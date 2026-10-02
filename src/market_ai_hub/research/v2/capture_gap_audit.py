"""Capture-gap audit: separate legitimately-absent time from real capture loss.

The recorded tick store has holes. Some are expected (no subscribed venue is open), others are
real loss (a venue was open and we captured nothing). Mixing them makes the capture look either
better or worse than it is, so each gap is classified against `session_truth` at three sample
points (start / middle / end) and is only called expected when no subscribed venue was open at
any of them.

Read-only. No model, no probability, no ranking.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable, Iterable

V2_CAPTURE_GAP_AUDIT_SCHEMA_VERSION = "GA.1"

GAP_MARKET_CLOSED_EXPECTED = "MARKET_CLOSED_EXPECTED"
GAP_RECORDER_OFF_EXPECTED = "RECORDER_OFF_EXPECTED"
GAP_CAPTURE_LOSS_WHILE_RUNNING = "CAPTURE_LOSS_WHILE_RUNNING"
GAP_UNCLASSIFIED = "UNCLASSIFIED_NO_LIVENESS_RECORD"
GAP_STATUSES: tuple[str, ...] = (
    GAP_MARKET_CLOSED_EXPECTED, GAP_RECORDER_OFF_EXPECTED,
    GAP_CAPTURE_LOSS_WHILE_RUNNING, GAP_UNCLASSIFIED,
)
# A gap is a real defect only when the venue was open AND this process was running.
GAP_REAL_LOSS_STATUSES: tuple[str, ...] = (GAP_CAPTURE_LOSS_WHILE_RUNNING,)

DEFAULT_MIN_GAP_SECONDS = 120.0
_SAMPLE_POINTS = 3


class CaptureGapAuditError(Exception):
    """Base for audit contract violations."""


def _session_venues() -> dict[int, str]:
    """Market -> venue map, reused from the recorder so there is a single source."""
    from market_ai_hub.integrations.yuanta.live_quote_recorder import _MARKET_SESSION_VENUE

    return dict(_MARKET_SESSION_VENUE)


def default_session_probe(markets: Iterable[int], asof: datetime) -> tuple[bool, list[str]]:
    """(any_open, open_venue_ids) using the recorder's session check."""
    from market_ai_hub.integrations.yuanta.live_quote_recorder import _subscribed_market_open

    venues = {m: _session_venues().get(int(m)) for m in markets}
    open_venues: list[str] = []
    for market, venue in venues.items():
        if not venue:
            continue
        from market_ai_hub.research.v2 import session_truth as _st

        try:
            ctx = _st.resolve_venue_session(venue, asof)
        except Exception:
            continue
        if getattr(ctx, "market_open", False):
            open_venues.append(venue)
    return bool(open_venues) or _subscribed_market_open(markets, asof), sorted(set(open_venues))


@dataclass(frozen=True)
class CaptureGap:
    start: str
    end: str
    seconds: float
    classification: str
    open_venues: list[str] = field(default_factory=list)
    sampled_at: list[str] = field(default_factory=list)

    def model_dump(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class CaptureGapAudit:
    day: str
    tick_count: int
    first_tick: str | None
    last_tick: str | None
    span_seconds: float
    expected_seconds: float
    loss_seconds: float
    gaps: list[CaptureGap] = field(default_factory=list)
    markets: list[int] = field(default_factory=list)
    min_gap_seconds: float = DEFAULT_MIN_GAP_SECONDS
    schema_version: str = V2_CAPTURE_GAP_AUDIT_SCHEMA_VERSION
    audit_id: str = ""       # derived

    def __post_init__(self) -> None:
        for g in self.gaps:
            if g.classification not in GAP_STATUSES:
                raise CaptureGapAuditError(f"unknown gap classification: {g.classification!r}")

    def model_dump(self) -> dict:
        return asdict(self)

    def identity_payload(self) -> dict:
        d = asdict(self)
        d.pop("audit_id", None)
        return d


def _identity(payload: dict) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return "v2ga_" + sha256(blob.encode("utf-8")).hexdigest()[:16]


def list_capture_days(store_root) -> list[str]:
    """Recorded partitions (presence does not imply usable content)."""
    root = Path(store_root)
    if not root.exists():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir())


def _lifecycle_intervals(root: Path) -> list[tuple[datetime, datetime | None]]:
    """[(start, stop|None)] from the recorder's lifecycle journal; [] when there is none."""
    import json

    from market_ai_hub.integrations.yuanta.live_quote_recorder import lifecycle_path

    path = lifecycle_path(Path(root))
    if not path.exists():
        return []
    intervals: list[tuple[datetime, datetime | None]] = []
    open_start: datetime | None = None
    rows: list[tuple[datetime, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
            rows.append((datetime.fromisoformat(str(d["at"])), str(d.get("event", ""))))
        except Exception:
            continue
    for at, event in sorted(rows):
        if event == "START":
            open_start = at
        elif event == "STOP" and open_start is not None:
            intervals.append((open_start, at))
            open_start = None
    if open_start is not None:
        intervals.append((open_start, None))
    return intervals


def _liveness(intervals, start: datetime, end: datetime, now: datetime) -> str:
    """"RUNNING" / "OFF" / "UNKNOWN" for the gap interval. Never guessed."""
    if not intervals:
        return "UNKNOWN"
    for a, b in intervals:
        if a <= end and start <= (b or now):
            return "RUNNING"
    # No interval overlaps the gap. The journal is written by the process itself, so once it
    # has started it is authoritative up to the present: a gap after the last STOP really was
    # off. Before the first START we know nothing, so stay UNKNOWN.
    if min(a for a, _ in intervals) <= start and end <= now:
        return "OFF"
    return "UNKNOWN"


def _distinct_ticks(store_root, day: str) -> list[datetime]:
    import duckdb

    part = Path(store_root) / day
    if not part.exists():
        return []
    con = duckdb.connect()
    con.execute("SET enable_progress_bar=false")
    try:
        df = con.execute(
            f"SELECT DISTINCT received_at FROM read_parquet('{part.as_posix()}/*.parquet', "
            f"union_by_name=true) ORDER BY received_at").df()
    except Exception as exc:
        raise CaptureGapAuditError(f"STORE_UNREADABLE: {type(exc).__name__}") from exc
    return [datetime.fromisoformat(str(x)) for x in df["received_at"].tolist()]


def audit_capture_gaps(
    store_root,
    day: str,
    *,
    min_gap_seconds: float = DEFAULT_MIN_GAP_SECONDS,
    markets: Iterable[int] | None = None,
    session_probe: Callable[[Iterable[int], datetime], tuple[bool, list[str]]] | None = None,
) -> CaptureGapAudit:
    """Classify every hole in one recorded day as expected-absent or real capture loss."""
    if min_gap_seconds <= 0:
        raise CaptureGapAuditError("min_gap_seconds must be > 0")
    market_list = sorted({int(m) for m in (markets if markets is not None
                                           else _session_venues().keys())})
    probe = session_probe or default_session_probe
    store_root_path = Path(store_root)
    intervals = _lifecycle_intervals(store_root_path)
    now = datetime.now(timezone.utc)

    ticks = _distinct_ticks(store_root, day)
    if not ticks:
        return CaptureGapAudit(day=day, tick_count=0, first_tick=None, last_tick=None,
                               span_seconds=0.0, expected_seconds=0.0, loss_seconds=0.0,
                               markets=market_list, min_gap_seconds=min_gap_seconds)

    gaps: list[CaptureGap] = []
    expected = loss = 0.0
    for a, b in zip(ticks, ticks[1:]):
        seconds = (b - a).total_seconds()
        if seconds < min_gap_seconds:
            continue
        sampled: list[datetime] = []
        for i in range(_SAMPLE_POINTS):
            sampled.append(a + (b - a) * (i / (_SAMPLE_POINTS - 1)))
        any_open = False
        open_venues: set[str] = set()
        for ts in sampled:
            opened, venues = probe(market_list, ts)
            any_open = any_open or opened
            open_venues.update(venues)
        if not any_open:
            classification = GAP_MARKET_CLOSED_EXPECTED
        else:
            liv = _liveness(intervals, a, b, now)
            if liv == "RUNNING":
                classification = GAP_CAPTURE_LOSS_WHILE_RUNNING
            elif liv == "OFF":
                classification = GAP_RECORDER_OFF_EXPECTED
            else:
                # No liveness record covers this period, so whether we were supposed to be
                # capturing is unknown. Report that instead of guessing.
                classification = GAP_UNCLASSIFIED
        if classification in GAP_REAL_LOSS_STATUSES:
            loss += seconds
        else:
            expected += seconds
        gaps.append(CaptureGap(
            start=a.isoformat(), end=b.isoformat(), seconds=seconds,
            classification=classification, open_venues=sorted(open_venues),
            sampled_at=[t.isoformat() for t in sampled]))

    audit = CaptureGapAudit(
        day=day, tick_count=len(ticks), first_tick=ticks[0].isoformat(),
        last_tick=ticks[-1].isoformat(),
        span_seconds=(ticks[-1] - ticks[0]).total_seconds(),
        expected_seconds=expected, loss_seconds=loss, gaps=gaps,
        markets=market_list, min_gap_seconds=min_gap_seconds)
    return replace(audit, audit_id=_identity(audit.identity_payload()))


def audit_days(store_root, days: Iterable[str], **kwargs) -> list[CaptureGapAudit]:
    return [audit_capture_gaps(store_root, d, **kwargs) for d in days]
