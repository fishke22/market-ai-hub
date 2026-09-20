"""Phase 2G.2 — Release-time correctness + revision policy（7）。

Macro feature 必須區分 observation_period / scheduled_release_time /
actual_release_time / available_at。8 月 CPI 不得因 period=August 就在 8 月可見；
只有 release 發生後才可使用。

revision policy：FIRST_RELEASE / LATEST_REVISED。回測預設 FIRST_RELEASE / AS_KNOWN_AT_TIME。
官方來源無歷史 vintage → REVISION_RISK，不得假稱 point-in-time perfect。
"""
from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel

FIRST_RELEASE = "FIRST_RELEASE"
LATEST_REVISED = "LATEST_REVISED"
AS_KNOWN_AT_TIME = "AS_KNOWN_AT_TIME"
REVISION_RISK = "REVISION_RISK"


class MacroObservation(BaseModel):
    series_id: str
    observation_period: str                 # e.g. "2024-08"（資料期間，非可見時點）
    value: float
    scheduled_release_time: datetime | None = None
    actual_release_time: datetime | None = None
    available_at: datetime | None = None    # = actual_release_time（release 後才可用）
    revision_policy: str = FIRST_RELEASE
    has_historical_vintage: bool = False


def available_as_of(obs: MacroObservation, information_cutoff: datetime) -> bool:
    """release 發生後才可用。period 早不代表可見。"""
    if obs.actual_release_time is None:
        return False
    c = information_cutoff if information_cutoff.tzinfo is not None else information_cutoff.replace(tzinfo=timezone.utc)
    r = obs.actual_release_time if obs.actual_release_time.tzinfo is not None else obs.actual_release_time.replace(tzinfo=timezone.utc)
    return r <= c


def revision_flag(obs: MacroObservation) -> str:
    """FIRST_RELEASE 且無 vintage → REVISION_RISK；LATEST_REVISED → 明示。"""
    if obs.revision_policy == LATEST_REVISED:
        return LATEST_REVISED
    if obs.revision_policy == FIRST_RELEASE and not obs.has_historical_vintage:
        return REVISION_RISK
    return FIRST_RELEASE


def as_known_at_time(obs: MacroObservation, information_cutoff: datetime) -> dict:
    """回傳 (value, flag)。未 release → 不可用；無 vintage → REVISION_RISK。"""
    if not available_as_of(obs, information_cutoff):
        return {"available": False, "value": None, "flag": "NOT_RELEASED"}
    return {"available": True, "value": obs.value, "flag": revision_flag(obs)}
