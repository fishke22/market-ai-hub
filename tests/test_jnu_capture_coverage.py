from datetime import datetime, timedelta, timezone
import json
from pathlib import Path

from scripts.update_jnu_capture_coverage import (
    HEALTHY_CLASSIFICATION,
    PREFERRED_WINDOW,
    update_coverage,
)


def _write_materialized(root: Path, *, label_ready=False, open_seen=False, close_seen=False):
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
                "expected_session_open": "2026-09-30T08:00:00+00:00",
                "expected_session_close": "2026-09-30T21:00:00+00:00",
                "first_event_at": "2026-09-30T08:05:53+00:00",
                "last_event_at": "2026-09-30T14:00:00+00:00",
                "trade_count": 100,
                "total_volume": 500,
                "open_boundary_observed": open_seen,
                "verified_close": close_seen,
                "label_ready": label_ready,
            }
        },
    }), encoding="utf-8")


def test_usual_1855_2200_is_informational_not_hard_gate(tmp_path):
    _write_materialized(tmp_path)
    assert PREFERRED_WINDOW["usual_start"] == "18:55"
    assert PREFERRED_WINDOW["usual_end"] == "22:00"
    assert PREFERRED_WINDOW["informational_only"] is True
    early = datetime(2026, 9, 30, 8, 10, tzinfo=timezone.utc)  # 16:10 Taipei
    state = update_coverage(tmp_path, classification=HEALTHY_CLASSIFICATION, checked_at=early)
    assert state["intervals"][-1]["status"] == "ACTIVE"
    assert state["policy"]["pc_may_start_early_or_late"] is True


def test_healthy_samples_extend_window_and_long_gap_starts_new_window(tmp_path):
    _write_materialized(tmp_path)
    t0 = datetime(2026, 9, 30, 10, 55, tzinfo=timezone.utc)  # 18:55 Taipei
    update_coverage(tmp_path, classification=HEALTHY_CLASSIFICATION, checked_at=t0)
    state = update_coverage(
        tmp_path,
        classification=HEALTHY_CLASSIFICATION,
        checked_at=t0 + timedelta(minutes=5),
    )
    assert len(state["intervals"]) == 1
    assert state["intervals"][0]["observed_minutes"] == 5
    state = update_coverage(
        tmp_path,
        classification=HEALTHY_CLASSIFICATION,
        checked_at=t0 + timedelta(minutes=20),
    )
    assert len(state["intervals"]) == 2
    assert state["intervals"][0]["status"] == "CLOSED"
    assert state["intervals"][0]["close_reason"] == "HEALTHY_SAMPLE_GAP"
    assert state["intervals"][1]["status"] == "ACTIVE"


def test_partial_window_remains_useful_context_but_not_full_label(tmp_path):
    _write_materialized(tmp_path, label_ready=False, open_seen=False, close_seen=False)
    state = update_coverage(
        tmp_path,
        classification=HEALTHY_CLASSIFICATION,
        checked_at=datetime(2026, 9, 30, 11, 0, tzinfo=timezone.utc),
    )
    session = state["sessions"]["JNU2612|NIGHT|2026-09-30"]
    assert session["coverage_class"] == "PARTIAL_WINDOW"
    assert session["usable_as_context"] is True
    assert session["full_session_label_ready"] is False
    assert session["missing_open_boundary"] is True
    assert state["policy"]["missing_time_is_never_backfilled"] is True


def test_full_session_label_ready_is_preserved_when_materializer_proves_it(tmp_path):
    _write_materialized(tmp_path, label_ready=True, open_seen=True, close_seen=True)
    state = update_coverage(
        tmp_path,
        classification=HEALTHY_CLASSIFICATION,
        checked_at=datetime(2026, 9, 30, 21, 1, tzinfo=timezone.utc),
    )
    session = state["sessions"]["JNU2612|NIGHT|2026-09-30"]
    assert session["coverage_class"] == "FULL_SESSION_LABEL_READY"
    assert session["full_session_label_ready"] is True
    assert session["missing_open_boundary"] is False
    assert session["missing_close_boundary"] is False


def test_nonhealthy_sample_closes_active_verified_window(tmp_path):
    _write_materialized(tmp_path)
    t0 = datetime(2026, 9, 30, 10, 55, tzinfo=timezone.utc)
    update_coverage(tmp_path, classification=HEALTHY_CLASSIFICATION, checked_at=t0)
    state = update_coverage(
        tmp_path,
        classification="SAFE_DEFAULT_OWNER_DEGRADED",
        checked_at=t0 + timedelta(minutes=5),
    )
    assert state["intervals"][-1]["status"] == "CLOSED"
    assert state["intervals"][-1]["close_reason"] == "OWNER_SAFE_DEFAULT_OWNER_DEGRADED"
