from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from scripts.update_jnu_capture_brief import build_brief, markdown_path
from scripts.update_jnu_capture_coverage import HEALTHY_CLASSIFICATION, update_coverage
from scripts.update_jnu_capture_research_summary import build_summary


def _write_status(root: Path):
    p = root / "status.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "jnu_microstructure_live_verified": True,
        "jnu_microstructure_callbacks": {"stock_tick": 20, "five_tick": 100},
        "dropped_records": 0,
        "persistence_error": None,
        "connection_event_state": "CONNECTED",
    }), encoding="utf-8")


def _write_session(root: Path, *, trades, volume, sum_pv, latest=67150.0):
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
                "vwap": sum_pv / volume,
                "latest_price": latest,
                "observed_high": 67510.0,
                "observed_low": 67120.0,
                "bars": {"a": {}, "b": {}},
                "price_volume_bins": {"67150.0": volume},
                "price_trade_bins": {"67150.0": trades},
                "open_boundary_observed": False,
                "verified_close": False,
                "label_ready": False,
            }
        },
    }), encoding="utf-8")


def test_brief_is_human_readable_and_keeps_claims_blocked(tmp_path):
    _write_status(tmp_path)
    _write_session(tmp_path, trades=100, volume=500, sum_pv=33_575_000)
    t0 = datetime(2026, 9, 30, 10, 55, tzinfo=timezone.utc)
    update_coverage(tmp_path, classification=HEALTHY_CLASSIFICATION, checked_at=t0)
    _write_session(tmp_path, trades=125, volume=620, sum_pv=41_637_000, latest=67140.0)
    update_coverage(
        tmp_path,
        classification=HEALTHY_CLASSIFICATION,
        checked_at=t0 + timedelta(minutes=5),
    )
    build_summary(tmp_path)
    out = build_brief(tmp_path)
    assert out["status"] == "ACTIVE_CAPTURE"
    assert out["authorization_required"] is False
    assert out["claims"] == {
        "predictive_gain": False,
        "calibrated_probability": False,
        "trading_edge": False,
        "order_action": False,
    }
    session = out["sessions"][0]
    assert session["window_trade_count"] == 25
    assert session["session_latest_price"] == 67140.0
    assert session["full_session_label_ready"] is False
    assert "未觀察到官方開盤邊界" in session["label_block_reasons_zh_tw"]
    text = markdown_path(tmp_path).read_text(encoding="utf-8")
    assert "現在可以做" in text
    assert "現在不能宣稱／不能做" in text
    assert "JNU2612" in text


def test_brief_reports_incomplete_baseline_without_backfill(tmp_path):
    _write_status(tmp_path)
    _write_session(tmp_path, trades=100, volume=500, sum_pv=33_575_000)
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
    update_coverage(
        tmp_path,
        classification=HEALTHY_CLASSIFICATION,
        checked_at=datetime(2026, 9, 30, 10, 10, tzinfo=timezone.utc),
    )
    build_summary(tmp_path)
    out = build_brief(tmp_path)
    assert out["capture_window"]["metrics_complete_from_window_start"] is False
    assert "不倒算、不補造" in out["capture_window"]["metrics_note_zh_tw"]
    assert any("缺失時間不得回填" in x for x in out["cannot_claim_or_do_zh_tw"])
