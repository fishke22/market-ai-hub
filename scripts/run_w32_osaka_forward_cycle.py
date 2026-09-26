"""Operate the W3.2 exact-contract Osaka forward cycle from canonical local stores.

Research only.  This script never calls a broker and never accepts market values from
the command line.  It first attempts settlement of pending W3.2 forward predictions
from the canonical Feature Store, then precommits the next 1-session baseline from
the exact contract DAILY terminal close already present in that store.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from market_ai_hub.feature_store.store import FeatureStore
from market_ai_hub.research.v2 import forward_cycle as FC
from market_ai_hub.research.v2 import prediction_audit as PA

_JNU_RE = re.compile(r"^JNU\d{4}$")


def _is_w32_scope(pred: PA.PredictionRecord) -> bool:
    return (

        pred.target_family == FC.TARGET_FAMILY
        and pred.instrument == FC.INSTRUMENT
        and pred.horizon == FC.HORIZON
        and (
            (pred.model == FC.MODEL_NAME and pred.model_version == FC.MODEL_VERSION)
            or (pred.model == FC.EVENT_MODEL_NAME and pred.model_version == FC.EVENT_MODEL_VERSION)
        )
        and pred.sample_origin == "FORWARD_PRECOMMITTED"
    )


def _public_result(result: FC.ForwardCycleResult) -> dict[str, Any]:
    return {
        "status": result.status,
        "reason": result.reason,
        "prediction_id": result.prediction_id,
        "forecast_artifact_id": result.forecast_artifact_id,
        "outcome_id": result.outcome_id,
        "input_trading_date": result.input_trading_date,
        "target_trading_date": result.target_trading_date,
        "values_exposed": False,
    }


def run_cycle(
    contract_code: str,
    *,
    db: PA.PredictionAuditDB | None = None,
    store: FeatureStore | None = None,
) -> dict[str, Any]:
    contract = str(contract_code or "").strip().upper()
    if not _JNU_RE.fullmatch(contract):
        raise ValueError("EXPECTED_EXACT_JNU_CONTRACT")

    audit = db or PA.PredictionAuditDB()
    features = store or FeatureStore()
    settlements: list[dict[str, Any]] = []

    for prediction_id in audit.list_prediction_ids():
        pred = audit.get_prediction(prediction_id)
        if pred is None or not _is_w32_scope(pred):
            continue
        if audit.get_outcomes(prediction_id):
            continue
        if pred.model == FC.EVENT_MODEL_NAME:
            result = FC.settle_osaka_event_probability_from_feature_store(
                prediction_id, db=audit, store=features,
            )
        else:
            result = FC.settle_osaka_from_feature_store(
                prediction_id, db=audit, store=features,
            )
        settlements.append(_public_result(result))

    precommit = FC.precommit_osaka_from_feature_store(
        contract_code=contract, db=audit, store=features,
    )
    event_precommit = FC.precommit_osaka_event_probability_from_feature_store(
        contract_code=contract, db=audit, store=features,
    )
    return {
        "schema": "W3.2_OSAKA_FORWARD_OPERATOR_V2",
        "contract_code": contract,
        "settlements": settlements,
        "precommit": _public_result(precommit),
        "event_probability_precommit": _public_result(event_precommit),
        "values_exposed": False,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--contract-code", required=True)
    args = ap.parse_args(argv)
    try:
        result = run_cycle(args.contract_code)
    except Exception as exc:
        print(json.dumps({
            "status": "ERROR",
            "error_type": type(exc).__name__,
            "values_exposed": False,
        }, ensure_ascii=False, sort_keys=True))
        return 1

    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    ok = {FC.STATUS_PRECOMMITTED, FC.STATUS_ALREADY_PRECOMMITTED}
    point_status = result["precommit"]["status"]
    event_status = result["event_probability_precommit"]["status"]
    return 0 if point_status in ok and event_status in ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
