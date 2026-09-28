"""Collect or inspect immutable Taiwan target-context forward receipts."""
from __future__ import annotations

import argparse
import json

from market_ai_hub.research.taiwan_context_forward import (
    collect_taiwan_context_forward_receipt,
    load_taiwan_context_forward_protocol,
    summarize_taiwan_context_receipts,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbol", default="3706.TW")
    parser.add_argument("--inventory-only", action="store_true")
    parser.add_argument("--decision-time", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    protocol = load_taiwan_context_forward_protocol()
    if args.dry_run or args.inventory_only:
        inventory = summarize_taiwan_context_receipts(
            args.symbol,
            decision_time=args.decision_time,
            protocol=protocol,
        )
        result = {
            "status": "DRY_RUN" if args.dry_run else "INVENTORY_ONLY",
            "protocol_id": protocol.protocol_id,
            "protocol_hash": protocol.hash,
            "inventory": inventory,
            "writes_receipt": False,
            "broker_used": False,
            "account_accessed": False,
            "recorder_touched": False,
            "runtime_handover": False,
            "scheduler_installed": False,
            "order_action": False,
        }
    else:
        result = collect_taiwan_context_forward_receipt(args.symbol)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True, default=str))
    status = str((result.get("inventory") or {}).get("status") or "")
    return 0 if not status.startswith("BLOCKED_") else 2


if __name__ == "__main__":
    raise SystemExit(main())
