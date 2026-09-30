"""Human-readable zero-cost JNU live capture brief."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from market_ai_hub.integrations.yuanta.durable_spool import durable_json_replace
from market_ai_hub.integrations.yuanta.live_quote_recorder import recorder_root

SCHEMA_VERSION = "AV2.JNU.LIVE_CAPTURE_BRIEF.1"
TAIPEI = ZoneInfo("Asia/Taipei")


def json_path(root: Path) -> Path:
    return Path(root) / "research" / "jnu_live_capture_brief.json"


def markdown_path(root: Path) -> Path:
    return Path(root) / "research" / "jnu_live_capture_brief_zh_tw.md"


def _load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def _local_stamp(value: Any) -> str | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value)).astimezone(TAIPEI)
        return dt.isoformat()
    except Exception:
        return str(value)


def _label_reason_zh(reason: str) -> str:
    mapping = {
        "OFFICIAL_OPEN_BOUNDARY_NOT_OBSERVED": "未觀察到官方開盤邊界",
        "OFFICIAL_CLOSE_BOUNDARY_NOT_OBSERVED": "未觀察到官方收盤邊界",
    }
    return mapping.get(reason, reason)


def build_brief(root: Path) -> dict[str, Any]:
    root = Path(root)
    summary = _load(root / "research" / "jnu_capture_window_summary.json")
    window = summary.get("latest_window")
    window = window if isinstance(window, dict) else None
    generated = datetime.now(timezone.utc).isoformat()

    if window is None:
        out = {
            "schema_version": SCHEMA_VERSION,
            "generated_at": generated,
            "status": "NO_VERIFIED_CAPTURE_WINDOW",
            "headline_zh_tw": "目前尚無 verified JNU capture window。",
            "next_action": "WAIT_FOR_PC_AND_HEALTHY_RECORDER",
            "authorization_required": False,
            "claims": {
                "predictive_gain": False,
                "calibrated_probability": False,
                "trading_edge": False,
                "order_action": False,
            },
        }
        _persist(root, out)
        return out

    sessions: list[dict[str, Any]] = []
    for row in window.get("sessions") or []:
        if not isinstance(row, dict):
            continue
        context = row.get("session_context")
        context = context if isinstance(context, dict) else {}
        reasons = [_label_reason_zh(str(x)) for x in (row.get("label_block_reasons") or [])]
        sessions.append({
            "instrument": row.get("base_quote_code"),
            "session": row.get("session"),
            "session_start_date": row.get("session_start_date"),
            "window_trade_count": row.get("window_trade_count"),
            "window_total_volume": row.get("window_total_volume"),
            "window_vwap": row.get("window_vwap"),
            "new_5m_bar_count": row.get("new_5m_bar_count"),
            "session_latest_price": context.get("latest_price"),
            "session_observed_high": context.get("observed_high"),
            "session_observed_low": context.get("observed_low"),
            "session_vwap": context.get("session_vwap"),
            "profile_context_available": bool(
                row.get("session_price_volume_profile_available")
                or row.get("session_price_trade_profile_available")
            ),
            "profile_semantics": row.get("profile_semantics"),
            "usable_as_context": bool(row.get("usable_as_context")),
            "full_session_label_ready": bool(row.get("full_session_label_ready")),
            "label_block_reasons_zh_tw": reasons,
        })

    active = str(window.get("status") or "") == "ACTIVE"
    metrics_complete = bool(window.get("metrics_complete_from_window_start"))
    micro = window.get("microstructure_context")
    micro = micro if isinstance(micro, dict) else {}
    usable_sessions = [x for x in sessions if x["usable_as_context"]]

    can_do = [
        "保留並累積實際開機期間的 JNU StockTick / 5 分鐘結構",
        "使用 capture-window 差分成交筆數、DealVol 與 window VWAP",
        "使用 session 累積價格/成交量 profile 作 context（不冒充 window-specific profile）",
    ]
    if bool(micro.get("live_verified")):
        can_do.append("使用目前已驗證的 microstructure callback 健康狀態作資料品質判斷")
    cannot_do = [
        "缺失時間不得回填成真實行情",
        "未觀察到完整 open+close 時不得標成 FULL_SESSION_LABEL_READY",
        "目前不得宣稱 predictive gain、校準機率或 trading edge",
        "不得由此產生個人化進出場價、部位或下單動作",
    ]

    headline = (
        "JNU 正在錄製；目前資料可作 partial-window/context 研究。"
        if active
        else "JNU 這段 capture window 已結束；資料已保留作研究/context。"
    )
    out = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated,
        "status": "ACTIVE_CAPTURE" if active else "CLOSED_CAPTURE",
        "headline_zh_tw": headline,
        "capture_window": {
            "started_at_taipei": _local_stamp(window.get("started_at")),
            "last_healthy_at_taipei": _local_stamp(window.get("last_healthy_at")),
            "closed_at_taipei": _local_stamp(window.get("closed_at")),
            "observed_minutes": window.get("observed_minutes"),
            "metrics_baseline_at_taipei": _local_stamp(window.get("metrics_baseline_at")),
            "metrics_complete_from_window_start": metrics_complete,
            "metrics_note_zh_tw": (
                "差分基準從 verified window 開始，這段 window 的差分統計完整。"
                if metrics_complete
                else "差分基準在 window 已開始後才上線；基準前的資料不倒算、不補造。"
            ),
        },
        "data_health": {
            "microstructure_live_verified": bool(micro.get("live_verified")),
            "callbacks": micro.get("callbacks") or {},
            "dropped_records": micro.get("dropped_records"),
            "persistence_error": micro.get("persistence_error"),
            "connection_event_state": micro.get("connection_event_state"),
        },
        "sessions": sessions,
        "usable_session_count": len(usable_sessions),
        "can_do_now_zh_tw": can_do,
        "cannot_claim_or_do_zh_tw": cannot_do,
        "next_action": "CONTINUE_CAPTURE_WHILE_PC_ON" if active else "WAIT_FOR_NEXT_PC_ON_WINDOW",
        "authorization_required": False,
        "claims": {
            "predictive_gain": False,
            "calibrated_probability": False,
            "trading_edge": False,
            "order_action": False,
        },
    }
    _persist(root, out)
    return out


def _fmt_num(value: Any, digits: int = 2) -> str:
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
        "# JNU Live Capture Brief",
        "",
        f"- 狀態：{out.get('headline_zh_tw')}",
        f"- 產生時間：{_local_stamp(out.get('generated_at'))}",
    ]
    window = out.get("capture_window") or {}
    if window:
        lines.extend([
            f"- verified window：{window.get('started_at_taipei')} → {window.get('last_healthy_at_taipei')}",
            f"- 已觀察分鐘：約 {_fmt_num(window.get('observed_minutes'))}",
            f"- 差分基準：{window.get('metrics_baseline_at_taipei')}",
            f"- 基準說明：{window.get('metrics_note_zh_tw')}",
        ])

    health = out.get("data_health") or {}
    if health:
        lines.extend([
            "",
            "## 資料健康",
            f"- microstructure live verified：{health.get('microstructure_live_verified')}",
            f"- dropped records：{health.get('dropped_records')}",
            f"- persistence error：{health.get('persistence_error')}",
            f"- connection：{health.get('connection_event_state')}",
        ])

    for session in out.get("sessions") or []:
        lines.extend([
            "",
            f"## {session.get('instrument')} {session.get('session')}",
            f"- 這個 capture window 新增 trades：{_fmt_num(session.get('window_trade_count'))}",
            f"- 這個 capture window 新增 DealVol：{_fmt_num(session.get('window_total_volume'))}",
            f"- window VWAP：{_fmt_num(session.get('window_vwap'))}",
            f"- session 最新價：{_fmt_num(session.get('session_latest_price'))}",
            f"- session observed range：{_fmt_num(session.get('session_observed_low'))}–{_fmt_num(session.get('session_observed_high'))}",
            f"- session VWAP：{_fmt_num(session.get('session_vwap'))}",
            f"- context 可用：{session.get('usable_as_context')}",
            f"- FULL_SESSION_LABEL_READY：{session.get('full_session_label_ready')}",
        ])
        reasons = session.get("label_block_reasons_zh_tw") or []
        if reasons:
            lines.append("- 尚未 full-session label-ready 原因：" + "；".join(str(x) for x in reasons))

    lines.extend(["", "## 現在可以做"])
    lines.extend(f"- {x}" for x in out.get("can_do_now_zh_tw") or [])
    lines.extend(["", "## 現在不能宣稱／不能做"])
    lines.extend(f"- {x}" for x in out.get("cannot_claim_or_do_zh_tw") or [])
    lines.extend([
        "",
        f"- 下一步：{out.get('next_action')}",
        f"- 是否需要新授權：{out.get('authorization_required')}",
        "",
    ])
    return "\n".join(lines)


def _persist(root: Path, out: dict[str, Any]) -> None:
    jp = json_path(root)
    mp = markdown_path(root)
    jp.parent.mkdir(parents=True, exist_ok=True)
    durable_json_replace(jp, out)
    text = _markdown(out)
    tmp = mp.with_suffix(mp.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(mp)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--recorder-root", type=Path)
    args = ap.parse_args()
    root = args.recorder_root or Path(recorder_root())
    out = build_brief(root)
    print(json.dumps({
        "schema_version": out["schema_version"],
        "status": out["status"],
        "headline_zh_tw": out["headline_zh_tw"],
        "json_path": str(json_path(root)),
        "markdown_path": str(markdown_path(root)),
        "authorization_required": out["authorization_required"],
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
