"""Fetch and materialize official TAIFEX TMF settlements for future-safe research."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json

from market_ai_hub.providers.taifex import TaifexProvider
from market_ai_hub.research.accuracy_v2_p3b_taifex import (
    materialize_tmf_settlement_snapshot,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="")
    parser.add_argument("--end", default="")
    args = parser.parse_args()

    now = datetime.now(timezone.utc)
    start = args.start or (now - timedelta(days=28)).strftime("%Y/%m/%d")
    end = args.end or now.strftime("%Y/%m/%d")
    snapshot = TaifexProvider().fetch_daily_snapshot("TMF", start=start, end=end)
    summary = materialize_tmf_settlement_snapshot(snapshot)
    blocked_reasons = sorted({
        str(row.get("reason"))
        for row in summary.get("results", [])
        if row.get("status") == "BLOCKED" and row.get("reason")
    })
    compact = {
        key: value
        for key, value in summary.items()
        if key != "results"
    }
    compact["blocked_reasons"] = blocked_reasons
    print(json.dumps(compact, ensure_ascii=False, sort_keys=True, default=str))
    blocked = int(summary.get("counts", {}).get("BLOCKED", 0))
    return 0 if blocked == 0 else 2


if __name__ == "__main__":
    raise SystemExit(main())
