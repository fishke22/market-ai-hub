import json
from pathlib import Path

from scripts.update_jnu_capture_window_rollup import build_rollup, markdown_path


def _write_dataset(root: Path, rows):
    p = root / "research" / "jnu_capture_window_dataset.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "schema_version": "AV2.JNU.CAPTURE_WINDOW_DATASET.1",
        "updated_at": "2026-10-01T00:00:00+00:00",
        "rows": rows,
    }), encoding="utf-8")


def _row(window_id, *, start_date="2026-09-30", minutes=30, complete=True, vwap=100.0, volume=10, trades=5):
    return {
        "window_id": window_id,
        "status": "CLOSED",
        "started_at": window_id,
        "last_healthy_at": window_id,
        "close_reason": "OWNER_NO_RUNNING_OWNER",
        "observed_minutes": minutes,
        "metrics_complete_from_window_start": complete,
        "quote_only": True,
        "broker_order_action": False,
        "microstructure_context": {
            "live_verified": True,
            "dropped_records": 0,
            "persistence_error": None,
        },
        "sessions": [{
            "base_quote_code": "JNU2612",
            "session": "NIGHT",
            "session_start_date": start_date,
            "window_trade_count": trades,
            "window_total_volume": volume,
            "window_vwap": vwap,
            "new_5m_bar_count": 2,
            "usable_as_context": True,
            "full_session_label_ready": False,
        }],
        "research_use": {
            "prediction_gain_claim_allowed": False,
            "calibrated_probability_claim_allowed": False,
            "trading_edge_claim_allowed": False,
        },
    }


def test_rollup_does_not_treat_two_windows_same_session_as_two_independent_sessions(tmp_path):
    _write_dataset(tmp_path, [
        _row("2026-09-30T10:00:00+00:00", minutes=30, complete=False, vwap=100, volume=10, trades=5),
        _row("2026-09-30T14:00:00+00:00", minutes=60, complete=True, vwap=110, volume=30, trades=15),
    ])
    out = build_rollup(tmp_path)
    assert out["status"] == "PASS"
    assert out["window_count"] == 2
    assert out["unique_market_session_count"] == 1
    assert out["market_sessions_with_multiple_windows_count"] == 1
    assert out["quality"]["metrics_complete_from_window_start_count"] == 1
    assert out["quality"]["metrics_incomplete_from_window_start_count"] == 1
    assert out["quality"]["observed_minutes"]["total"] == 90
    instrument = out["instruments"][0]
    assert instrument["window_count"] == 2
    assert instrument["market_session_count"] == 1
    assert instrument["window_trade_count_total"] == 20
    assert instrument["window_total_volume"] == 40
    assert instrument["capture_volume_weighted_vwap"] == 107.5
    assert instrument["statistical_independence_assumed"] is False
    assert out["research_interpretation"]["prediction_performance_evaluated"] is False


def test_rollup_counts_distinct_market_sessions_by_session_and_date(tmp_path):
    _write_dataset(tmp_path, [
        _row("2026-09-30T10:00:00+00:00", start_date="2026-09-30"),
        _row("2026-10-01T10:00:00+00:00", start_date="2026-10-01"),
    ])
    out = build_rollup(tmp_path)
    assert out["window_count"] == 2
    assert out["unique_market_session_count"] == 2
    assert out["market_sessions_with_multiple_windows_count"] == 0
    assert out["instruments"][0]["market_session_count"] == 2


def test_rollup_keeps_claims_blocked_and_reports_zero_broker_actions(tmp_path):
    _write_dataset(tmp_path, [_row("2026-09-30T10:00:00+00:00")])
    out = build_rollup(tmp_path)
    interp = out["research_interpretation"]
    assert interp["predictive_gain_claim_allowed"] is False
    assert interp["calibrated_probability_claim_allowed"] is False
    assert interp["trading_edge_claim_allowed"] is False
    assert out["quality"]["broker_order_action_window_count"] == 0
    text = markdown_path(tmp_path).read_text(encoding="utf-8")
    assert "window_count 不等於獨立市場樣本數" in text
    assert "PREDICTIVE_GAIN=false" in text


def test_rollup_handles_empty_dataset_without_inventing_evidence(tmp_path):
    _write_dataset(tmp_path, [])
    out = build_rollup(tmp_path)
    assert out["status"] == "NO_CLOSED_WINDOWS"
    assert out["window_count"] == 0
    assert out["unique_market_session_count"] == 0
    assert out["quality"]["observed_minutes"]["count"] == 0
    assert out["instruments"] == []
