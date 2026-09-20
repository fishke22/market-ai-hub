"""Phase 2C — 事件引擎（Event Engine）。

- Known events：PRE_EVENT / EVENT_WINDOW / POST_EVENT（依排程與 as_of 判定）。
- Breaking event：記錄後，凡 forecast 的 information_cutoff < event_time → FORECAST_STALE_AFTER_EVENT。
  觸發後應 refresh data → recompute regime → rerun forecast（由 orchestration 層執行）。
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd


def _aware(dt) -> datetime:
    if isinstance(dt, datetime):
        return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)
    ts = pd.Timestamp(dt)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    return ts.to_pydatetime()


def event_phase(schedule_dates: list[datetime | str], as_of,
                pre_days: int = 3, post_days: int = 3) -> str:
    """依 as_of 與排程判定 phase：PRE_EVENT / EVENT_WINDOW / POST_EVENT / NONE。"""
    as_of = pd.Timestamp(_aware(as_of))
    for d in schedule_dates:
        ev = pd.Timestamp(_aware(d))
        day = ev.normalize()
        a = as_of.normalize()
        delta_days = (a - day).days
        if -pre_days <= delta_days < 0:
            return "PRE_EVENT"
        if delta_days == 0:
            return "EVENT_WINDOW"
        if 0 < delta_days <= post_days:
            return "POST_EVENT"
    return "NONE"


class EventEngine:
    def __init__(self) -> None:
        self.breaking_events: list[dict] = []  # {name, event_time}

    def record_breaking_event(self, name: str, event_time: datetime) -> None:
        self.breaking_events.append({"name": name, "event_time": _aware(event_time)})

    def stale_forecast_ids(self, forecasts: list[dict], breaking_event_time: datetime | None = None) -> list[str]:
        """回傳 information_cutoff < event_time 的 forecast ids（FORECAST_STALE_AFTER_EVENT）。

        forecasts: list of {"forecast_id": str, "information_cutoff": datetime}
        """
        events = self.breaking_events if breaking_event_time is None else [
            {"name": "breaking", "event_time": _aware(breaking_event_time)}
        ]
        stale: list[str] = []
        for fc in forecasts:
            cutoff = fc.get("information_cutoff")
            if cutoff is None:
                continue
            cutoff = pd.Timestamp(_aware(cutoff))
            for ev in events:
                et = pd.Timestamp(ev["event_time"])
                if cutoff < et:
                    stale.append(fc["forecast_id"])
                    break
        return stale
