"""Capture-gap audit tests: expected absence vs real capture loss."""
from __future__ import annotations

import sys
from datetime import datetime, timezone

import pytest

sys.path.insert(0, "src")

from market_ai_hub.research.v2 import capture_gap_audit as GA

UTC = timezone.utc


def _store(tmp_path, day, ticks):
    import duckdb

    part = tmp_path / "parquet" / day
    part.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("CREATE TABLE t (received_at VARCHAR, market_no BIGINT, instrument_code VARCHAR)")
    for t in ticks:
        con.execute("INSERT INTO t VALUES (?, 207, 'JNUPM2612')", [t])
    con.execute(f"COPY t TO '{(part / 'p.parquet').as_posix()}' (FORMAT PARQUET)")
    con.close()
    return tmp_path / "parquet"


def _journal(tmp_path, events):
    from market_ai_hub.integrations.yuanta.live_quote_recorder import lifecycle_path

    path = lifecycle_path(tmp_path / "parquet")
    path.parent.mkdir(parents=True, exist_ok=True)
    import json

    with path.open("w", encoding="utf-8", newline="") as fh:
        for at, event in events:
            fh.write(json.dumps({"at": at, "event": event}) + "\n")


def _always_open(_markets, _ts):
    return True, ["CME"]


def _always_closed(_markets, _ts):
    return False, []


def test_gap_while_recorder_running_and_venue_open_is_real_loss(tmp_path):
    root = _store(tmp_path, "2026-10-02",
                  ["2026-10-02T10:00:00+00:00", "2026-10-02T12:00:00+00:00"])
    _journal(tmp_path, [("2026-10-02T09:00:00+00:00", "START")])
    a = GA.audit_capture_gaps(root, "2026-10-02", session_probe=_always_open)
    assert len(a.gaps) == 1
    assert a.gaps[0].classification == GA.GAP_CAPTURE_LOSS_WHILE_RUNNING
    assert a.loss_seconds == pytest.approx(7200.0)
    assert a.expected_seconds == 0.0


def test_gap_with_recorder_stopped_is_expected(tmp_path):
    root = _store(tmp_path, "2026-10-02",
                  ["2026-10-02T10:00:00+00:00", "2026-10-02T12:00:00+00:00"])
    # the recorder is up before and after the hole, but off for the whole hole
    _journal(tmp_path, [("2026-10-02T09:00:00+00:00", "START"),
                        ("2026-10-02T09:30:00+00:00", "STOP"),
                        ("2026-10-02T13:00:00+00:00", "START")])
    a = GA.audit_capture_gaps(root, "2026-10-02", session_probe=_always_open)
    assert a.gaps[0].classification == GA.GAP_RECORDER_OFF_EXPECTED
    assert a.loss_seconds == 0.0


def test_gap_without_liveness_record_is_not_guessed(tmp_path):
    root = _store(tmp_path, "2026-10-02",
                  ["2026-10-02T10:00:00+00:00", "2026-10-02T12:00:00+00:00"])
    a = GA.audit_capture_gaps(root, "2026-10-02", session_probe=_always_open)
    assert a.gaps[0].classification == GA.GAP_UNCLASSIFIED
    assert a.loss_seconds == 0.0          # never claim loss we cannot prove


def test_gap_with_every_venue_closed_is_expected(tmp_path):
    root = _store(tmp_path, "2026-10-02",
                  ["2026-10-02T09:00:00+00:00", "2026-10-02T11:00:00+00:00"])
    _journal(tmp_path, [("2026-10-02T08:00:00+00:00", "START")])
    a = GA.audit_capture_gaps(root, "2026-10-02", session_probe=_always_closed)
    assert a.gaps[0].classification == GA.GAP_MARKET_CLOSED_EXPECTED
    assert a.loss_seconds == 0.0


def test_short_gaps_are_ignored_and_result_is_content_addressed(tmp_path):
    root = _store(tmp_path, "2026-10-02",
                  ["2026-10-02T10:00:00+00:00", "2026-10-02T10:00:30+00:00",
                   "2026-10-02T12:00:00+00:00"])
    _journal(tmp_path, [("2026-10-02T09:00:00+00:00", "START")])
    a1 = GA.audit_capture_gaps(root, "2026-10-02", session_probe=_always_open)
    a2 = GA.audit_capture_gaps(root, "2026-10-02", session_probe=_always_open)
    assert len(a1.gaps) == 1                       # the 30 s gap is below the threshold
    assert a1.audit_id and a1.audit_id == a2.audit_id
    assert a1.model_dump() == a2.model_dump()


def test_liveness_helper_never_invents_state():
    now = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
    iv = [(datetime(2026, 10, 2, 9, 0, tzinfo=UTC), datetime(2026, 10, 2, 10, 0, tzinfo=UTC))]
    inside = (datetime(2026, 10, 2, 9, 30, tzinfo=UTC), datetime(2026, 10, 2, 9, 45, tzinfo=UTC))
    after = (datetime(2026, 10, 2, 11, 0, tzinfo=UTC), datetime(2026, 10, 2, 11, 30, tzinfo=UTC))
    assert GA._liveness(iv, *inside, now) == "RUNNING"
    assert GA._liveness(iv, *after, now) == "OFF"
    assert GA._liveness([], *inside, now) == "UNKNOWN"
    # far outside the journal's span -> unknown, not "off"
    far = (datetime(2026, 9, 1, 0, 0, tzinfo=UTC), datetime(2026, 9, 1, 1, 0, tzinfo=UTC))
    assert GA._liveness(iv, *far, now) == "UNKNOWN"


def test_unknown_classification_is_rejected():
    with pytest.raises(GA.CaptureGapAuditError):
        GA.CaptureGapAudit(day="2026-10-02", tick_count=1, first_tick=None, last_tick=None,
                           span_seconds=1.0, expected_seconds=0.0, loss_seconds=0.0,
                           gaps=[GA.CaptureGap(start="a", end="b", seconds=1.0,
                                               classification="MADE_UP")])


def test_missing_store_is_unreadable_not_fabricated(tmp_path):
    a = GA.audit_capture_gaps(tmp_path / "parquet", "2026-10-02", session_probe=_always_open)
    assert a.tick_count == 0 and a.gaps == [] and a.loss_seconds == 0.0


def test_gap_partially_covering_a_running_window_is_not_claimed_expected(tmp_path):
    root = _store(tmp_path, "2026-10-02",
                  ["2026-10-02T10:00:00+00:00", "2026-10-02T12:00:00+00:00"])
    _journal(tmp_path, [("2026-10-02T09:00:00+00:00", "START"),
                        ("2026-10-02T10:30:00+00:00", "STOP"),
                        ("2026-10-02T12:30:00+00:00", "START")])
    a = GA.audit_capture_gaps(root, "2026-10-02", session_probe=_always_open)
    assert a.gaps[0].classification == GA.GAP_CAPTURE_LOSS_WHILE_RUNNING
