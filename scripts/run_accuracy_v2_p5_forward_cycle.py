"""Operate Accuracy v2 P5 from public sources only."""
from __future__ import annotations

import argparse
import json

from market_ai_hub.services.data_continuity import jnu_data_continuity_status

from market_ai_hub.research.accuracy_v2_p5_engine import (
    p5_forward_evidence_summary,
    preview_p5_origin,
    run_p5_cycle,
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if args.dry_run:
        result = {
            "status": "DRY_RUN",
            "preview": preview_p5_origin(),
            "evidence": p5_forward_evidence_summary(),
            "data_continuity": jnu_data_continuity_status(),
            "broker_used": False,
            "credentials_used": False,
            "recorder_touched": False,
            "order_action": False,
            "writes_prediction": False,
        }
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, default=str))
        return 0
    result = run_p5_cycle()
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, default=str))
    status = str((result.get("precommit") or {}).get("status") or "")
    benign = {
        "PRECOMMITTED", "ALREADY_PRECOMMITTED", "WAITING_FOR_ORIGIN",
        "BEFORE_FIRST_ELIGIBLE_ORIGIN", "MISSED_CANONICAL_ORIGIN",
        "ABSTAIN", "DATA_NOT_READY",
    }
    return 0 if status in benign else 2


if __name__ == "__main__":
    raise SystemExit(main())
