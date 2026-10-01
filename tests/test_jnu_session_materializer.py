from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from market_ai_hub.services.jnu_session_materializer import (
    JNUSessionMaterializer,
    first_passage_to_level,
    label_ready_row,
    load_materialized_sessions,
    select_session,
    settlement_excursion,
)


JST = ZoneInfo("Asia/Tokyo")


def _tick(code, local_iso, serial, price, volume):
    local = datetime.fromisoformat(local_iso).replace(tzinfo=JST)
    return {
        "callback_type": "SubscribeStockTick",
        "market_no": 207,
        "instrument_code": code,
        "received_at": local.astimezone(timezone.utc).isoformat(),
        "source_time_of_day": local.strftime("%H:%M:%S.000"),
        "timestamp_quality": "SOURCE_TIME_OF_DAY_ONLY",
        "DealPrice": price,
        "DealVol": volume,
        "SerialNo": serial,
    }


def test_day_session_materializes_ohlcv_vwap_excursions_and_verified_close(tmp_path):
    m = JNUSessionMaterializer(tmp_path, runtime_build_id="test", persist_interval_seconds=0)
    ticks = [
        _tick("JNU2612", "2026-09-29T08:45:00", 1, 100.0, 2),
        _tick("JNU2612", "2026-09-29T09:00:00", 2, 110.0, 3),
        _tick("JNU2612", "2026-09-29T09:30:00", 3, 95.0, 5),
        _tick("JNU2612", "2026-09-29T15:45:00", 4, 105.0, 10),
    ]
    for tick in ticks:
        assert m.ingest(tick) is True
    artifact = m.snapshot()
    session = select_session(artifact, contract_month="202612", session="DAY")
    assert session["session_start_date"] == "2026-09-29"
    assert session["session_open"] == 100.0
    assert session["observed_high"] == 110.0
    assert session["observed_low"] == 95.0
    assert session["latest_price"] == 105.0
    assert session["total_volume"] == 20.0
    assert session["trade_count"] == 4
    assert session["vwap"] == pytest.approx((100 * 2 + 110 * 3 + 95 * 5 + 105 * 10) / 20)
    assert session["mfe_from_session_open"] == 10.0
    assert session["mae_from_session_open"] == -5.0
    assert session["opening_range_high"] == 110.0
    assert session["opening_range_low"] == 100.0
    assert session["opening_range_complete"] is True
    assert session["verified_close"] is True
    assert session["verified_close_price"] == 105.0
    assert session["coverage_complete"] is True
    assert label_ready_row(session)["label_eligible"] is True
    excursion = settlement_excursion(session, 102.0)
    assert excursion["latest_minus_settlement"] == 3.0
    assert excursion["high_minus_settlement"] == 8.0
    assert excursion["low_minus_settlement"] == -7.0


def test_night_session_crosses_midnight_and_keeps_start_date(tmp_path):
    m = JNUSessionMaterializer(tmp_path, runtime_build_id="test", persist_interval_seconds=0)
    for tick in [
        _tick("JNUPM2612", "2026-09-29T17:00:00", 10, 200.0, 1),
        _tick("JNUPM2612", "2026-09-30T00:05:00", 11, 210.0, 2),
        _tick("JNUPM2612", "2026-09-30T06:00:00", 12, 205.0, 3),
    ]:
        assert m.ingest(tick) is True
    session = select_session(m.snapshot(), contract_month="202612", session="NIGHT")
    assert session["session_start_date"] == "2026-09-29"
    assert session["session_open"] == 200.0
    assert session["verified_close"] is True
    assert session["verified_close_price"] == 205.0
    assert session["coverage_complete"] is True


def test_duplicate_tick_is_idempotent(tmp_path):
    m = JNUSessionMaterializer(tmp_path, runtime_build_id="test", persist_interval_seconds=0)
    tick = _tick("JNUPM2612", "2026-09-29T17:00:00", 99, 300.0, 7)
    assert m.ingest(tick) is True
    assert m.ingest(tick) is False
    session = select_session(m.snapshot(), contract_month="202612", session="NIGHT")
    assert session["trade_count"] == 1
    assert session["total_volume"] == 7.0


def test_partial_session_is_not_label_ready_and_first_passage_is_explicit(tmp_path):
    m = JNUSessionMaterializer(tmp_path, runtime_build_id="test", persist_interval_seconds=0)
    for i, price in enumerate([100.0, 103.0, 106.0, 104.0]):
        assert m.ingest(
            _tick("JNUPM2612", f"2026-09-29T17:{i * 5:02d}:00", 200 + i, price, 1)
        )
    session = select_session(m.snapshot(), contract_month="202612", session="NIGHT")
    assert session["verified_close"] is False
    assert label_ready_row(session)["label_eligible"] is False
    assert first_passage_to_level(session, level=None, direction="UP")["status"] == "LEVEL_REQUIRED"
    reached = first_passage_to_level(session, level=105.0, direction="UP")
    assert reached["status"] == "OBSERVED_TRUE"
    assert reached["value"] is True
    assert reached["resolution"] == "5MIN_OHLC"
    not_reached = first_passage_to_level(session, level=90.0, direction="DOWN")
    assert not_reached["status"] == "OBSERVED_FALSE_SO_FAR"
    assert not_reached["value"] is False


def test_materialized_artifact_freshness_and_reload(tmp_path):
    m = JNUSessionMaterializer(tmp_path, runtime_build_id="test", persist_interval_seconds=0)
    tick = _tick("JNU2612", "2026-09-29T08:45:00", 1, 100.0, 1)
    assert m.ingest(tick)
    m.flush()
    persisted_at = datetime.fromisoformat(m.snapshot()["updated_at"]).astimezone(timezone.utc)
    fresh = load_materialized_sessions(
        tmp_path,
        now=persisted_at,
        max_age_seconds=120,
    )
    assert fresh["status"] == "FRESH"
    stale = load_materialized_sessions(
        tmp_path,
        now=persisted_at.replace(microsecond=0) + timedelta(minutes=10),
        max_age_seconds=120,
    )
    assert stale["status"] == "STALE"
    reloaded = JNUSessionMaterializer(tmp_path, runtime_build_id="new", persist_interval_seconds=0)
    session = select_session(reloaded.snapshot(), contract_month="202612", session="DAY")
    assert session["trade_count"] == 1
