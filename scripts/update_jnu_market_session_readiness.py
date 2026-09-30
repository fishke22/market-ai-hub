"""Readiness gate for accumulating distinct JNU market sessions."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from market_ai_hub.integrations.yuanta.durable_spool import durable_json_replace
from market_ai_hub.integrations.yuanta.live_quote_recorder import recorder_root

SCHEMA_VERSION = "AV2.JNU.MARKET_SESSION_READINESS.1"
MIN_DISTINCT_SESSIONS_FOR_DESCRIPTIVE_PAIRING = 2


def view_path(root: Path) -> Path:
    return Path(root) / "research" / "jnu_market_session_view.json"


def readiness_path(root: Path) -> Path:
    return Path(root) / "research" / "jnu_market_session_readiness.json"


def markdown_path(root: Path) -> Path:
    return Path(root) / "research" / "jnu_market_session_readiness_zh_tw.md"


def _load_view(root: Path) -> dict[str, Any]:
    path = view_path(root)
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return raw if isinstance(raw, dict) else {}


def build_readiness(root: Path) -> dict[str, Any]:
    root = Path(root)
    view = _load_view(root)
    sessions = [x for x in (view.get("market_sessions") or []) if isinstance(x, dict)]
    eligible = [
        x for x in sessions
        if isinstance(x.get("research_use"), dict)
        and x["research_use"].get("context_allowed") is True
    ]
    eligible_keys = [
        str(x.get("market_session_key"))
        for x in eligible
        if x.get("market_session_key")
    ]
    eligible_count = len(set(eligible_keys))
    needed = max(0, MIN_DISTINCT_SESSIONS_FOR_DESCRIPTIVE_PAIRING - eligible_count)
    descriptive_ready = eligible_count >= MIN_DISTINCT_SESSIONS_FOR_DESCRIPTIVE_PAIRING

    if not sessions:
        status = "NO_MARKET_SESSIONS"
        blocker = "NO_DISTINCT_MARKET_SESSION_ROWS"
    elif not descriptive_ready:
        status = "ACCUMULATING_MARKET_SESSIONS"
        blocker = "NEED_AT_LEAST_2_DISTINCT_MARKET_SESSIONS_FOR_CROSS_SESSION_PAIR"
    else:
        status = "DESCRIPTIVE_PAIRING_READY_ONLY"
        blocker = "MODEL_EVALUATION_STILL_REQUIRES_PREDECLARED_CHRONOLOGICAL_PROTOCOL"

    out = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "source_view_schema": view.get("schema_version"),
        "source_view_generated_at": view.get("generated_at"),
        "source_rows_sha256": view.get("source_rows_sha256"),
        "market_session_count": len(sessions),
        "eligible_market_session_count": eligible_count,
        "eligible_market_session_keys": sorted(set(eligible_keys)),
        "minimum_distinct_sessions_for_descriptive_pairing": (
            MIN_DISTINCT_SESSIONS_FOR_DESCRIPTIVE_PAIRING
        ),
        "sessions_needed_for_descriptive_pairing": needed,
        "cross_session_descriptive_pairing_ready": descriptive_ready,
        "chronological_model_selection_ready": False,
        "predictive_performance_evaluation_ready": False,
        "blocker": blocker,
        "policy": {
            "capture_window_count_never_substitutes_for_market_session_count": True,
            "two_sessions_only_unlocks_descriptive_pairing": True,
            "model_selection_requires_separate_predeclared_chronological_protocol": True,
            "predictive_gain_claim_allowed": False,
            "calibrated_probability_claim_allowed": False,
            "trading_edge_claim_allowed": False,
        },
    }
    _persist(root, out)
    return out


def _markdown(out: dict[str, Any]) -> str:
    return "\n".join([
        "# JNU Market Session 累積 Readiness",
        "",
        f"- 狀態：{out.get('status')}",
        f"- market-session rows：{out.get('market_session_count')}",
        f"- eligible distinct sessions：{out.get('eligible_market_session_count')}",
        f"- 描述性 cross-session pairing 最低需求：{out.get('minimum_distinct_sessions_for_descriptive_pairing')}",
        f"- 尚需 sessions：{out.get('sessions_needed_for_descriptive_pairing')}",
        f"- cross-session descriptive pairing ready：{out.get('cross_session_descriptive_pairing_ready')}",
        f"- blocker：{out.get('blocker')}",
        "",
        "注意：達到 2 個 session 只代表可以建立跨-session描述性配對表，",
        "不代表可以做模型挑選、宣稱預測增益、校準機率或 trading edge。",
        "",
        "- PREDICTIVE_GAIN=false",
        "- CALIBRATED=false",
        "- TRADING_EDGE=false",
        "",
    ])


def _persist(root: Path, out: dict[str, Any]) -> None:
    jp = readiness_path(root)
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
    out = build_readiness(root)
    print(json.dumps({
        "schema_version": out["schema_version"],
        "status": out["status"],
        "eligible_market_session_count": out["eligible_market_session_count"],
        "sessions_needed_for_descriptive_pairing": out[
            "sessions_needed_for_descriptive_pairing"
        ],
        "cross_session_descriptive_pairing_ready": out[
            "cross_session_descriptive_pairing_ready"
        ],
        "readiness_path": str(readiness_path(root)),
    }, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
