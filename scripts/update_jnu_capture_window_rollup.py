"""Cross-window quality rollup for immutable JNU capture-window rows."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from statistics import mean, median
from typing import Any

from market_ai_hub.integrations.yuanta.durable_spool import durable_json_replace
from market_ai_hub.integrations.yuanta.live_quote_recorder import recorder_root

SCHEMA_VERSION = "AV2.JNU.CAPTURE_WINDOW_ROLLUP.1"


def rollup_path(root: Path) -> Path:
    return Path(root) / "research" / "jnu_capture_window_rollup.json"


def markdown_path(root: Path) -> Path:
    return Path(root) / "research" / "jnu_capture_window_rollup_zh_tw.md"


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


def _rows_hash(rows: list[dict[str, Any]]) -> str:
    payload = json.dumps(rows, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _market_session_key(session: dict[str, Any]) -> str | None:
    session_name = session.get("session")
    start_date = session.get("session_start_date")
    if not session_name or not start_date:
        return None
    return f"{session_name}|{start_date}"


def _time_key(row: dict[str, Any]) -> str:
    return str(row.get("started_at") or "")


def _duration_stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {
            "count": 0,
            "total": 0.0,
            "mean": None,
            "median": None,
            "min": None,
            "max": None,
        }
    return {
        "count": len(values),
        "total": sum(values),
        "mean": mean(values),
        "median": median(values),
        "min": min(values),
        "max": max(values),
    }


def build_rollup(root: Path) -> dict[str, Any]:
    root = Path(root)
    dataset = _load_dataset(root)
    rows = [row for row in (dataset.get("rows") or []) if isinstance(row, dict)]
    rows = sorted(rows, key=_time_key)
    generated_at = datetime.now(timezone.utc).isoformat()

    market_session_windows: dict[str, set[str]] = defaultdict(set)
    close_reasons: Counter[str] = Counter()
    observed_minutes: list[float] = []
    instruments: dict[str, dict[str, Any]] = {}
    micro_verified_count = 0
    dropped_records_total = 0
    persistence_error_window_count = 0
    broker_order_action_window_count = 0
    complete_baseline_count = 0
    any_full_label_window_count = 0
    all_full_label_window_count = 0

    for row in rows:
        window_id = str(row.get("window_id") or "")
        reason = str(row.get("close_reason") or "UNKNOWN")
        close_reasons[reason] += 1
        if row.get("metrics_complete_from_window_start"):
            complete_baseline_count += 1
        if row.get("broker_order_action"):
            broker_order_action_window_count += 1

        runtime = row.get("microstructure_context")
        runtime = runtime if isinstance(runtime, dict) else {}
        if runtime.get("live_verified"):
            micro_verified_count += 1
        dropped_records_total += _integer(runtime.get("dropped_records"))
        if runtime.get("persistence_error"):
            persistence_error_window_count += 1

        minutes = row.get("observed_minutes")
        try:
            if minutes is not None:
                observed_minutes.append(float(minutes))
        except (TypeError, ValueError):
            pass

        row_sessions = [x for x in (row.get("sessions") or []) if isinstance(x, dict)]
        full_flags = [bool(x.get("full_session_label_ready")) for x in row_sessions]
        if any(full_flags):
            any_full_label_window_count += 1
        if full_flags and all(full_flags):
            all_full_label_window_count += 1

        for session in row_sessions:
            market_key = _market_session_key(session)
            if market_key and window_id:
                market_session_windows[market_key].add(window_id)

            code = str(session.get("base_quote_code") or session.get("session_key") or "UNKNOWN")
            acc = instruments.setdefault(code, {
                "instrument": code,
                "window_ids": [],
                "market_session_keys": set(),
                "window_trade_count_total": 0,
                "window_total_volume": 0.0,
                "window_vwap_weighted_numerator": 0.0,
                "window_vwap_weight": 0.0,
                "window_vwaps": [],
                "new_5m_bar_count_total": 0,
                "usable_context_window_count": 0,
                "full_session_label_ready_window_count": 0,
            })
            if window_id:
                acc["window_ids"].append(window_id)
            if market_key:
                acc["market_session_keys"].add(market_key)
            trades = _integer(session.get("window_trade_count"))
            volume = _number(session.get("window_total_volume"))
            vwap_raw = session.get("window_vwap")
            vwap = None
            try:
                if vwap_raw is not None:
                    vwap = float(vwap_raw)
            except (TypeError, ValueError):
                vwap = None
            acc["window_trade_count_total"] += trades
            acc["window_total_volume"] += volume
            acc["new_5m_bar_count_total"] += _integer(session.get("new_5m_bar_count"))
            if session.get("usable_as_context"):
                acc["usable_context_window_count"] += 1
            if session.get("full_session_label_ready"):
                acc["full_session_label_ready_window_count"] += 1
            if vwap is not None:
                acc["window_vwaps"].append(vwap)
                if volume > 0:
                    acc["window_vwap_weighted_numerator"] += vwap * volume
                    acc["window_vwap_weight"] += volume

    instrument_rows: list[dict[str, Any]] = []
    for code in sorted(instruments):
        acc = instruments[code]
        vwaps = list(acc["window_vwaps"])
        weight = float(acc["window_vwap_weight"])
        instrument_rows.append({
            "instrument": code,
            "window_count": len(acc["window_ids"]),
            "market_session_count": len(acc["market_session_keys"]),
            "window_trade_count_total": acc["window_trade_count_total"],
            "window_total_volume": acc["window_total_volume"],
            "capture_volume_weighted_vwap": (
                acc["window_vwap_weighted_numerator"] / weight if weight > 0 else None
            ),
            "window_vwap_min": min(vwaps) if vwaps else None,
            "window_vwap_max": max(vwaps) if vwaps else None,
            "new_5m_bar_count_total": acc["new_5m_bar_count_total"],
            "usable_context_window_count": acc["usable_context_window_count"],
            "full_session_label_ready_window_count": acc["full_session_label_ready_window_count"],
            "statistical_independence_assumed": False,
        })

    market_sessions = [
        {
            "market_session_key": key,
            "window_count": len(window_ids),
            "window_ids": sorted(window_ids),
        }
        for key, window_ids in sorted(market_session_windows.items())
    ]
    multiwindow_sessions = [x for x in market_sessions if x["window_count"] > 1]

    status = "PASS" if rows else "NO_CLOSED_WINDOWS"
    out = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at,
        "status": status,
        "source_dataset_schema": dataset.get("schema_version"),
        "source_dataset_updated_at": dataset.get("updated_at"),
        "source_rows_sha256": _rows_hash(rows),
        "window_count": len(rows),
        "unique_market_session_count": len(market_sessions),
        "market_sessions_with_multiple_windows_count": len(multiwindow_sessions),
        "market_sessions": market_sessions,
        "quality": {
            "closed_window_count": len(rows),
            "all_rows_closed": all(row.get("status") == "CLOSED" for row in rows),
            "metrics_complete_from_window_start_count": complete_baseline_count,
            "metrics_incomplete_from_window_start_count": len(rows) - complete_baseline_count,
            "microstructure_live_verified_window_count": micro_verified_count,
            "dropped_records_total": dropped_records_total,
            "persistence_error_window_count": persistence_error_window_count,
            "broker_order_action_window_count": broker_order_action_window_count,
            "windows_with_any_full_session_label_ready": any_full_label_window_count,
            "windows_all_sessions_full_session_label_ready": all_full_label_window_count,
            "observed_minutes": _duration_stats(observed_minutes),
            "close_reason_counts": dict(sorted(close_reasons.items())),
        },
        "instruments": instrument_rows,
        "research_interpretation": {
            "window_count_is_not_independent_sample_count": True,
            "market_session_groups_are_primary_overlap_guard": True,
            "same_market_session_multiwindow_detected": bool(multiwindow_sessions),
            "prediction_performance_evaluated": False,
            "predictive_gain_claim_allowed": False,
            "calibrated_probability_claim_allowed": False,
            "trading_edge_claim_allowed": False,
            "full_session_label_claim_requires_row_level_ready": True,
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
    q = out.get("quality") or {}
    d = q.get("observed_minutes") or {}
    lines = [
        "# JNU Capture Window 跨視窗品質摘要",
        "",
        f"- 狀態：{out.get('status')}",
        f"- CLOSED windows：{out.get('window_count')}",
        f"- unique market sessions：{out.get('unique_market_session_count')}",
        f"- 同一 market session 被切成多個 windows 的 session 數：{out.get('market_sessions_with_multiple_windows_count')}",
        f"- verified capture 總分鐘：{_fmt(d.get('total'))}",
        f"- 從 window start 完整計量：{q.get('metrics_complete_from_window_start_count')}",
        f"- baseline 中途採用：{q.get('metrics_incomplete_from_window_start_count')}",
        f"- microstructure verified windows：{q.get('microstructure_live_verified_window_count')}",
        f"- dropped records 合計：{q.get('dropped_records_total')}",
        f"- persistence error windows：{q.get('persistence_error_window_count')}",
        f"- broker order action windows：{q.get('broker_order_action_window_count')}",
        "",
        "## 樣本解讀",
        "- window_count 不等於獨立市場樣本數；同一 NIGHT/DAY + session_start_date 會合併成一個 market-session group。",
        "- 本摘要只量資料品質與擷取覆蓋，不評估方向準確率、校準機率或 trading edge。",
    ]
    for item in out.get("market_sessions") or []:
        lines.append(
            f"- {item.get('market_session_key')}：{item.get('window_count')} 個 windows"
        )
    for item in out.get("instruments") or []:
        lines.extend([
            "",
            f"## {item.get('instrument')}",
            f"- windows：{item.get('window_count')}；market sessions：{item.get('market_session_count')}",
            f"- capture trades 合計：{_fmt(item.get('window_trade_count_total'))}",
            f"- capture DealVol 合計：{_fmt(item.get('window_total_volume'))}",
            f"- capture volume-weighted VWAP：{_fmt(item.get('capture_volume_weighted_vwap'))}",
            f"- 5m bars 新增合計：{_fmt(item.get('new_5m_bar_count_total'))}",
            f"- context 可用 windows：{item.get('usable_context_window_count')}",
            f"- FULL_SESSION_LABEL_READY windows：{item.get('full_session_label_ready_window_count')}",
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
    jp = rollup_path(root)
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
    out = build_rollup(root)
    print(json.dumps({
        "schema_version": out["schema_version"],
        "status": out["status"],
        "window_count": out["window_count"],
        "unique_market_session_count": out["unique_market_session_count"],
        "market_sessions_with_multiple_windows_count": out[
            "market_sessions_with_multiple_windows_count"
        ],
        "source_rows_sha256": out["source_rows_sha256"],
        "rollup_path": str(rollup_path(root)),
        "markdown_path": str(markdown_path(root)),
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
