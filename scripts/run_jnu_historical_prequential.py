from __future__ import annotations

import json

from market_ai_hub.research.historical_prequential import run_replay, save_one_use_evidence
from market_ai_hub.services.model_runtime import get_chronos, get_timesfm


def main() -> int:
    result = run_replay(
        {
            "chronos-2": get_chronos(),
            "timesfm-3.0": get_timesfm(),
        }
    )
    if result.get("status") != "OK":
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2
    path = save_one_use_evidence(result)
    summary = {
        "status": result["status"],
        "evidence_id": result["evidence_id"],
        "evidence_grade": result["evidence_grade"],
        "origin_count": result["origin_count"],
        "partition_counts": result["partition_counts"],
        "first_origin": result["first_origin"],
        "last_origin": result["last_origin"],
        "sealed_path": str(path),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
