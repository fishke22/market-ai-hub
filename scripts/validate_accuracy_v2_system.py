"""Complete Accuracy v2 engineering/readiness validation."""
from __future__ import annotations

import json

from market_ai_hub.research.accuracy_v2_p4_engine import analyze_no_new_forward_outcome
from market_ai_hub.research.accuracy_v2_p5_engine import p5_forward_evidence_summary, preview_p5_origin
from market_ai_hub.research.accuracy_v2_p7_engine import run_p7_acceptance
from market_ai_hub.services.build_info import build_fingerprint
from market_ai_hub.services.jnu_direct import analyze_jnu_direct


def main() -> int:
    jnu = analyze_jnu_direct("1d", validate_history=False)
    p4 = analyze_no_new_forward_outcome()
    p5_preview = preview_p5_origin()
    p5 = p5_forward_evidence_summary()
    p7 = run_p7_acceptance()
    analysis_ready = jnu.get("status") == "OK" and p4.get("status") == "OK"
    governed_prediction_ready = p5_preview.get("status") in {
        "WAITING_FOR_ORIGIN", "ELIGIBLE", "ALREADY_PRECOMMITTED",
        "BEFORE_FIRST_ELIGIBLE_ORIGIN", "MISSED_CANONICAL_ORIGIN",
    }
    p7_ready = p7.get("engineering_status") == "P7_ENGINEERING_PASS"
    overall = analysis_ready and governed_prediction_ready and p7_ready
    out = {
        "schema_version": "AV2.READINESS.1",
        "status": "READY_FOR_ANALYSIS_AND_GOVERNED_PREDICTION" if overall else "NOT_READY",
        "build": build_fingerprint(),
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
