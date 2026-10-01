"""Event calendar collector（零付費公開來源）— offline tests。"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from market_ai_hub.providers.base import ProviderError
from market_ai_hub.providers import event_calendar as ec
from market_ai_hub.targets.events import EventStore, OfficialEvent

FOMC_HTML = """<html><body>
<div class="panel panel-default"><div class="panel-heading"><h4><a id="42828">2026 FOMC Meetings</a></h4></div><div class="panel-body">
<div class="fomc-meeting__month col-xs-5 col-sm-3 col-md-2"><strong>January</strong></div>
<div class="fomc-meeting__date col-xs-4 col-sm-9 col-md-10 col-lg-1">27-28</div>
<div class="fomc-meeting--shaded fomc-meeting__month col-xs-5 col-sm-3 col-md-2"><strong>March</strong></div>
<div class="fomc-meeting__date col-xs-4 col-sm-9 col-md-10 col-lg-1">17-18*</div>
<div class="fomc-meeting__month col-xs-5 col-sm-3 col-md-2"><strong>October</strong></div>
<div class="fomc-meeting__date col-xs-4 col-sm-9 col-md-10 col-lg-1">28-29</div>
</div></div>
<div class="panel panel-default"><div class="panel-heading"><h4><a id="42827">2027 FOMC Meetings</a></h4></div><div class="panel-body">
<div class="fomc-meeting__month col-xs-5 col-sm-3 col-md-2"><strong>January</strong></div>
<div class="fomc-meeting__date col-xs-4 col-sm-9 col-md-10 col-lg-1">26-27</div>
</div></div>
</body></html>"""

BLS_HTML = """<html><body>
<a href="/schedule/news_release/empsit.htm">Employment Situation</a>
<a href="/schedule/archives/empsit_10022026.htm">October 2, 2026</a>
<a href="/news.release/archives/empsit_09042026.htm">September 2026</a>
<a href="/schedule/archives/empsit_12012025.htm">December 2025</a>
</body></html>"""


# ── parsers ──

def test_parse_fomc_meetings():
    out = ec.parse_fomc_meetings(FOMC_HTML)
    assert len(out) == 4
    names = [e.event_name for e in out]
    assert "FOMC Meeting (October 2026)" in names
    by = {e.event_name: e for e in out}
    oct26 = by["FOMC Meeting (October 2026)"]
    assert oct26.scheduled_at.year == 2026 and oct26.scheduled_at.month == 10
    assert oct26.scheduled_at.day == 28
    assert oct26.source == "FED" and oct26.importance_class == "HIGH"
    assert by["FOMC Meeting (January 2027)"].scheduled_at.year == 2027


def test_parse_bls_schedule():
    out = ec.parse_bls_schedule(BLS_HTML, "US Employment Situation (NFP)", "BLS", "HIGH", "08:30")
    dates = sorted((e.scheduled_at.year, e.scheduled_at.month, e.scheduled_at.day) for e in out)
    assert (2026, 10, 2) in dates
    # 10 月為美東夏令時（EDT=UTC-4）→ 08:30 ET == 12:30 UTC
    oct_row = [e for e in out if (e.scheduled_at.month, e.scheduled_at.day) == (10, 2)][0]
    assert oct_row.scheduled_at.hour == 12 and oct_row.scheduled_at.minute == 30
    assert oct_row.scheduled_at.tzinfo is not None
    # 過去年份的連結仍被解析（過濾在 collect 階段做）
    assert (2025, 12, 1) in dates


# ── filters / collector ──

def test_future_filter_drops_past():
    now = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)
    old = OfficialEvent(event_name="old", scheduled_at=now - timedelta(days=10))
    new = OfficialEvent(event_name="new", scheduled_at=now + timedelta(days=1))
    out = ec._future_filter([old, new], now=now)
    assert [e.event_name for e in out] == ["new"]


def test_collect_all_failed_raises(monkeypatch):
    def boom(*a, **k):
        raise ProviderError("boom")

    monkeypatch.setattr(ec, "fetch_fomc_meetings", boom)
    monkeypatch.setattr(ec, "fetch_bls_schedule", boom)
    with pytest.raises(ProviderError):
        ec.collect_events(now=datetime(2026, 10, 1, tzinfo=timezone.utc))


def test_collect_partial_failure_keeps_other_sources(monkeypatch):
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    future = OfficialEvent(
        event_name="US Employment Situation (NFP)", scheduled_at=now + timedelta(days=1),
        source="BLS", importance_class="HIGH",
    )

    def fomc_boom(*a, **k):
        raise ProviderError("fomc down")

    def fake_bls(name, url, source, importance, hm, html=None):
        if "CPI" in name:
            raise ProviderError("cpi down")
        return [future]

    monkeypatch.setattr(ec, "fetch_fomc_meetings", fomc_boom)
    monkeypatch.setattr(ec, "fetch_bls_schedule", fake_bls)
    out = ec.collect_events(now=now)
    assert [e.event_name for e in out] == ["US Employment Situation (NFP)"]


# ── store ──

def test_replace_scheduled_preserves_released_history(tmp_path):
    store = EventStore(root=tmp_path)
    released = OfficialEvent(
        event_name="done", scheduled_at=datetime(2026, 1, 1), released_at=datetime(2026, 1, 2),
        source="BLS", importance_class="HIGH",
    )
    past_sched = OfficialEvent(
        event_name="stale", scheduled_at=datetime(2026, 9, 1), source="BLS", importance_class="HIGH",
    )
    store.save(released)
    store.save(past_sched)
    fresh = [
        OfficialEvent(event_name="NFP", scheduled_at=datetime(2026, 10, 2, 12, 30),
                      source="BLS", importance_class="HIGH"),
    ]
    assert store.replace_scheduled(fresh) == 1
    upcoming = store.upcoming(top_n=10)
    assert [e.event_name for e in upcoming] == ["NFP"]
    # released history preserved（不因 replace 被刪）
    import duckdb
    with duckdb.connect(str(store.db_path)) as con:
        count = con.execute("SELECT COUNT(*) FROM events WHERE released_at IS NOT NULL").fetchone()[0]
    assert count == 1


def test_replace_scheduled_for_keeps_other_sources(tmp_path):
    store = EventStore(root=tmp_path)
    store.save(OfficialEvent(
        event_name="US Employment Situation (NFP)",
        scheduled_at=datetime(2026, 10, 2, 12, 30),
        source="BLS", importance_class="HIGH",
    ))
    replaced = store.replace_scheduled_for("FED", [
        OfficialEvent(event_name="FOMC Meeting (October 2026)",
                      scheduled_at=datetime(2026, 10, 27, 18, 0),
                      source="FED", importance_class="HIGH"),
    ])
    assert replaced == 1
    names = sorted(e.event_name for e in store.upcoming(top_n=10))
    assert names == ["FOMC Meeting (October 2026)", "US Employment Situation (NFP)"]


def test_event_snapshot_uses_store_when_populated(monkeypatch, tmp_path):
    from market_ai_hub.packet import builder

    store = EventStore(root=tmp_path)
    store.replace_scheduled([
        OfficialEvent(
            event_name="US Employment Situation (NFP)",
            scheduled_at=datetime(2026, 10, 2, 12, 30, tzinfo=timezone.utc),
            source="BLS", importance_class="HIGH",
        )
    ])
    monkeypatch.setattr("market_ai_hub.targets.events.EventStore", lambda: store)
    out = builder._event_snapshot(top_n=5)
    assert out and out[0]["status"] == "SCHEDULED"
    assert out[0]["event"] == "US Employment Situation (NFP)"
    assert out[0]["scheduled_at"]


def test_event_snapshot_fallback_when_store_empty(monkeypatch):
    from market_ai_hub.packet import builder

    class EmptyStore:
        def upcoming(self, top_n=10):
            return []

    monkeypatch.setattr("market_ai_hub.targets.events.EventStore", EmptyStore)
    out = builder._event_snapshot(top_n=3)
    assert all(row["status"] == "CALENDAR_AVAILABLE" for row in out)
    assert len(out) == 3


def test_provider_bot_policy_block_is_typed_not_a_parse_error(monkeypatch):
    """BLS blocks automated retrieval by policy (Akamai 'Access Denied').

    The collector must surface a typed provider block instead of pretending the page
    was parsed empty, and must never treat the block page as event data.
    """
    import httpx

    url = "https://www.bls.gov/schedule/news_release/empsit.htm"

    def _fake_get(_url, **_kw):
        req = httpx.Request("GET", _url)
        resp = httpx.Response(403, request=req,
                              text="<h2>Access Denied</h2><p>bot activity ... is prohibited</p>")
        raise httpx.HTTPStatusError("403 Forbidden", request=req, response=resp)

    monkeypatch.setattr(ec.httpx, "get", _fake_get)
    with pytest.raises(ProviderError, match="EVENT_ACCESS_DENIED_PROVIDER_BOT_POLICY"):
        ec._fetch(url)


def test_collect_events_degrades_when_one_source_is_blocked(monkeypatch):
    """One blocked source must not erase another source's events, and must not fake events."""
    from market_ai_hub.targets.events import OfficialEvent as _OE

    good = _OE(event_name="FOMC Meeting", scheduled_at=datetime(2026, 10, 27, 18, 0, tzinfo=timezone.utc),
               source="FED", importance_class="HIGH")
    monkeypatch.setattr(ec, "fetch_fomc_meetings", lambda *a, **k: [good])
    monkeypatch.setattr(ec, "fetch_bls_schedule",
                        lambda *a, **k: (_ for _ in ()).throw(
                            ProviderError("EVENT_ACCESS_DENIED_PROVIDER_BOT_POLICY")))
    out = ec.collect_events(now=datetime(2026, 10, 1, tzinfo=timezone.utc))
    assert [e.source for e in out] == ["FED"]


def test_event_refresh_status_surfaces_blocked_sources(tmp_path):
    """A blocked source must be visible so its stored dates are not read as current."""
    from market_ai_hub.targets.events import event_refresh_status

    (tmp_path / "refresh_log.json").write_text(json.dumps({
        "ok": True, "generated_at": "2026-10-01T16:00:00+00:00",
        "sources": {"FED": 10},
        "source_status": {"FED": "REFRESHED", "BLS": "BLOCKED_OR_FAILED"},
    }), encoding="utf-8")
    st = event_refresh_status(tmp_path)
    assert st["refreshed_sources"] == ["FED"]
    assert st["blocked_sources"] == ["BLS"]
    assert st["status"] == "OK"
    assert "stale" in st["note"]


def test_event_refresh_status_without_log(tmp_path):
    from market_ai_hub.targets.events import event_refresh_status

    assert event_refresh_status(tmp_path)["status"] == "NO_REFRESH_LOG"


def test_collect_events_records_per_source_status(monkeypatch):
    from market_ai_hub.targets.events import OfficialEvent as _OE

    good = _OE(event_name="FOMC", scheduled_at=datetime(2026, 10, 27, 18, 0, tzinfo=timezone.utc),
               source="FED", importance_class="HIGH")
    monkeypatch.setattr(ec, "fetch_fomc_meetings", lambda *a, **k: [good])
    monkeypatch.setattr(ec, "fetch_bls_schedule",
                        lambda *a, **k: (_ for _ in ()).throw(ProviderError("blocked")))
    ec.collect_events(now=datetime(2026, 10, 1, tzinfo=timezone.utc))
    assert ec.LAST_SOURCE_STATUS["FED"] == "REFRESHED"
    assert ec.LAST_SOURCE_STATUS["BLS"] == "BLOCKED_OR_FAILED"
