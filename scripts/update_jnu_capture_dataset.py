"""Append-only research dataset for immutable closed JNU capture windows."""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from market_ai_hub.integrations.yuanta.durable_spool import durable_json_replace
from market_ai_hub.integrations.yuanta.live_quote_recorder import recorder_root

SCHEMA_VERSION = "AV2.JNU.CAPTURE_WINDOW_DATASET.1"


def dataset_path(root: Path) -> Path:
    return Path(root) / "research" / "jnu_capture_window_dataset.json"


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "schema_version": SCHEMA_VERSION,
            "updated_at": None,
            "rows": [],
            "policy": {
                "closed_windows_only": True,
                "semantic_append_only": True,
                "existing_rows_mutable": False,
                "missing_time_backfill_allowed": False,
                "prediction_claims_allowed": False,
            },
        }
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        raw = {}
    if raw.get("schema_version") != SCHEMA_VERSION:
        return {
            "schema_version": SCHEMA_VERSION,
            "updated_at": None,
            "rows": [],
            "policy": {
                "closed_windows_only": True,
                "semantic_append_only": True,
                "existing_rows_mutable": False,
                "missing_time_backfill_allowed": False,
                "prediction_claims_allowed": False,
            },
        }
    return raw


def _load_summary(root: Path) -> dict[str, Any]:
    path = Path(root) / "research" / "jnu_capture_window_summary.json"
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def _canonical_hash(row: dict[str, Any]) -> str:
    payload = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _row_from_window(window: dict[str, Any]) -> dict[str, Any]:
    return {
        "window_id": window.get("window_id"),
        "status": window.get("status"),
        "started_at": window.get("started_at"),
        "started_local": window.get("started_local"),
        "last_healthy_at": window.get("last_healthy_at"),
        "closed_at": window.get("closed_at"),
        "close_reason": window.get("close_reason"),
        "observed_minutes": window.get("observed_minutes"),
        "gap_from_previous_verified_window_seconds": window.get(
            "gap_from_previous_verified_window_seconds"
        ),
        "metrics_baseline_at": window.get("metrics_baseline_at"),
        "metrics_latest_at": window.get("metrics_latest_at"),
        "metrics_complete_from_window_start": bool(
            window.get("metrics_complete_from_window_start")
        ),
        "metrics_baseline_reason": window.get("metrics_baseline_reason"),
        "session_context_snapshot_source": window.get("session_context_snapshot_source"),
        "microstructure_context": deepcopy(window.get("microstructure_context") or {}),
        "sessions": deepcopy(window.get("sessions") or []),
        "research_use": deepcopy(window.get("research_use") or {}),
        "quote_only": bool(window.get("quote_only")),
        "broker_order_action": bool(window.get("broker_order_action")),
    }


def update_dataset(root: Path) -> dict[str, Any]:
    root = Path(root)
    path = dataset_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    state = _load(path)
    rows = list(state.get("rows") or [])
    existing = {
        str(row.get("window_id")): row
        for row in rows
        if isinstance(row, dict) and row.get("window_id")
    }

    summary = _load_summary(root)
    appended = 0
    skipped_active = 0
    skipped_legacy = 0
    conflicts: list[str] = []

    for window in summary.get("windows") or []:
        if not isinstance(window, dict):
            continue
        if window.get("status") != "CLOSED":
            skipped_active += 1
            continue
        if window.get("session_context_snapshot_source") != "INTERVAL_LAST_VERIFIED_HEALTHY":
            skipped_legacy += 1
            continue
        row = _row_from_window(window)
        window_id = str(row.get("window_id") or "")
        if not window_id:
            continue
        prior = existing.get(window_id)
        if prior is not None:
            if _canonical_hash(prior) != _canonical_hash(row):
                conflicts.append(window_id)
            continue
        rows.append(row)
        existing[window_id] = row
        appended += 1

    if conflicts:
        return {
            "schema_version": SCHEMA_VERSION,
            "status": "IMMUTABILITY_CONFLICT",
            "conflict_window_ids": sorted(conflicts),
            "appended_count": 0,
            "row_count": len(state.get("rows") or []),
            "dataset_path": str(path),
        }

    state["schema_version"] = SCHEMA_VERSION
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    state["rows"] = rows
    state["row_count"] = len(rows)
    state["policy"] = {
        "closed_windows_only": True,
        "semantic_append_only": True,
        "existing_rows_mutable": False,
        "missing_time_backfill_allowed": False,
        "prediction_claims_allowed": False,
    }
    durable_json_replace(path, state)
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "PASS",
        "appended_count": appended,
        "row_count": len(rows),
        "skipped_active_count": skipped_active,
        "skipped_legacy_context_count": skipped_legacy,
        "dataset_path": str(path),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--recorder-root", type=Path)
    args = ap.parse_args()
    root = args.recorder_root or Path(recorder_root())
    result = update_dataset(root)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
