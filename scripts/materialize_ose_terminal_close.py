"""Offline operator entrypoint for W3.2 OSE/JNU DAILY terminal-close materialization.

Consumes only persisted recorder artifacts.  It never logs in, subscribes, requests
quotes, or accepts a caller-supplied close price.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from market_ai_hub.integrations.yuanta.live_quote_recorder import recorder_root
from market_ai_hub.research.v2 import terminal_close_materializer as TCM


def _resolve_artifact(base: Path, value: str) -> Path:
    root = base.resolve()
    text = str(value or "").strip()
    if not text:
        raise ValueError("ARTIFACT_PATH_REQUIRED")
    raw = Path(text).expanduser()
    candidate = raw if raw.is_absolute() else root / raw
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise ValueError("ARTIFACT_OUTSIDE_RECORDER_ROOT") from exc
    if not resolved.is_file():
        raise FileNotFoundError("ARTIFACT_NOT_FOUND")
    return resolved


def _public_result(result: TCM.TerminalCloseMaterializationResult) -> dict:
    return {
        "status": result.status,
        "reason": result.reason,
        "contract_code": result.contract_code,
        "contract_month": result.contract_month,
        "trading_date": result.trading_date,
        "session_close_timestamp": (
            result.session_close_timestamp.isoformat()
            if result.session_close_timestamp is not None else None
        ),
        "available_at": (
            result.available_at.isoformat() if result.available_at is not None else None
        ),
        "source_snapshot_ids": list(result.source_snapshot_ids),
        "lineage_id": result.lineage_id,
        "values_exposed": False,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw-artifact", required=True)
    ap.add_argument("--evidence-artifact", required=True)
    ap.add_argument("--expected-contract-code", default="")
    args = ap.parse_args(argv)

    try:
        base = recorder_root()
        raw = _resolve_artifact(base, args.raw_artifact)
        evidence = _resolve_artifact(base, args.evidence_artifact)
        result = TCM.materialize_ose_terminal_close_from_artifacts(
            raw,
            evidence,
            expected_contract_code=args.expected_contract_code,
        )
        print(json.dumps(_public_result(result), ensure_ascii=False, sort_keys=True))
        return 0 if result.status in {
            TCM.STATUS_MATERIALIZED,
            TCM.STATUS_ALREADY_MATERIALIZED,
        } else 2
    except Exception as exc:
        print(json.dumps({
            "status": "ERROR",
            "error_type": type(exc).__name__,
            "values_exposed": False,
        }, ensure_ascii=False, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
