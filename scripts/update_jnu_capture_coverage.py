"""Local zero-cost JNU capture-window coverage ledger.

This ledger records when the quote-only recorder is actually available on the user's
PC. The user's usual 18:55-22:00 window is informational, not a hard gate: earlier
or later availability is accepted. Missing time is never backfilled.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from market_ai_hub.integrations.yuanta.durable_spool import durable_json_replace
from market_ai_hub.integrations.yuanta.live_quote_recorder import recorder_root

SCHEMA_VERSION = "AV2.JNU.CAPTURE_COVERAGE.1"
TAIPEI = ZoneInfo("Asia/Taipei")
HEALTHY_CLASSIFICATION = "SAFE_DEFAULT_OWNER_HEALTHY"
MAX_HEALTHY_SAMPLE_GAP_SECONDS = 8 * 60
MAX_INTERVALS = 90
PREFERRED_WINDOW = {
    "timezone": "Asia/Taipei",
    "usual_start": "18:55",
    "usual_end": "22:00",
    "informational_only": True,
    "early_or_late_capture_allowed": True,
}


def coverage_path(root: Path) -> Path:
    return Path(root) / "automation" / "jnu_capture_coverage.json"


def _utc(value: datetime | None = None) -> datetime:
    out = value or datetime.now(timezone.utc)
    if out.tzinfo is None:
        out = out.replace(tzinfo=timezone.utc)
    return out.astimezone(timezone.utc)


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "schema_version": SCHEMA_VERSION,
            "updated_at": None,
            "preferred_window": deepcopy(PREFERRED_WINDOW),
            "intervals": [],
            "sessions": {},
        }
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        raw = {}
    if raw.get("schema_version") != SCHEMA_VERSION:
        raw = {}
    return {
        "schema_version": SCHEMA_VERSION,
        "updated_at": raw.get("updated_at"),
        "preferred_window": deepcopy(PREFERRED_WINDOW),
        "intervals": list(raw.get("intervals") or []),
        "sessions": dict(raw.get("sessions") or {}),
    }


def _close_interval(interval: dict[str, Any], *, reason: str) -> None:
    if interval.get("status") == "ACTIVE":
        interval["status"] = "CLOSED"
        interval["closed_at"] = interval.get("last_healthy_at")
        interval["close_reason"] = reason


def _materialized_sessions(root: Path) -> dict[str, Any]:
    path = Path(root) / "materialized" / "jnu_sessions.json"
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return raw.get("sessions") if isinstance(raw.get("sessions"), dict) else {}


def _session_counters(sessions: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for key, session in sessions.items():
        if not isinstance(session, dict):
            continue
        out[key] = {
            "trade_count": int(session.get("trade_count") or 0),
            "total_volume": float(session.get("total_volume") or 0.0),
            "sum_price_volume": float(session.get("sum_price_volume") or 0.0),
            "bar_count": len(session.get("bars") or {}),
            "price_volume_bin_count": len(session.get("price_volume_bins") or {}),
            "price_trade_bin_count": len(session.get("price_trade_bins") or {}),
            "last_event_at": session.get("last_event_at"),
        }
    return out


def _runtime_context(root: Path) -> dict[str, Any]:
    path = Path(root) / "status.json"
    if not path.exists():
        return {}
    try:
        status = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return {
        "jnu_microstructure_live_verified": bool(status.get("jnu_microstructure_live_verified")),
        "jnu_microstructure_callbacks": dict(status.get("jnu_microstructure_callbacks") or {}),
        "dropped_records": status.get("dropped_records"),
        "persistence_error": status.get("persistence_error"),
        "connection_event_state": status.get("connection_event_state"),
    }


def _session_summary(session: dict[str, Any]) -> dict[str, Any]:
    trade_count = int(session.get("trade_count") or 0)
    label_ready = bool(session.get("label_ready"))
    return {
        "base_quote_code": session.get("base_quote_code"),
        "contract_month": session.get("contract_month"),
        "session": session.get("session"),
        "session_start_date": session.get("session_start_date"),
        "expected_session_open": session.get("expected_session_open"),
        "expected_session_close": session.get("expected_session_close"),
        "first_event_at": session.get("first_event_at"),
        "last_event_at": session.get("last_event_at"),
        "trade_count": trade_count,
        "total_volume": session.get("total_volume"),
        "latest_price": session.get("latest_price"),
        "observed_high": session.get("observed_high"),
        "observed_low": session.get("observed_low"),
        "session_vwap": session.get("vwap"),
        "opening_range_high": session.get("opening_range_high"),
        "opening_range_low": session.get("opening_range_low"),
        "opening_range_complete": bool(session.get("opening_range_complete")),
        "open_boundary_observed": bool(session.get("open_boundary_observed")),
        "close_boundary_observed": bool(session.get("verified_close")),
        "full_session_label_ready": label_ready,
        "window_data_available": trade_count > 0,
        "usable_as_context": trade_count > 0,
        "coverage_class": "FULL_SESSION_LABEL_READY" if label_ready else "PARTIAL_WINDOW",
        "missing_open_boundary": not bool(session.get("open_boundary_observed")),
        "missing_close_boundary": not bool(session.get("verified_close")),
        "no_backfill": True,
    }


def update_coverage(
    root: Path,
    *,
    classification: str,
    checked_at: datetime | None = None,
    runtime_build_id: str = "",
) -> dict[str, Any]:
    root = Path(root)
    path = coverage_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    state = _load(path)
    now = _utc(checked_at)
    materialized = _materialized_sessions(root)
    counters = _session_counters(materialized)
    session_context = {
        key: _session_summary(value)
        for key, value in materialized.items()
        if isinstance(value, dict)
    }
    runtime_context = _runtime_context(root)
    intervals = state["intervals"]
    active = intervals[-1] if intervals and intervals[-1].get("status") == "ACTIVE" else None

    if classification == HEALTHY_CLASSIFICATION:
        if active is not None:
            try:
                last = datetime.fromisoformat(str(active.get("last_healthy_at"))).astimezone(timezone.utc)
                gap = (now - last).total_seconds()
            except Exception:
                gap = MAX_HEALTHY_SAMPLE_GAP_SECONDS + 1
            if gap > MAX_HEALTHY_SAMPLE_GAP_SECONDS:
                _close_interval(active, reason="HEALTHY_SAMPLE_GAP")
                active = None
        if active is None:
            local = now.astimezone(TAIPEI)
            active = {
                "status": "ACTIVE",
                "started_at": now.isoformat(),
                "last_healthy_at": now.isoformat(),
                "closed_at": None,
                "close_reason": None,
                "started_local": local.isoformat(),
                "runtime_build_id": runtime_build_id or None,
                "quote_only": True,
                "broker_order_action": False,
                "metrics_baseline_at": now.isoformat(),
                "metrics_latest_at": now.isoformat(),
                "metrics_complete_from_window_start": True,
                "metrics_baseline_reason": "WINDOW_START_COUNTER_SNAPSHOT",
                "session_baseline": deepcopy(counters),
                "session_latest": deepcopy(counters),
                "session_context_latest": deepcopy(session_context),
                "latest_runtime_context": deepcopy(runtime_context),
            }
            intervals.append(active)
        else:
            if not isinstance(active.get("session_baseline"), dict):
                active["metrics_baseline_at"] = now.isoformat()
                active["metrics_complete_from_window_start"] = False
                active["metrics_baseline_reason"] = "BASELINE_ADOPTED_AFTER_WINDOW_START"
                active["session_baseline"] = deepcopy(counters)
            active["last_healthy_at"] = now.isoformat()
            active["metrics_latest_at"] = now.isoformat()
            active["session_latest"] = deepcopy(counters)
            active["session_context_latest"] = deepcopy(session_context)
            active["latest_runtime_context"] = deepcopy(runtime_context)
            if runtime_build_id:
                active["runtime_build_id"] = runtime_build_id
    elif active is not None:
        _close_interval(active, reason=f"OWNER_{classification or 'UNVERIFIED'}")

    for interval in intervals:
        try:
            start = datetime.fromisoformat(str(interval["started_at"])).astimezone(timezone.utc)
            end = datetime.fromisoformat(str(interval["last_healthy_at"])).astimezone(timezone.utc)
            interval["observed_minutes"] = max(0.0, (end - start).total_seconds() / 60.0)
        except Exception:
            interval["observed_minutes"] = None

    state["intervals"] = intervals[-MAX_INTERVALS:]
    state["sessions"] = deepcopy(session_context)
    state["updated_at"] = now.isoformat()
    state["current_owner_classification"] = classification
    state["policy"] = {
        "full_session_is_optional": True,
        "partial_windows_are_preserved": True,
        "partial_windows_are_context_not_full_session_labels": True,
        "missing_time_is_never_backfilled": True,
        "pc_may_start_early_or_late": True,
        "pc_may_shut_down_before_session_close": True,
    }
    durable_json_replace(path, state)
    return deepcopy(state)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--recorder-root", type=Path)
    ap.add_argument("--classification", required=True)
    ap.add_argument("--runtime-build-id", default="")
    args = ap.parse_args()
    root = args.recorder_root or Path(recorder_root())
    state = update_coverage(
        root,
        classification=args.classification,
        runtime_build_id=args.runtime_build_id,
    )
    latest = state["intervals"][-1] if state["intervals"] else None
    print(json.dumps({
        "schema_version": state["schema_version"],
        "updated_at": state["updated_at"],
        "preferred_window": state["preferred_window"],
        "latest_interval": latest,
        "session_count": len(state["sessions"]),
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
