"""Export a frozen P2 development dataset for the isolated Qlib adapter boundary.

This script does not import, install, or execute Qlib.
"""
from __future__ import annotations

import argparse
import json

import pandas as pd

from market_ai_hub.automation.data_lake import default_data_root
from market_ai_hub.integrations.open_source_research import export_isolated_research_dataset
from market_ai_hub.research.accuracy_v2_p2 import load_p2_protocol
from market_ai_hub.research.accuracy_v2_p2_engine import build_p2_samples, source_fingerprint


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--destination", default="")
    args = ap.parse_args()

    p2 = load_p2_protocol()
    samples = [s for s in build_p2_samples() if s.partition == "DEVELOPMENT"]
    if not samples:
        print(json.dumps({"status": "DATA_NOT_READY", "development_origins": 0}))
        return 2

    rows = []
    for sample in samples:
        row = {
            "sample_id": sample.sample_id,
            "origin_date": str(sample.origin_date),
            "target_date": str(sample.target_date),
            "contract_month": sample.contract_month,
            "decision_time": sample.decision_time.isoformat(),
            "label_available_at": sample.label_available_at.isoformat(),
            "origin_price": sample.origin_price,
            "target_return": sample.target_return,
            "source_hash": sample.source_hash,
            "target_source_hash": sample.target_source_hash,
        }
        row.update(sample.features)
        rows.append(row)
    frame = pd.DataFrame(rows)

    destination = (
        args.destination
        or str(default_data_root() / "lab" / "isolated_research" / "qlib-v0.9.7")
    )
    result = export_isolated_research_dataset(
        "qlib",
        frame,
        destination,
        dataset_id="jnu_p2_development_v1",
        source_hash=source_fingerprint(samples),
        protocol_hash=p2.hash,
        task="RETURN_REGRESSION",
    )
    result.update({
        "status": "EXPORTED_NOT_EXECUTED",
        "development_origins": len(samples),
        "quarantine_origins_exported": 0,
        "final_origins_exported": 0,
        "qlib_imported": False,
        "qlib_executed": False,
    })
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
