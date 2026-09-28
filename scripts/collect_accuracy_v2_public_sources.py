"""Collect only legal public Accuracy v2 sources; never touches broker/session ownership."""
from __future__ import annotations

import argparse
import json

from market_ai_hub.research.future_data_acquisition import (
    collect_public_sources,
    future_data_readiness,
)


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

    result = collect_public_sources(
        taifex_start=args.taifex_start,
        taifex_end=args.taifex_end,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, default=str))
    jpx_ok = result["jpx"].get("settlement", {}).get("status") == "OK"
    tmf_counts = result["taifex_tmf"].get("counts", {})
    tmf_ok = result["taifex_tmf"].get("status") != "REFRESH_FAILED" and int(tmf_counts.get("BLOCKED", 0)) == 0
    return 0 if jpx_ok and tmf_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
