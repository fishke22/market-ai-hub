"""Complete Accuracy v2 engineering/readiness validation."""
from __future__ import annotations

import json

from market_ai_hub.research.accuracy_v2_p4_engine import analyze_no_new_forward_outcome
from market_ai_hub.research.accuracy_v2_p5_engine import p5_forward_evidence_summary, preview_p5_origin
from market_ai_hub.research.accuracy_v2_p7_engine import run_p7_acceptance
from market_ai_hub.services.build_info import build_fingerprint
from market_ai_hub.services.capability_registry import capability_registry_snapshot
from market_ai_hub.services.data_continuity import jnu_data_continuity_status
from market_ai_hub.services.jnu_direct import analyze_jnu_direct
from market_ai_hub.services.system_completion import system_completion_snapshot


def main() -> int:
    continuity = jnu_data_continuity_status()
    jnu = (
        {"status": "SKIPPED_DATA_CONTINUITY_MODE", "direct_model_available": False}
        if continuity.get("context_only")
        else analyze_jnu_direct("1d", validate_history=False)
    )
    p4 = analyze_no_new_forward_outcome()
    p5_preview = preview_p5_origin()
    p5 = p5_forward_evidence_summary()
    p7 = run_p7_acceptance()
    capabilities = capability_registry_snapshot()
    completion = system_completion_snapshot()

    p4_ready = p4.get("status") == "OK"
    analysis_ready = p4_ready and (
        jnu.get("status") == "OK" or bool(continuity.get("target_reference_available"))
    )
    governed_prediction_ready = (
        not continuity.get("context_only")
        and p5_preview.get("status") in {
            "WAITING_FOR_ORIGIN", "ELIGIBLE", "ALREADY_PRECOMMITTED",
            "BEFORE_FIRST_ELIGIBLE_ORIGIN", "MISSED_CANONICAL_ORIGIN",
        }
    )
    context_only_ready = bool(
        continuity.get("context_only")
        and continuity.get("target_reference_available")
        and p4_ready
    )
    p7_ready = p7.get("engineering_status") == "P7_ENGINEERING_PASS"
    engineering_complete = bool(
        completion.get("all_currently_actionable_engineering_complete")
    )
    overall = (
        analysis_ready
        and (governed_prediction_ready or context_only_ready)
        and p7_ready
        and engineering_complete
    )
    readiness_status = (
        "READY_FOR_ANALYSIS_AND_GOVERNED_PREDICTION"
        if overall and governed_prediction_ready
        else "READY_FOR_CONTEXT_ANALYSIS_ONLY"
        if overall and context_only_ready
        else "NOT_READY"
    )
    out = {
        "schema_version": "AV2.READINESS.1",
        "status": readiness_status,
        "build": build_fingerprint(),
        "data_continuity": continuity,
        "capability_registry_summary": capabilities.get("summary"),
        "system_completion": {
            "status": completion.get("status"),
            "all_currently_actionable_engineering_complete": engineering_complete,
            "actionable_engineering_gap_count": completion.get(
                "actionable_engineering_gap_count"
            ),
            "conditional_packages": completion.get("conditional_packages"),
            "deferred_non_blocking": completion.get("deferred_non_blocking"),
            "external_dependencies": completion.get("external_dependencies"),
        },
        "analysis": {
            "ready": analysis_ready,
            "jnu_status": jnu.get("status"),
            "direct_model_available": jnu.get("direct_model_available"),
            "research_stance": jnu.get("research_stance"),
            "not_trading_edge": jnu.get("not_trading_edge"),
            "p4_status": p4.get("status"),
            "point_reference": p4.get("point_reference"),
            "interval": p4.get("empirical_interval"),
            "decision_support": p4.get("decision_support"),
        },
        "forward_monitor": {
            "ready": governed_prediction_ready,
            "context_only_ready": context_only_ready,
            "preview": p5_preview,
            "expected_origins": p5.get("expected_canonical_origins"),
            "canonical_predictions": p5.get("canonical_prediction_count"),
            "settled_origins": p5.get("settled_canonical_origin_count"),
            "downgrade_state": p5.get("downgrade_state"),
        },
        "p7": p7,
        "conditional_remaining": {
            "P6": "BLOCKED_UNTIL_DATA_RUNTIME_AND_INDEPENDENT_GAIN_PREREQUISITES",
            "completion_blocker": False,
        },
        "PREDICTIVE_GAIN": False,
        "CALIBRATED": False,
        "TRADING_EDGE": False,
        "live_execution_enabled": False,
    }
    print(json.dumps(out, ensure_ascii=False, sort_keys=True, default=str))
    return 0 if overall else 2


if __name__ == "__main__":
    raise SystemExit(main())
