"""Zero-cost P5 local dispatch and storage-budget guards."""
from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
from zoneinfo import ZoneInfo

import scripts.dispatch_accuracy_v2_p5_zero_cost_fallback as dispatch
from scripts.validate_accuracy_v2_p5_cloud_artifact_budget import validate_budget

ROOT = Path(__file__).resolve().parents[1]
TAIPEI = ZoneInfo("Asia/Taipei")


def _run_row(*, event="schedule", status="queued", conclusion="", title="scheduled", hour=7, minute=40):
    return {
        "databaseId": 123,
        "event": event,
        "status": status,
        "conclusion": conclusion,
        "createdAt": f"2026-09-30T{hour-8 if hour >= 8 else hour+16:02d}:{minute:02d}:00Z",
        "displayTitle": title,
        "headBranch": "main",
    }


def test_relevant_run_accepts_native_schedule_or_local_marker_only():
    now = datetime(2026, 9, 30, 7, 52, tzinfo=TAIPEI)
    native = {
        "databaseId": 1, "event": "schedule", "status": "queued", "conclusion": "",
        "createdAt": "2026-09-29T23:40:00Z", "displayTitle": "schedule",
    }
    assert dispatch.relevant_run([native], now=now)["databaseId"] == 1
    manual_smoke = {
        "databaseId": 2, "event": "workflow_dispatch", "status": "completed",
        "conclusion": "success", "createdAt": "2026-09-29T23:45:00Z",
        "displayTitle": "P5 Cloud Public Forward (manual)",
    }
    assert dispatch.relevant_run([manual_smoke], now=now) is None
    local = dict(manual_smoke, databaseId=3, displayTitle=f"P5 ({dispatch.LOCAL_MARKER})")
    assert dispatch.relevant_run([local], now=now)["databaseId"] == 3


def test_dispatch_skips_existing_active_run(monkeypatch):
    calls = []
    def fake(args):
        calls.append(args)
        if args[:2] == ["auth", "status"]:
            return type("P", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        rows = [{
            "databaseId": 9, "event": "schedule", "status": "in_progress",
            "conclusion": "", "createdAt": "2026-09-29T23:40:00Z",
            "displayTitle": "schedule", "headBranch": "main",
        }]
        return type("P", (), {"returncode": 0, "stdout": json.dumps(rows), "stderr": ""})()
    monkeypatch.setattr(dispatch, "_run_gh", fake)
    out = dispatch.check_and_dispatch(now=datetime(2026, 9, 30, 7, 52, tzinfo=TAIPEI))
    assert out["status"] == "SKIP_EXISTING_ACTIVE_OR_SUCCESS"
    assert out["dispatch_performed"] is False
    assert not any(args[:2] == ["workflow", "run"] for args in calls)


def test_dispatch_uses_scheduled_mode_and_marker(monkeypatch):
    calls = []
    def fake(args):
        calls.append(args)
        if args[:2] == ["auth", "status"]:
            return type("P", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        if args[:2] == ["run", "list"]:
            return type("P", (), {"returncode": 0, "stdout": "[]", "stderr": ""})()
        return type("P", (), {"returncode": 0, "stdout": "", "stderr": ""})()
    monkeypatch.setattr(dispatch, "_run_gh", fake)
    out = dispatch.check_and_dispatch(now=datetime(2026, 9, 30, 8, 8, tzinfo=TAIPEI))
    assert out["status"] == "DISPATCHED"
    cmd = next(x for x in calls if x[:2] == ["workflow", "run"])
    assert "mode=scheduled" in cmd
    assert f"dispatch_source={dispatch.LOCAL_MARKER}" in cmd
    assert out["paid_service_required"] is False
    assert out["aws_required"] is False


def test_artifact_budget_passes_small_and_fails_oversize(tmp_path):
    for rel in (
        "audit/prediction_audit.duckdb",
        "automation/p5_forward_state.json",
        "cloud/p5_cloud_run_summary.json",
        "cloud/p5_cloud_state_manifest.json",
    ):
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x" * 16)
    assert validate_budget(tmp_path)["status"] == "PASS"
    (tmp_path / "audit/prediction_audit.duckdb").write_bytes(b"x" * (8 * 1024 * 1024 + 1))
    assert validate_budget(tmp_path)["status"] == "FAIL"


def test_workflow_is_standard_runner_bounded_retention_and_has_local_marker():
    text = (ROOT / ".github/workflows/p5-cloud-public-forward.yml").read_text(encoding="utf-8")
    assert "runs-on: ubuntu-24.04" in text
    assert "REPOSITORY_PRIVATE" in text
    assert 'test "$REPOSITORY_PRIVATE" = "false"' in text
    assert "larger" not in text.lower()
    assert "dispatch_source:" in text
    assert dispatch.LOCAL_MARKER in text
    assert "retention-days: 7" in text
    assert text.count("retention-days: 3") == 2
    assert "retention-days: 30" not in text
    assert "validate_accuracy_v2_p5_cloud_artifact_budget.py" in text


def test_registration_is_two_weekday_local_fallbacks_and_no_broker():
    text = (ROOT / "scripts/register_accuracy_v2_p5_zero_cost_fallback.ps1").read_text(encoding="utf-8")
    assert 'planned_times = @("07:52", "08:08")' in text
    assert "-At 07:52" in text and "-At 08:08" in text
    assert "aws_required = $false" in text
    assert "paid_service_required = $false" in text
    assert "broker_used = $false" in text
    assert "order_action = $false" in text
