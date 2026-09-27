"""Collect only legal public Accuracy v2 sources; never touches broker/session ownership."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json

from market_ai_hub.providers.taifex import TaifexProvider
from market_ai_hub.research.accuracy_v2_p3b_taifex import materialize_tmf_settlement_snapshot
from market_ai_hub.research.future_data_acquisition import future_data_readiness
from market_ai_hub.services.jnu_direct import refresh_jnu_direct_data


def _compact_tmf(summary: dict) -> dict:
    return {
        key: value
        for key, value in summary.items()
        if key != "results"
    } | {
        "blocked_reasons": sorted({
            str(row.get("reason"))
            for row in summary.get("results", [])
            if row.get("status") == "BLOCKED" and row.get("reason")
        })
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--taifex-start", default="")
    ap.add_argument("--taifex-end", default="")
    args = ap.parse_args()

    readiness = future_data_readiness()
    if args.dry_run:
        print(json.dumps({
            "status": "DRY_RUN",
            "readiness": readiness,
            "broker_used": False,
            "credentials_used": False,
            "recorder_touched": False,
        }, ensure_ascii=False, sort_keys=True))
        return 0

    now = datetime.now(timezone.utc)
    start = args.taifex_start or (now - timedelta(days=28)).strftime("%Y/%m/%d")
    end = args.taifex_end or now.strftime("%Y/%m/%d")
    result = {
        "schema_version": "AV2PUBLICCOLLECT.1",
        "started_at": now.isoformat(),
        "broker_used": False,
        "credentials_used": False,
        "recorder_touched": False,
        "jpx": refresh_jnu_direct_data(force=True),
    }
    try:
        snap = TaifexProvider().fetch_daily_snapshot("TMF", start=start, end=end)
        result["taifex_tmf"] = _compact_tmf(materialize_tmf_settlement_snapshot(snap))
    except Exception as exc:
        result["taifex_tmf"] = {
            "status": "REFRESH_FAILED",
            "error": type(exc).__name__,
        }
    result["completed_at"] = datetime.now(timezone.utc).isoformat()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, default=str))
    jpx_ok = result["jpx"].get("settlement", {}).get("status") == "OK"
    tmf_counts = result["taifex_tmf"].get("counts", {})
    tmf_ok = result["taifex_tmf"].get("status") != "REFRESH_FAILED" and int(tmf_counts.get("BLOCKED", 0)) == 0
    return 0 if jpx_ok and tmf_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
