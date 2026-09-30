import json
from pathlib import Path

from scripts.update_jnu_market_session_view import build_view, markdown_path


def _write_dataset(root: Path, rows):
    p = root / "research" / "jnu_capture_window_dataset.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "schema_version": "AV2.JNU.CAPTURE_WINDOW_DATASET.1",
        "updated_at": "2026-10-01T00:00:00+00:00",
        "rows": rows,
    }), encoding="utf-8")


def _row(window_id, *, date="2026-09-30", latest=100, full=False, volume=10, trades=5, complete=True):
    return {
        "window_id": window_id,
        "status": "CLOSED",
        "started_at": window_id,
        "last_healthy_at": window_id,
        "close_reason": "OWNER_NO_RUNNING_OWNER",
        "observed_minutes": 30,
        "metrics_complete_from_window_start": complete,
        "microstructure_context": {
            "live_verified": True,
            "dropped_records": 0,
            "persistence_error": None,
        },
        "sessions": [{
            "base_quote_code": "JNU2612",
            "session": "NIGHT",
            "session_start_date": date,
            "window_trade_count": trades,
            "window_total_volume": volume,
            "window_vwap": latest,
            "new_5m_bar_count": 2,
            "usable_as_context": True,
            "full_session_label_ready": full,
            "session_context": {"latest_price": latest},
        }],
    }


def test_two_windows_same_session_become_one_market_session_row(tmp_path):
    _write_dataset(tmp_path, [
        _row("2026-09-30T10:00:00+00:00", latest=100, volume=10, trades=5, complete=False),
        _row("2026-09-30T14:00:00+00:00", latest=110, volume=30, trades=15),
    ])
    out = build_view(tmp_path)
    assert out["capture_window_count"] == 2
    assert out["market_session_count"] == 1
    session = out["market_sessions"][0]
    assert session["capture_window_count"] == 2
    assert session["segmented_capture"] is True
    assert session["metrics_complete_from_window_start_count"] == 1
    assert session["metrics_incomplete_from_window_start_count"] == 1
    item = session["instruments"][0]
    assert item["captured_trade_count_total"] == 20
    assert item["captured_volume_total"] == 40
    assert item["captured_volume_weighted_vwap"] == 107.5
    assert item["market_session_full_session_label_ready"] is False


def test_segmented_capture_never_upgrades_full_session_label_even_if_sources_say_ready(tmp_path):
    _write_dataset(tmp_path, [
        _row("2026-09-30T10:00:00+00:00", full=True),
        _row("2026-09-30T14:00:00+00:00", full=True),
    ])
    out = build_view(tmp_path)
    item = out["market_sessions"][0]["instruments"][0]
    assert item["source_full_session_label_ready_count"] == 2
    assert item["market_session_full_session_label_ready"] is False


def test_single_unsegmented_full_session_can_preserve_row_level_ready(tmp_path):
    _write_dataset(tmp_path, [
        _row("2026-09-30T10:00:00+00:00", full=True),
    ])
    out = build_view(tmp_path)
    item = out["market_sessions"][0]["instruments"][0]
    assert item["market_session_full_session_label_ready"] is True


def test_different_session_dates_produce_distinct_rows(tmp_path):
    _write_dataset(tmp_path, [
        _row("2026-09-30T10:00:00+00:00", date="2026-09-30"),
        _row("2026-10-01T10:00:00+00:00", date="2026-10-01"),
    ])
    out = build_view(tmp_path)
    assert out["capture_window_count"] == 2
    assert out["market_session_count"] == 2


def test_market_session_view_keeps_prediction_claims_blocked(tmp_path):
    _write_dataset(tmp_path, [_row("2026-09-30T10:00:00+00:00")])
    out = build_view(tmp_path)
    research = out["market_sessions"][0]["research_use"]
    assert research["prediction_performance_evaluated"] is False
    assert research["predictive_gain_claim_allowed"] is False
    assert research["calibrated_probability_claim_allowed"] is False
    assert research["trading_edge_claim_allowed"] is False
    text = markdown_path(tmp_path).read_text(encoding="utf-8")
    assert "一個 market session 一列" in text
    assert "PREDICTIVE_GAIN=false" in text
