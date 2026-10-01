"""Zero-cost official event calendar collector（免金鑰、公開來源）。

Sources:
- FOMC meeting calendar（federalreserve.gov，會議首日 14:00 ET 為近似決策時間）
- BLS release schedules（bls.gov schedule pages：Employment Situation、CPI；
  日期以官方連結檔名 MMDDYYYY 為準，時間用官方慣例 08:30 ET）

各來源獨立 fail-closed；只有「全部來源都失敗」時整次刷新才算失敗。
日期是權威事實；時刻是官方慣例的近似值，僅作排序與警示用途。
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx

from market_ai_hub.providers.base import ProviderError
from market_ai_hub.targets.events import OfficialEvent

USER_AGENT = "MARKET_AI_HUB/1.1 (public-source research calendar)"
FOMC_URL = "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm"
NY = ZoneInfo("America/New_York")

# url / source / importance_class / 慣例公告時刻(ET)
BLS_SCHEDULES = {
    "US Employment Situation (NFP)": (
        "https://www.bls.gov/schedule/news_release/empsit.htm", "BLS", "HIGH", "08:30",
    ),
    "US CPI": (
        "https://www.bls.gov/schedule/news_release/cpi.htm", "BLS", "HIGH", "08:30",
    ),
}

_DATE_RE = re.compile(r"/([A-Za-z0-9_\-]+)_(\d{8})\.htm")
# 真實 Fed 頁面：年份寫在 <a id="…">2026 FOMC Meetings</a>；月份/日期 div 的 class
# 帶 col-* 尾巴且有 shaded 變體，故用 [^"<>]* 容錯。
_YEAR_HEAD_RE = re.compile(r'<a id="\d+">\s*(?P<year>\d{4})\s+FOMC Meetings</a>', re.S)
_MEETING_RE = re.compile(
    r'fomc-meeting__month[^"<>]*"\s*>\s*<strong>\s*(?P<month>\w+)\s*</strong>.*?'
    r'fomc-meeting__date[^"<>]*"\s*>\s*(?P<day>\d+)',
    re.S,
)

# 供 fail-honest 診斷：來源解析為空時留下原始 HTML 前段（update 腳本會 dump 成檔）。
DIAG: dict[str, str] = {}
# Per-source outcome of the most recent collect_events() call. Lets consumers tell a
# refreshed source from one that is currently blocked (e.g. BLS bot policy).
LAST_SOURCE_STATUS: dict[str, str] = {}
_MONTHS = {
    "January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6,
    "July": 7, "August": 8, "September": 9, "October": 10, "November": 11, "December": 12,
}


def _fetch(url: str) -> str:
    resp = None
    try:
        resp = httpx.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                              "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
            timeout=20.0,
            follow_redirects=True,
        )
        resp.raise_for_status()
    except Exception as exc:
        try:
            if resp is not None and resp.text:
                DIAG[url] = resp.text[:3000]
        except Exception:
            pass
        # BLS blocks automated retrieval by policy (Akamai 'Access Denied').
        # Report it as a typed provider block: do not retry-loop and never treat the
        # block page as data. Scheduled dates stay UNAVAILABLE for that source.
        status = getattr(getattr(exc, 'response', None), 'status_code', None)
        if status == 403:
            raise ProviderError(f"EVENT_ACCESS_DENIED_PROVIDER_BOT_POLICY {url}") from exc
        raise ProviderError(f"EVENT_FETCH_FAILED {url}: {type(exc).__name__}") from exc
    if not resp.text:
        raise ProviderError(f"EVENT_FETCH_EMPTY {url}")
    return resp.text


def _et_to_utc(year: int, month: int, day: int, hm: str) -> datetime:
    hh, mm = hm.split(":")
    return datetime(year, month, day, int(hh), int(mm), tzinfo=NY).astimezone(timezone.utc)


def _future_filter(events: list[OfficialEvent], now: datetime | None = None) -> list[OfficialEvent]:
    now = now or datetime.now(timezone.utc)
    return [e for e in events if e.scheduled_at >= now - timedelta(days=1)]


def parse_fomc_meetings(html: str) -> list[OfficialEvent]:
    """解析 Fed FOMC 日曆頁（可單測：傳入 html）。會議記首日 14:00 ET（近似決策時刻）。"""
    meetings: list[OfficialEvent] = []
    year_heads = list(_YEAR_HEAD_RE.finditer(html))
    blocks: list[tuple[int, str]] = []
    for i, m in enumerate(year_heads):
        end = year_heads[i + 1].start() if i + 1 < len(year_heads) else len(html)
        blocks.append((int(m.group("year")), html[m.end():end]))
    for year, block in blocks:
        for mm in _MEETING_RE.finditer(block):
            month = _MONTHS.get(mm.group("month"))
            if month is None:
                continue
            day = int(mm.group("day"))
            scheduled_at = _et_to_utc(year, month, day, "14:00")
            meetings.append(
                OfficialEvent(
                    event_name=f"FOMC Meeting ({mm.group('month')} {year})",
                    scheduled_at=scheduled_at,
                    source="FED",
                    importance_class="HIGH",
                )
            )
    return meetings


def parse_bls_schedule(html: str, name: str, source: str, importance: str, hm: str) -> list[OfficialEvent]:
    """解析 BLS 排程頁（可單測）。日期以官方連結檔名 MMDDYYYY 為權威。"""
    events: list[OfficialEvent] = []
    seen = set()
    for match in _DATE_RE.finditer(html):
        ymd = match.group(2)  # MMDDYYYY
        try:
            month, day, year = int(ymd[0:2]), int(ymd[2:4]), int(ymd[4:8])
        except ValueError:
            continue
        key = (year, month, day)
        if key in seen or year < 2020 or year > 2100:
            continue
        seen.add(key)
        events.append(
            OfficialEvent(
                event_name=name,
                scheduled_at=_et_to_utc(year, month, day, hm),
                source=source,
                importance_class=importance,
            )
        )
    return events


def fetch_fomc_meetings(html: str | None = None) -> list[OfficialEvent]:
    text = html or _fetch(FOMC_URL)
    out = parse_fomc_meetings(text)
    if not out:
        raise ProviderError("FOMC_PARSE_EMPTY")
    return out


def fetch_bls_schedule(name: str, url: str, source: str, importance: str, hm: str,
                       html: str | None = None) -> list[OfficialEvent]:
    text = html or _fetch(url)
    out = parse_bls_schedule(text, name, source, importance, hm)
    if not out:
        DIAG[name] = text[:6000]
        raise ProviderError(f"BLS_PARSE_EMPTY {name}")
    return out


def collect_events(now: datetime | None = None) -> list[OfficialEvent]:
    """彙整所有免金鑰來源；部分來源失敗仍保留其他來源的結果，全部失敗才 raise。"""
    events: list[OfficialEvent] = []
    errors: list[str] = []
    LAST_SOURCE_STATUS.clear()
    try:
        events.extend(fetch_fomc_meetings())
        LAST_SOURCE_STATUS["FED"] = "REFRESHED"
    except ProviderError as exc:
        errors.append(str(exc))
        LAST_SOURCE_STATUS["FED"] = "BLOCKED_OR_FAILED"
    for name, (url, source, importance, hm) in BLS_SCHEDULES.items():
        try:
            events.extend(fetch_bls_schedule(name, url, source, importance, hm))
            LAST_SOURCE_STATUS[source] = "REFRESHED"
        except ProviderError as exc:
            errors.append(str(exc))
            LAST_SOURCE_STATUS[source] = "BLOCKED_OR_FAILED"
    if not events:
        raise ProviderError("EVENT_COLLECT_ALL_FAILED: " + " | ".join(errors[:3]))
    return _future_filter(events, now=now)