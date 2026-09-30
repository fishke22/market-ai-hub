"""Fail-closed size budget for zero-cost P5 GitHub Actions artifacts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

STATE_LIMIT = 8 * 1024 * 1024
DIAGNOSTIC_LIMIT = 2 * 1024 * 1024
STATE_PATHS = (
    Path("audit/prediction_audit.duckdb"),
    Path("automation/p5_forward_state.json"),
    Path("cloud/p5_cloud_run_summary.json"),
    Path("cloud/p5_cloud_state_manifest.json"),
)


def _size(path: Path) -> int:
    return path.stat().st_size if path.is_file() else 0


def validate_budget(root: Path) -> dict:
    state = sum(_size(root / rel) for rel in STATE_PATHS)
    diagnostics = 0
    for rel in (Path("cloud"), Path("automation")):
        base = root / rel
        if base.is_dir():
            diagnostics += sum(p.stat().st_size for p in base.rglob("*") if p.is_file())
    return {
        "schema": "AV2.P5.ZERO_COST_ARTIFACT_BUDGET.1",
        "status": "PASS" if state <= STATE_LIMIT and diagnostics <= DIAGNOSTIC_LIMIT else "FAIL",
        "state_bytes": state,
        "state_limit_bytes": STATE_LIMIT,
        "diagnostic_bytes": diagnostics,
        "diagnostic_limit_bytes": DIAGNOSTIC_LIMIT,
        "paid_storage_expansion_allowed": False,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True)
    args = ap.parse_args()
    result = validate_budget(args.root)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
