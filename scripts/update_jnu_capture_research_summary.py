"""Research/quality summary for verified JNU capture windows."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from market_ai_hub.integrations.yuanta.durable_spool import durable_json_replace
from market_ai_hub.integrations.yuanta.live_quote_recorder import recorder_root

SCHEMA_VERSION = "AV2.JNU.CAPTURE_WINDOW_RESEARCH.1"
MAX_WINDOWS = 30


def summary_path(root: Path) -> Path:
    return Path(root) / "research" / "jnu_capture_window_summary.json"


def _load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def _number(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _integer(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _session_delta(
    key: str,
    *,
    baseline: dict[str, Any],
    latest: dict[str, Any],
    session: dict[str, Any],
) -> dict[str, Any]:
    base = baseline.get(key) if isinstance(baseline.get(key), dict) else None
    end = latest.get(key) if isinstance(latest.get(key), dict) else None
    full_label = bool(session.get("full_session_label_ready"))
    reasons: list[str] = []
    if not bool(session.get("open_boundary_observed")):
        reasons.append("OFFICIAL_OPEN_BOUNDARY_NOT_OBSERVED")
    if not bool(session.get("close_boundary_observed")):
        reasons.append("OFFICIAL_CLOSE_BOUNDARY_NOT_OBSERVED")
    if base is None or end is None:
        return {
            "session_key": key,
            "base_quote_code": session.get("base_quote_code"),
            "session": session.get("session"),
            "session_start_date": session.get("session_start_date"),
            "window_metrics_available": False,
            "window_metrics_reason": "WINDOW_COUNTER_BASELINE_NOT_AVAILABLE",
            "coverage_class": session.get("coverage_class"),
            "usable_as_context": bool(session.get("usable_as_context")),
            "full_session_label_ready": full_label,
            "label_block_reasons": reasons,
        }

    trades = max(0, _integer(end.get("trade_count")) - _integer(base.get("trade_count")))
    volume = max(0.0, _number(end.get("total_volume")) - _number(base.get("total_volume")))
    sum_pv = _number(end.get("sum_price_volume")) - _number(base.get("sum_price_volume"))
    vwap = (sum_pv / volume) if volume > 0 else None
    new_bars = max(0, _integer(end.get("bar_count")) - _integer(base.get("bar_count")))
    return {
        "session_key": key,
        "base_quote_code": session.get("base_quote_code"),
        "session": session.get("session"),
        "session_start_date": session.get("session_start_date"),
        "window_metrics_available": True,
        "window_trade_count": trades,
        "window_total_volume": volume,
        "window_vwap": vwap,
        "new_5m_bar_count": new_bars,
        "session_price_volume_profile_available": bool(end.get("price_volume_bin_count")),
        "session_price_trade_profile_available": bool(end.get("price_trade_bin_count")),
        "profile_semantics": "SESSION_CUMULATIVE_CONTEXT_NOT_WINDOW_SPECIFIC",
        "coverage_class": session.get("coverage_class"),
        "usable_as_context": bool(session.get("usable_as_context")) and trades > 0,
        "full_session_label_ready": full_label,
        "label_block_reasons": reasons,
    }


def build_summary(root: Path) -> dict[str, Any]:
    root = Path(root)
    coverage = _load_json(root / "automation" / "jnu_capture_coverage.json")
    intervals = list(coverage.get("intervals") or [])
    sessions = coverage.get("sessions") if isinstance(coverage.get("sessions"), dict) else {}
    windows: list[dict[str, Any]] = []
    previous_end: datetime | None = None

    for interval in intervals[-MAX_WINDOWS:]:
        if not isinstance(interval, dict):
            continue
        baseline = interval.get("session_baseline")
        latest = interval.get("session_latest")
        baseline = baseline if isinstance(baseline, dict) else {}
        latest = latest if isinstance(latest, dict) else {}
        session_keys = sorted(set(baseline) | set(latest))
        per_session = [
            _session_delta(
                key,
                baseline=baseline,
                latest=latest,
                session=sessions.get(key) if isinstance(sessions.get(key), dict) else {},
            )
            for key in session_keys
        ]
        per_session = [
            row
            for row in per_session
            if row.get("window_trade_count", 0) > 0
            or row.get("window_metrics_available") is False
            or row.get("full_session_label_ready")
        ]

        started = None
        last_healthy = None
        try:
            started = datetime.fromisoformat(str(interval.get("started_at"))).astimezone(timezone.utc)
            last_healthy = datetime.fromisoformat(str(interval.get("last_healthy_at"))).astimezone(timezone.utc)
        except Exception:
            pass
        gap_seconds = None
        if started is not None and previous_end is not None:
            gap_seconds = max(0.0, (started - previous_end).total_seconds())
        if last_healthy is not None:
            previous_end = last_healthy

        runtime = interval.get("latest_runtime_context")
        runtime = runtime if isinstance(runtime, dict) else {}
        windows.append({
            "window_id": interval.get("started_at"),
            "status": interval.get("status"),
            "started_at": interval.get("started_at"),
            "started_local": interval.get("started_local"),
            "last_healthy_at": interval.get("last_healthy_at"),
            "closed_at": interval.get("closed_at"),
            "close_reason": interval.get("close_reason"),
            "observed_minutes": interval.get("observed_minutes"),
            "gap_from_previous_verified_window_seconds": gap_seconds,
            "metrics_baseline_at": interval.get("metrics_baseline_at"),
            "metrics_latest_at": interval.get("metrics_latest_at"),
            "metrics_complete_from_window_start": bool(
                interval.get("metrics_complete_from_window_start", False)
            ),
            "metrics_baseline_reason": interval.get("metrics_baseline_reason"),
            "quote_only": bool(interval.get("quote_only")),
            "broker_order_action": bool(interval.get("broker_order_action")),
            "microstructure_context": {
                "live_verified": bool(runtime.get("jnu_microstructure_live_verified")),
                "callbacks": runtime.get("jnu_microstructure_callbacks") or {},
                "dropped_records": runtime.get("dropped_records"),
                "persistence_error": runtime.get("persistence_error"),
                "connection_event_state": runtime.get("connection_event_state"),
            },
            "sessions": per_session,
            "research_use": {
                "partial_window_context_allowed": True,
                "full_session_label_requires_real_boundaries": True,
                "missing_time_backfill_allowed": False,
                "prediction_gain_claim_allowed": False,
                "calibrated_probability_claim_allowed": False,
                "trading_edge_claim_allowed": False,
            },
        })

    out = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_coverage_schema": coverage.get("schema_version"),
        "preferred_window": coverage.get("preferred_window"),
        "policy": coverage.get("policy"),
        "windows": windows,
        "latest_window": windows[-1] if windows else None,
    }
    path = summary_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    durable_json_replace(path, out)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--recorder-root", type=Path)
    args = ap.parse_args()
    root = args.recorder_root or Path(recorder_root())
    out = build_summary(root)
    latest = out.get("latest_window")
    print(json.dumps({
        "schema_version": out["schema_version"],
        "generated_at": out["generated_at"],
        "window_count": len(out["windows"]),
        "latest_window": latest,
        "artifact_path": str(summary_path(root)),
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
