from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from scripts.update_jnu_capture_coverage import HEALTHY_CLASSIFICATION, update_coverage
from scripts.update_jnu_capture_research_summary import build_summary


def _write_status(root: Path, *, callbacks=4):
    p = root / "status.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "jnu_microstructure_live_verified": True,
        "jnu_microstructure_callbacks": {"stock_tick": callbacks, "five_tick": 2},
        "dropped_records": 0,
        "persistence_error": None,
        "connection_event_state": "CONNECTED",
    }), encoding="utf-8")


def _write_session(root: Path, *, trades, volume, sum_pv, bars, label_ready=False):
    p = root / "materialized" / "jnu_sessions.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "schema_version": "JNU.SESSION.MATERIALIZED.2",
        "sessions": {
            "JNU2612|NIGHT|2026-09-30": {
                "base_quote_code": "JNU2612",
                "contract_month": "202612",
                "session": "NIGHT",
                "session_start_date": "2026-09-30",
                "first_event_at": "2026-09-30T08:05:53+00:00",
                "last_event_at": "2026-09-30T11:00:00+00:00",
                "trade_count": trades,
                "total_volume": volume,
                "sum_price_volume": sum_pv,
                "bars": {f"bar-{i}": {} for i in range(bars)},
                "price_volume_bins": {"67100.0": volume},
                "price_trade_bins": {"67100.0": trades},
                "open_boundary_observed": False,
                "verified_close": False,
                "label_ready": label_ready,
            }
        },
    }), encoding="utf-8")


def test_window_summary_uses_counter_deltas_not_whole_session(tmp_path):
    _write_status(tmp_path)
    _write_session(tmp_path, trades=100, volume=500, sum_pv=33_500_000, bars=10)
    t0 = datetime(2026, 9, 30, 10, 55, tzinfo=timezone.utc)
    update_coverage(tmp_path, classification=HEALTHY_CLASSIFICATION, checked_at=t0)

    _write_session(tmp_path, trades=125, volume=620, sum_pv=41_552_000, bars=13)
    update_coverage(
        tmp_path,
        classification=HEALTHY_CLASSIFICATION,
        checked_at=t0 + timedelta(minutes=5),
    )
    out = build_summary(tmp_path)
    latest = out["latest_window"]
    session = latest["sessions"][0]
    assert session["window_trade_count"] == 25
    assert session["window_total_volume"] == 120
    assert round(session["window_vwap"], 4) == round((41_552_000 - 33_500_000) / 120, 4)
    assert session["new_5m_bar_count"] == 3
    assert session["usable_as_context"] is True
    assert session["full_session_label_ready"] is False
    assert "OFFICIAL_OPEN_BOUNDARY_NOT_OBSERVED" in session["label_block_reasons"]


def test_existing_active_window_without_baseline_is_honest_from_adoption_point(tmp_path):
    _write_status(tmp_path)
    _write_session(tmp_path, trades=100, volume=500, sum_pv=33_500_000, bars=10)
    coverage = tmp_path / "automation" / "jnu_capture_coverage.json"
    coverage.parent.mkdir(parents=True, exist_ok=True)
    coverage.write_text(json.dumps({
        "schema_version": "AV2.JNU.CAPTURE_COVERAGE.1",
        "intervals": [{
            "status": "ACTIVE",
            "started_at": "2026-09-30T10:00:00+00:00",
            "last_healthy_at": "2026-09-30T10:05:00+00:00",
            "started_local": "2026-09-30T18:00:00+08:00",
            "quote_only": True,
            "broker_order_action": False,
        }],
        "sessions": {},
    }), encoding="utf-8")
    now = datetime(2026, 9, 30, 10, 10, tzinfo=timezone.utc)
    state = update_coverage(tmp_path, classification=HEALTHY_CLASSIFICATION, checked_at=now)
    interval = state["intervals"][-1]
    assert interval["metrics_complete_from_window_start"] is False
    assert interval["metrics_baseline_at"] == now.isoformat()
    assert interval["metrics_baseline_reason"] == "BASELINE_ADOPTED_AFTER_WINDOW_START"


def test_next_start_closes_stale_prior_window_at_last_healthy_not_restart_time(tmp_path):
    _write_status(tmp_path)
    _write_session(tmp_path, trades=10, volume=20, sum_pv=1_340_000, bars=1)
    t0 = datetime(2026, 9, 30, 10, 55, tzinfo=timezone.utc)
    update_coverage(tmp_path, classification=HEALTHY_CLASSIFICATION, checked_at=t0)
    state = update_coverage(
        tmp_path,
        classification=HEALTHY_CLASSIFICATION,
        checked_at=t0 + timedelta(hours=2),
    )
    old, new = state["intervals"][-2:]
    assert old["status"] == "CLOSED"
    assert old["closed_at"] == t0.isoformat()
    assert old["close_reason"] == "HEALTHY_SAMPLE_GAP"
    assert new["status"] == "ACTIVE"
    assert new["started_at"] == (t0 + timedelta(hours=2)).isoformat()


def test_summary_carries_sampled_microstructure_quality_context(tmp_path):
    _write_status(tmp_path, callbacks=7)
    _write_session(tmp_path, trades=10, volume=20, sum_pv=1_340_000, bars=1)
    t0 = datetime(2026, 9, 30, 10, 55, tzinfo=timezone.utc)
    update_coverage(tmp_path, classification=HEALTHY_CLASSIFICATION, checked_at=t0)
    out = build_summary(tmp_path)
    runtime = out["latest_window"]["microstructure_context"]
    assert runtime["live_verified"] is True
    assert runtime["callbacks"]["stock_tick"] == 7
    assert runtime["dropped_records"] == 0
    assert out["latest_window"]["research_use"]["missing_time_backfill_allowed"] is False
