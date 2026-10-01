"""Coverage diagnostics for the pre-registered microstructure night-window features.

Extraction only: no model, no probability, no ranking. Prints one row per recorded night so
missing capture is visible instead of silently absent.

Usage:
  python scripts/microstructure_feature_coverage.py [instrument_code ...]
"""
from __future__ import annotations

import json
import sys

from market_ai_hub.integrations.yuanta.live_quote_recorder import recorder_root
from market_ai_hub.research.v2.microstructure_features import (
    FEATURE_NAMES, PROTOCOL_ID, extract_night_window, list_trading_dates,
)


def main(argv: list[str]) -> int:
    instruments = argv[1:] or ["JNUPM2612", "JNU2612"]
    root = str(recorder_root() / "parquet")
    dates = list_trading_dates(root)
    print(f"protocol={PROTOCOL_ID} store={root}")
    print(f"dates={len(dates)} instruments={instruments}")
    print(f"{'date':<12} {'instrument':<12} {'status':<22} {'n':>7} {'mins':>7}  notes")
    usable = 0
    rows: list[dict] = []
    for d in dates:
        for sym in instruments:
            w = extract_night_window(root, d, sym)
            mins = (w.features.get("window_minutes") or 0.0) if w.features else 0.0
            note = w.reason[:40]
            if w.status == "OK":
                usable += 1
                note = (f"ret={w.features['window_log_return']:.5f} "
                        f"rv={w.features['realized_vol']:.5f} "
                        f"vwap_dev={w.features['vwap_deviation']:.5f} "
                        f"imb={w.features['signed_volume_imbalance']:.3f}")
            print(f"{d:<12} {sym:<12} {w.status:<22} {w.trade_count:>7} {mins:>7.1f}  {note}")
            rows.append(w.model_dump())

    print(f"\nusable windows: {usable} / {len(dates) * len(instruments)}")
    print(f"frozen feature list: {len(FEATURE_NAMES)} -> {', '.join(FEATURE_NAMES)}")
    print("\nHONESTY: DEVELOPMENT_ONLY. This is feature coverage, not signal, not evidence,")
    print("         not a probability and not a trading edge.")
    print("\nJSON:")
    print(json.dumps(rows, ensure_ascii=False, default=str)[:400])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
