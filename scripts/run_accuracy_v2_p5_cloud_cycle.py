"""Public-source-only cloud operator for Accuracy v2 P5."""
from __future__ import annotations

import argparse
from datetime import datetime, time, timedelta
import json
from pathlib import Path
import time as time_module
from zoneinfo import ZoneInfo

from market_ai_hub.config.runtime_paths import data_root
from market_ai_hub.research.accuracy_v2_p5_engine import (
    p5_forward_evidence_summary,
    preview_p5_origin,
    run_p5_cycle,
)
from market_ai_hub.research.v2 import prediction_audit as PA
from market_ai_hub.services.build_info import build_fingerprint
from market_ai_hub.services.data_continuity import jnu_data_continuity_status
from market_ai_hub.targets.jpx_daily import JPXOSEDailyReportProvider, public_daily_report_months
from market_ai_hub.targets.jpx_settlement import JPXSettlementProvider

SCHEMA_VERSION = "AV2P5CLOUD.1"
TAIPEI = ZoneInfo("Asia/Taipei")
PREWARM_TIME = time(8, 1, 0)
CANONICAL_RUN_TIME = time(8, 5, 5)
MAX_PREWARM_WAIT_SECONDS = 30 * 60
BENIGN_PRECOMMIT = {
    "PRECOMMITTED", "ALREADY_PRECOMMITTED", "WAITING_FOR_ORIGIN",
    "BEFORE_FIRST_ELIGIBLE_ORIGIN", "MISSED_CANONICAL_ORIGIN",
    "ABSTAIN", "DATA_NOT_READY",
}


def sync_jpx_public(month_count: int, lookback_days: int) -> dict:
    """Rebuild the public JPX input window on an ephemeral cloud runner."""
    provider = JPXSettlementProvider()
    today = datetime.now(ZoneInfo("Asia/Tokyo")).date()
    errors: list[str] = []
    settlement: dict = {"status": "NO_RECENT_SETTLEMENT", "errors": errors}
    for i in range(max(int(lookback_days), 1)):
        date_text = (today - timedelta(days=i)).strftime("%Y%m%d")
        try:
            rows = provider.fetch_parse(date_text)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{date_text}:{type(exc).__name__}")
            continue
        micro = [row for row in rows if row.product == "Nikkei 225 Micro Futures"]
        if not micro:
            continue
        path = provider.save(date_text, rows)
        settlement = {
            "status": "OK",
            "trade_date": date_text,
            "micro_contracts": len(micro),
            "saved": str(path),
            "errors_before_success": errors,
        }
        break

    months = public_daily_report_months()
    selected = months[-max(int(month_count), 1):]
    archive = (
        JPXOSEDailyReportProvider().sync_public_months(selected, skip_existing=True)
        if selected else {"status": "NO_PUBLIC_MONTH"}
    )
    return {
        "schema": "JPX_MICRO_DIRECT_SYNC_V1",
        "settlement": settlement,
        "archive": archive,
        "broker_used": False,
        "credentials_used": False,
    }


def _now_taipei() -> datetime:
    return datetime.now(TAIPEI)


def _seconds_until_today(target: time, *, now: datetime | None = None) -> float:
    current = (now or _now_taipei()).astimezone(TAIPEI)
    target_dt = datetime.combine(current.date(), target, tzinfo=TAIPEI)
    return max(0.0, (target_dt - current).total_seconds())


def _bounded_wait(target: time) -> float:
    seconds = _seconds_until_today(target)
    if seconds <= 0:
        return 0.0
    if seconds > MAX_PREWARM_WAIT_SECONDS:
        raise RuntimeError("P5_CLOUD_INVOCATION_TOO_EARLY")
    time_module.sleep(seconds)
    return seconds


def _write_summary(payload: dict) -> Path:
    root = data_root()
    cloud_dir = root / "cloud"
    cloud_dir.mkdir(parents=True, exist_ok=True)
    summary_path = cloud_dir / "p5_cloud_run_summary.json"
    manifest_path = cloud_dir / "p5_cloud_state_manifest.json"
    summary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8",
    )
    audit_path = PA.default_audit_db_path()
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "generated_at": datetime.now(TAIPEI).isoformat(),
        "state_valid": True,
        "audit_db_present": audit_path.is_file(),
        "p5_state_present": (root / "automation" / "p5_forward_state.json").is_file(),
        "public_sources_only": True,
        "broker_used": False,
        "credentials_used": False,
        "recorder_touched": False,
        "order_action": False,
        "build_id": build_fingerprint()["build_id"],
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return summary_path


def run_smoke(*, months: int, lookback_days: int) -> dict:
    PA.PredictionAuditDB()
    sync = sync_jpx_public(months, lookback_days)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "mode": "smoke",
        "generated_at": datetime.now(TAIPEI).isoformat(),
        "sync": sync,
        "preview": preview_p5_origin(),
        "evidence": p5_forward_evidence_summary(),
        "data_continuity": jnu_data_continuity_status(),
        "writes_prediction": False,
        "public_sources_only": True,
        "broker_used": False,
        "credentials_used": False,
        "recorder_touched": False,
        "order_action": False,
    }
    _write_summary(payload)
    return payload


def run_scheduled(*, months: int, lookback_days: int) -> dict:
    waited_for_publication = _bounded_wait(PREWARM_TIME)
    sync = sync_jpx_public(months, lookback_days)
    waited_for_origin = _bounded_wait(CANONICAL_RUN_TIME)
    cycle = run_p5_cycle()
    payload = {
        "schema_version": SCHEMA_VERSION,
        "mode": "scheduled",
        "generated_at": datetime.now(TAIPEI).isoformat(),
        "waited_for_publication_seconds": waited_for_publication,
        "waited_for_origin_seconds": waited_for_origin,
        "sync": sync,
        "cycle": cycle,
        "public_sources_only": True,
        "broker_used": False,
        "credentials_used": False,
        "recorder_touched": False,
        "order_action": False,
    }
    _write_summary(payload)
    return payload


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=("smoke", "scheduled"), default="smoke")
    ap.add_argument("--months", type=int, default=3)
    ap.add_argument("--settlement-lookback-days", type=int, default=10)
    args = ap.parse_args()
    if args.months < 3:
        raise SystemExit("P5 cloud bootstrap requires at least 3 public archive months")
    result = (
        run_smoke(months=args.months, lookback_days=args.settlement_lookback_days)
        if args.mode == "smoke"
        else run_scheduled(months=args.months, lookback_days=args.settlement_lookback_days)
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, default=str))
    if args.mode == "smoke":
        return 0
    status = str((result.get("cycle", {}).get("precommit") or {}).get("status") or "")
    return 0 if status in BENIGN_PRECOMMIT else 2


if __name__ == "__main__":
    raise SystemExit(main())
