from datetime import datetime, timezone

import pytest

from market_ai_hub.data.timezones import ensure_utc, iso, to_display, utc_now


def test_utc_now_aware():
    assert utc_now().tzinfo is not None


def test_ensure_utc_rejects_naive():
    with pytest.raises(ValueError):
        ensure_utc(datetime(2026, 1, 1))


def test_ensure_utc_converts():
    jst = datetime(2026, 1, 1, 9, 0, tzinfo=timezone.utc)
    assert ensure_utc(jst).hour == 9


def test_display_conversion_tokyo():
    utc9 = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    tokyo = to_display(utc9, "Asia/Tokyo")
    assert tokyo.hour == 9


def test_display_conversion_taipei():
    utc9 = datetime(2026, 1, 1, 0, 0, tzinfo=timezone.utc)
    taipei = to_display(utc9, "Asia/Taipei")
    assert taipei.hour == 8


def test_iso_contains_offset():
    assert "+" in iso(datetime.now(timezone.utc))
