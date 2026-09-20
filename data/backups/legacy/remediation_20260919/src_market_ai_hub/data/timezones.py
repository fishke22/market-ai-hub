"""時間與 timezone 工具。storage 一律 UTC，禁止 naive datetime。"""
from __future__ import annotations

from datetime import datetime, timezone

from pytz import timezone as tz

DISPLAY_ZONES = {
    "Asia/Taipei": tz("Asia/Taipei"),
    "Asia/Tokyo": tz("Asia/Tokyo"),
    "America/New_York": tz("America/New_York"),
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def ensure_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        raise ValueError("naive datetime not allowed")
    return dt.astimezone(timezone.utc)


def to_display(dt: datetime, zone: str) -> datetime:
    return ensure_utc(dt).astimezone(DISPLAY_ZONES[zone])


def iso(dt: datetime) -> str:
    return ensure_utc(dt).isoformat()
