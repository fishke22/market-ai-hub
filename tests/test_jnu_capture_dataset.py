from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from scripts.update_jnu_capture_coverage import HEALTHY_CLASSIFICATION, update_coverage
from scripts.update_jnu_capture_dataset import update_dataset
from scripts.update_jnu_capture_research_summary import build_summary


def _status(root: Path):
    p = root / "status.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "jnu_microstructure_live_verified": True,
        "jnu_microstructure_callbacks": {"stock_tick": 3, "five_tick": 7},
        "dropped_records": 0,
        "persistence_error": None,
        "connection_event_state": "CONNECTED",
    }), encoding="utf-8")


def _session(root: Path, *, trades, volume, price, label_ready=False, open_seen=False, close_seen=False):
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
                "sum_price_volume": price * volume,
                "vwap": price,
                "latest_price": price,
                "observed_high": price + 20,
                "observed_low": price - 20,
                "bars": {"a": {}, "b": {}},
                "price_volume_bins": {str(price): volume},
                "price_trade_bins": {str(price): trades},
                "open_boundary_observed": open_seen,
                "verified_close": close_seen,
                "label_ready": label_ready,
            }
        },
    }), encoding="utf-8")


def test_active_window_is_not_appended(tmp_path):
    _status(tmp_path)
    _session(tmp_path, trades=10, volume=20, price=67100)
    t0 = datetime(2026, 9, 30, 10, 55, tzinfo=timezone.utc)
    update_coverage(tmp_path, classification=HEALTHY_CLASSIFICATION, checked_at=t0)
    build_summary(tmp_path)
    result = update_dataset(tmp_path)
    assert result["status"] == "PASS"
    assert result["appended_count"] == 0
    assert result["row_count"] == 0


def test_closed_window_uses_last_verified_context_not_later_session_state(tmp_path):
    _status(tmp_path)
    t0 = datetime(2026, 9, 30, 10, 55, tzinfo=timezone.utc)
    _session(tmp_path, trades=10, volume=20, price=67100)
    update_coverage(tmp_path, classification=HEALTHY_CLASSIFICATION, checked_at=t0)

    _session(tmp_path, trades=20, volume=40, price=67200)
    update_coverage(
        tmp_path,
        classification=HEALTHY_CLASSIFICATION,
        checked_at=t0 + timedelta(minutes=5),
    )

    # Two hours later, the same official session has changed substantially.
    # The old capture window must close using its last verified context (67200),
    # not this later materializer state.
    _session(
        tmp_path,
        trades=100,
        volume=200,
        price=68000,
        label_ready=True,
        open_seen=True,
        close_seen=True,
    )
    update_coverage(
        tmp_path,
        classification=HEALTHY_CLASSIFICATION,
        checked_at=t0 + timedelta(hours=2),
    )
    summary = build_summary(tmp_path)
    old = summary["windows"][0]
    assert old["status"] == "CLOSED"
    assert old["session_context_snapshot_source"] == "INTERVAL_LAST_VERIFIED_HEALTHY"
    assert old["sessions"][0]["session_context"]["latest_price"] == 67200
    assert old["sessions"][0]["full_session_label_ready"] is False

    result = update_dataset(tmp_path)
    assert result["appended_count"] == 1
    stored = json.loads(
        (tmp_path / "research" / "jnu_capture_window_dataset.json").read_text(encoding="utf-8")
    )
    row = stored["rows"][0]
    assert row["sessions"][0]["session_context"]["latest_price"] == 67200
    assert row["sessions"][0]["full_session_label_ready"] is False


def test_dataset_is_semantically_append_only_and_detects_rewrite(tmp_path):
    _status(tmp_path)
    t0 = datetime(2026, 9, 30, 10, 55, tzinfo=timezone.utc)
    _session(tmp_path, trades=10, volume=20, price=67100)
    update_coverage(tmp_path, classification=HEALTHY_CLASSIFICATION, checked_at=t0)
    update_coverage(
        tmp_path,
        classification=HEALTHY_CLASSIFICATION,
        checked_at=t0 + timedelta(minutes=20),
    )
    build_summary(tmp_path)
    first = update_dataset(tmp_path)
    assert first["appended_count"] == 1
    second = update_dataset(tmp_path)
    assert second["status"] == "PASS"
    assert second["appended_count"] == 0
    assert second["row_count"] == 1

    summary_path = tmp_path / "research" / "jnu_capture_window_summary.json"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    summary["windows"][0]["observed_minutes"] = 999
    summary_path.write_text(json.dumps(summary), encoding="utf-8")
    conflict = update_dataset(tmp_path)
    assert conflict["status"] == "IMMUTABILITY_CONFLICT"
    assert conflict["row_count"] == 1


def test_legacy_closed_window_without_context_snapshot_is_not_promoted(tmp_path):
    research = tmp_path / "research"
    research.mkdir(parents=True)
    (research / "jnu_capture_window_summary.json").write_text(json.dumps({
        "windows": [{
            "window_id": "legacy",
            "status": "CLOSED",
            "session_context_snapshot_source": "LEGACY_GLOBAL_FALLBACK",
            "sessions": [],
        }]
    }), encoding="utf-8")
    result = update_dataset(tmp_path)
    assert result["appended_count"] == 0
    assert result["skipped_legacy_context_count"] == 1
