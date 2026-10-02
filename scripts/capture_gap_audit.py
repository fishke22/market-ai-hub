"""Capture-gap audit runner: how much recorded time was really lost?

Usage:
  python scripts/capture_gap_audit.py [YYYY-MM-DD ...]
"""
from __future__ import annotations

import sys

from market_ai_hub.integrations.yuanta.live_quote_recorder import recorder_root
from market_ai_hub.research.v2.capture_gap_audit import (
    GAP_REAL_LOSS_STATUSES, audit_capture_gaps, list_capture_days,
)


def main(argv: list[str]) -> int:
    root = str(recorder_root() / "parquet")
    days = argv[1:] or list_capture_days(root)
    if not days:
        print("no recorded days")
        return 1
    print(f"store={root}")
    total_loss = total_expected = 0.0
    for day in days:
        a = audit_capture_gaps(root, day)
        total_loss += a.loss_seconds
        total_expected += a.expected_seconds
        print(f"\n=== {day}  ticks={a.tick_count}  span={a.span_seconds/3600:.2f} h "
              f"loss={a.loss_seconds/3600:.2f} h  expected-absent={a.expected_seconds/3600:.2f} h ===")
        for g in a.gaps:
            mark = "LOSS " if g.classification in GAP_REAL_LOSS_STATUSES else "      "
            print(f"  {mark} {g.seconds/60:8.1f} min  {g.start[11:19]}Z -> {g.end[11:19]}Z"
                  f"  {g.classification:<32} open={','.join(g.open_venues) or '-'}")
    print(f"\nTOTAL real capture loss (venue open + recorder running): {total_loss/3600:.2f} h")
    print(f"TOTAL not-real-loss (closed / recorder off / unclassified): {total_expected/3600:.2f} h")
    print("\nHONESTY: absence of data is not evidence of anything except absence of capture.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
