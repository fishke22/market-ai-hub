"""Deterministic market-session view derived from immutable JNU capture windows."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any

from market_ai_hub.integrations.yuanta.durable_spool import durable_json_replace
from market_ai_hub.integrations.yuanta.live_quote_recorder import recorder_root

SCHEMA_VERSION = "AV2.JNU.MARKET_SESSION_VIEW.1"


def view_path(root: Path) -> Path:
    return Path(root) / "research" / "jnu_market_session_view.json"


def markdown_path(root: Path) -> Path:
    return Path(root) / "research" / "jnu_market_session_view_zh_tw.md"


def dataset_path(root: Path) -> Path:
    return Path(root) / "research" / "jnu_capture_window_dataset.json"


def _load_dataset(root: Path) -> dict[str, Any]:
    path = dataset_path(root)
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def _rows_hash(rows: list[dict[str, Any]]) -> str:
    payload = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _market_session_key(session: dict[str, Any]) -> str | None:
    session_name = session.get("session")
    start_date = session.get("session_start_date")
    if not session_name or not start_date:
        return None
    return f"{session_name}|{start_date}"


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


def _parse_time(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value)).astimezone(timezone.utc)
    except Exception:
        return None


def _session_groups(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        keys = {
            key
            for session in (row.get("sessions") or [])
            if isinstance(session, dict)
            for key in [_market_session_key(session)]
            if key
        }
        for key in keys:
            grouped[key].append(row)
    for key in grouped:
        grouped[key] = sorted(grouped[key], key=lambda x: str(x.get("started_at") or ""))
    return grouped


def _build_market_session(key: str, windows: list[dict[str, Any]]) -> dict[str, Any]:
    window_ids = [str(x.get("window_id")) for x in windows if x.get("window_id")]
    starts = [_parse_time(x.get("started_at")) for x in windows]
    ends = [_parse_time(x.get("last_healthy_at")) for x in windows]
    starts = [x for x in starts if x is not None]
    ends = [x for x in ends if x is not None]
    gaps: list[float] = []
    for left, right in zip(windows, windows[1:]):
        left_end = _parse_time(left.get("last_healthy_at"))
        right_start = _parse_time(right.get("started_at"))
        if left_end is not None and right_start is not None:
            gaps.append(max(0.0, (right_start - left_end).total_seconds()))

    close_reasons = Counter(str(x.get("close_reason") or "UNKNOWN") for x in windows)
    instrument_acc: dict[str, dict[str, Any]] = {}
    for row in windows:
        for session in row.get("sessions") or []:
            if not isinstance(session, dict) or _market_session_key(session) != key:
                continue
            code = str(session.get("base_quote_code") or session.get("session_key") or "UNKNOWN")
            acc = instrument_acc.setdefault(code, {
                "instrument": code,
                "window_count": 0,
                "trade_count_total": 0,
                "volume_total": 0.0,
                "vwap_numerator": 0.0,
                "vwap_weight": 0.0,
                "new_5m_bar_count_total": 0,
                "usable_context_window_count": 0,
                "source_full_session_label_ready_count": 0,
                "last_verified_context": None,
                "last_verified_time": None,
            })
            acc["window_count"] += 1
            acc["trade_count_total"] += _integer(session.get("window_trade_count"))
            volume = _number(session.get("window_total_volume"))
            acc["volume_total"] += volume
            try:
                vwap = float(session.get("window_vwap")) if session.get("window_vwap") is not None else None
            except (TypeError, ValueError):
                vwap = None
            if vwap is not None and volume > 0:
                acc["vwap_numerator"] += vwap * volume
                acc["vwap_weight"] += volume
            acc["new_5m_bar_count_total"] += _integer(session.get("new_5m_bar_count"))
            if session.get("usable_as_context"):
                acc["usable_context_window_count"] += 1
            if session.get("full_session_label_ready"):
                acc["source_full_session_label_ready_count"] += 1

            row_time = _parse_time(row.get("last_healthy_at"))
            prior_time = acc["last_verified_time"]
            if row_time is not None and (prior_time is None or row_time >= prior_time):
                acc["last_verified_time"] = row_time
                acc["last_verified_context"] = session.get("session_context")

    instruments: list[dict[str, Any]] = []
    for code in sorted(instrument_acc):
        acc = instrument_acc[code]
        weight = float(acc["vwap_weight"])
        # Conservative rule: segmented capture cannot be upgraded to a whole-session label.
        full_ready = (
            len(windows) == 1
            and acc["window_count"] == 1
            and acc["source_full_session_label_ready_count"] == 1
        )
        instruments.append({
            "instrument": code,
            "capture_window_count": acc["window_count"],
            "captured_trade_count_total": acc["trade_count_total"],
            "captured_volume_total": acc["volume_total"],
            "captured_volume_weighted_vwap": (
                acc["vwap_numerator"] / weight if weight > 0 else None
            ),
            "captured_new_5m_bar_count_total": acc["new_5m_bar_count_total"],
            "usable_context_window_count": acc["usable_context_window_count"],
            "source_full_session_label_ready_count": acc[
                "source_full_session_label_ready_count"
            ],
            "market_session_full_session_label_ready": full_ready,
            "last_verified_context": acc["last_verified_context"],
        })

    verified_minutes = sum(_number(x.get("observed_minutes")) for x in windows)
    complete_count = sum(
        1 for x in windows if x.get("metrics_complete_from_window_start")
    )
    micro_verified = sum(
        1
        for x in windows
        if isinstance(x.get("microstructure_context"), dict)
        and x["microstructure_context"].get("live_verified")
    )
    dropped = sum(
        _integer((x.get("microstructure_context") or {}).get("dropped_records"))
        for x in windows
        if isinstance(x.get("microstructure_context"), dict)
    )
    persistence_errors = sum(
        1
        for x in windows
        if isinstance(x.get("microstructure_context"), dict)
        and x["microstructure_context"].get("persistence_error")
    )

    return {
        "market_session_key": key,
        "session": key.split("|", 1)[0] if "|" in key else None,
        "session_start_date": key.split("|", 1)[1] if "|" in key else None,
        "window_ids": window_ids,
        "capture_window_count": len(windows),
        "captured_start_at": min(starts).isoformat() if starts else None,
        "captured_last_healthy_at": max(ends).isoformat() if ends else None,
        "verified_capture_minutes_total": verified_minutes,
        "inter_window_gap_seconds": gaps,
        "inter_window_gap_seconds_total": sum(gaps),
        "metrics_complete_from_window_start_count": complete_count,
        "metrics_incomplete_from_window_start_count": len(windows) - complete_count,
        "microstructure_live_verified_window_count": micro_verified,
        "dropped_records_total": dropped,
        "persistence_error_window_count": persistence_errors,
        "close_reason_counts": dict(sorted(close_reasons.items())),
        "segmented_capture": len(windows) > 1,
        "statistical_independence_between_windows_assumed": False,
        "instruments": instruments,
        "research_use": {
            "context_allowed": any(
                item["usable_context_window_count"] > 0 for item in instruments
            ),
            "prediction_performance_evaluated": False,
            "predictive_gain_claim_allowed": False,
            "calibrated_probability_claim_allowed": False,
            "trading_edge_claim_allowed": False,
        },
    }


def build_view(root: Path) -> dict[str, Any]:
    root = Path(root)
    dataset = _load_dataset(root)
    rows = [x for x in (dataset.get("rows") or []) if isinstance(x, dict)]
    rows = sorted(rows, key=lambda x: str(x.get("started_at") or ""))
    groups = _session_groups(rows)
    sessions = [_build_market_session(key, groups[key]) for key in sorted(groups)]
    out = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if sessions else "NO_MARKET_SESSIONS",
        "source_dataset_schema": dataset.get("schema_version"),
        "source_dataset_updated_at": dataset.get("updated_at"),
        "source_rows_sha256": _rows_hash(rows),
        "capture_window_count": len(rows),
        "market_session_count": len(sessions),
        "market_sessions": sessions,
        "policy": {
            "one_row_per_session_and_start_date": True,
            "segmented_capture_never_upgrades_full_session_label": True,
            "window_independence_not_assumed": True,
            "missing_time_backfill_allowed": False,
            "prediction_claims_allowed": False,
        },
    }
    _persist(root, out)
    return out


def _fmt(value: Any, digits: int = 2) -> str:
    if value is None:
        return "無"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    if abs(number - round(number)) < 1e-9:
        return f"{number:,.0f}"
    return f"{number:,.{digits}f}"


def _markdown(out: dict[str, Any]) -> str:
    lines = [
        "# JNU Market Session 研究 View",
        "",
        f"- capture windows：{out.get('capture_window_count')}",
        f"- market sessions：{out.get('market_session_count')}",
        "- 一個 market session 一列；PC 開關切段不增加獨立樣本數。",
    ]
    for session in out.get("market_sessions") or []:
        lines.extend([
            "",
            f"## {session.get('market_session_key')}",
            f"- capture windows：{session.get('capture_window_count')}",
            f"- verified capture minutes：{_fmt(session.get('verified_capture_minutes_total'))}",
            f"- inter-window gap seconds：{_fmt(session.get('inter_window_gap_seconds_total'))}",
            f"- segmented capture：{session.get('segmented_capture')}",
            f"- complete baselines：{session.get('metrics_complete_from_window_start_count')}",
            f"- incomplete baselines：{session.get('metrics_incomplete_from_window_start_count')}",
            f"- dropped records：{session.get('dropped_records_total')}",
            f"- persistence errors：{session.get('persistence_error_window_count')}",
        ])
        for item in session.get("instruments") or []:
            lines.extend([
                f"- {item.get('instrument')} captured trades：{_fmt(item.get('captured_trade_count_total'))}",
                f"- {item.get('instrument')} DealVol：{_fmt(item.get('captured_volume_total'))}",
                f"- {item.get('instrument')} capture VWAP：{_fmt(item.get('captured_volume_weighted_vwap'))}",
                f"- {item.get('instrument')} FULL_SESSION_LABEL_READY：{item.get('market_session_full_session_label_ready')}",
            ])
    lines.extend([
        "",
        "## Claims",
        "- PREDICTIVE_GAIN=false",
        "- CALIBRATED=false",
        "- TRADING_EDGE=false",
        "",
    ])
    return "\n".join(lines)


def _persist(root: Path, out: dict[str, Any]) -> None:
    jp = view_path(root)
    mp = markdown_path(root)
    jp.parent.mkdir(parents=True, exist_ok=True)
    durable_json_replace(jp, out)
    tmp = mp.with_suffix(mp.suffix + ".tmp")
    tmp.write_text(_markdown(out), encoding="utf-8")
    tmp.replace(mp)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--recorder-root", type=Path)
    args = ap.parse_args()
    root = args.recorder_root or Path(recorder_root())
    out = build_view(root)
    print(json.dumps({
        "schema_version": out["schema_version"],
        "status": out["status"],
        "capture_window_count": out["capture_window_count"],
        "market_session_count": out["market_session_count"],
        "source_rows_sha256": out["source_rows_sha256"],
        "view_path": str(view_path(root)),
        "markdown_path": str(markdown_path(root)),
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
