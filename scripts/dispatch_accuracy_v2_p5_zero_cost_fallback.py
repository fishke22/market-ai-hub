"""Zero-cost local fallback dispatcher for the public P5 GitHub workflow."""
from __future__ import annotations

import argparse
from datetime import datetime, time
import json
import subprocess
from typing import Any
from zoneinfo import ZoneInfo

TAIPEI = ZoneInfo("Asia/Taipei")
WORKFLOW = "p5-cloud-public-forward.yml"
BRANCH = "main"
LOCAL_MARKER = "local-zero-cost-fallback"
WINDOW_START = time(7, 35)
WINDOW_END = time(8, 19)
LOCAL_ACTIVE_STATUSES = {"queued", "in_progress", "waiting", "pending", "requested"}
NATIVE_STARTED_STATUSES = {"in_progress", "waiting"}
GOOD_CONCLUSIONS = {"success"}


def _run_gh(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["gh", *args], check=False, capture_output=True, text=True, timeout=30
    )


def _parse_stamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(TAIPEI)


def relevant_run(rows: list[dict[str, Any]], *, now: datetime) -> dict[str, Any] | None:
    local = now.astimezone(TAIPEI)
    start = datetime.combine(local.date(), WINDOW_START, tzinfo=TAIPEI)
    for row in sorted(rows, key=lambda x: str(x.get("createdAt") or ""), reverse=True):
        try:
            created = _parse_stamp(str(row.get("createdAt") or ""))
        except Exception:
            continue
        if created < start:
            continue
        event = str(row.get("event") or "")
        title = str(row.get("displayTitle") or "")
        is_native = event == "schedule"
        is_local = LOCAL_MARKER in title
        if not is_native and not is_local:
            continue
        status = str(row.get("status") or "").lower()
        conclusion = str(row.get("conclusion") or "").lower()
        # A queued native cron is not punctuality evidence: queue delay is exactly
        # what this fallback is meant to bypass. A prior local fallback, however,
        # must suppress another local dispatch even while it is still queued.
        if is_native and (
            status in NATIVE_STARTED_STATUSES or conclusion in GOOD_CONCLUSIONS
        ):
            return row
        if is_local and (
            status in LOCAL_ACTIVE_STATUSES or conclusion in GOOD_CONCLUSIONS
        ):
            return row
    return None


def check_and_dispatch(*, now: datetime | None = None, dry_run: bool = False) -> dict[str, Any]:
    local = (now or datetime.now(TAIPEI)).astimezone(TAIPEI)
    result: dict[str, Any] = {
        "schema": "AV2.P5.ZERO_COST_DISPATCH.1",
        "checked_at": local.isoformat(),
        "status": "BLOCKED",
        "dispatch_performed": False,
        "paid_service_required": False,
        "aws_required": False,
        "broker_used": False,
        "recorder_touched": False,
        "order_action": False,
    }
    if local.weekday() >= 5:
        result.update(status="IDLE_NON_WEEKDAY")
        return result
    current = local.time().replace(tzinfo=None)
    if current < WINDOW_START or current > WINDOW_END:
        result.update(status="IDLE_OUTSIDE_WINDOW")
        return result

    auth = _run_gh(["auth", "status"])
    if auth.returncode != 0:
        result.update(status="BLOCKED_GH_AUTH_UNAVAILABLE")
        return result

    proc = _run_gh([
        "run", "list", "--workflow", WORKFLOW, "--branch", BRANCH, "--limit", "20",
        "--json", "databaseId,event,status,conclusion,createdAt,displayTitle,headBranch",
    ])
    if proc.returncode != 0:
        result.update(status="BLOCKED_RUN_LIST_FAILED")
        return result
    try:
        rows = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        result.update(status="BLOCKED_RUN_LIST_INVALID_JSON")
        return result
    existing = relevant_run(rows if isinstance(rows, list) else [], now=local)
    if existing is not None:
        result.update(
            status="SKIP_EXISTING_ACTIVE_OR_SUCCESS",
            existing_run_id=existing.get("databaseId"),
            existing_event=existing.get("event"),
            existing_status=existing.get("status"),
            existing_conclusion=existing.get("conclusion"),
        )
        return result

    if dry_run:
        result.update(status="DRY_RUN_WOULD_DISPATCH")
        return result

    dispatched = _run_gh([
        "workflow", "run", WORKFLOW, "--ref", BRANCH,
        "-f", "mode=scheduled",
        "-f", f"dispatch_source={LOCAL_MARKER}",
    ])
    if dispatched.returncode != 0:
        result.update(status="DISPATCH_FAILED")
        return result
    result.update(status="DISPATCHED", dispatch_performed=True)
    return result


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    result = check_and_dispatch(dry_run=args.dry_run)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] not in {
        "BLOCKED_GH_AUTH_UNAVAILABLE", "BLOCKED_RUN_LIST_FAILED",
        "BLOCKED_RUN_LIST_INVALID_JSON", "DISPATCH_FAILED",
    } else 2


if __name__ == "__main__":
    raise SystemExit(main())
