"""Regression tests for current-vs-legacy Accuracy v2 research truth."""
from market_ai_hub.packet.builder import build_analysis_packet
from market_ai_hub.services.research_truth import research_evidence_summary, model_gate_explanation


def test_current_truth_supersedes_legacy_phase2_without_deleting_history():
    truth = research_evidence_summary()
    assert truth["source"] == "ACCURACY_V2_CURRENT"
    assert truth["direct_micro_historical"] == "BLOCKED_HORIZON_MISMATCH"
    assert truth["direct_micro_development"] == "NO_IMPROVEMENT_BASELINE_RETAINED"
    assert truth["causal"] == "NOT_ESTABLISHED_CURRENT_ACCURACY_V2"
    assert "STATISTICAL_FORECAST_EVIDENCE" in truth["legacy_phase2"]["direct_micro_historical"]
    assert truth["legacy_phase2"]["note"].startswith("historical only")
    reason = model_gate_explanation()
    assert "BLOCKED" in reason.upper()
    assert "NO_IMPROVEMENT" in reason
    assert "historical statistical signal exists" not in reason


def test_osaka_packet_exposes_current_direct_path_without_upgrading_evidence():
    packet = build_analysis_packet(
        market="osaka",
        target="OSE_NIKKEI225_MICRO_FUTURES",
        horizon="1d",
        detail_level="normal",
        save_analysis=False,
    )
    semantics = packet["target_semantics"]
    assert semantics["direct_micro_forecast_status"] == "RESEARCH_AVAILABLE_FORWARD_UNVALIDATED"
    assert "no true Direct Micro model path" not in semantics["direct_micro_forecast_note"]
    assert packet["validation_truth"]["direct_micro_historical"] == "BLOCKED_HORIZON_MISMATCH"
    assert packet["validation_truth"]["direct_micro_development"] == "NO_IMPROVEMENT_BASELINE_RETAINED"
    assert "VAR(1)" not in str(packet["validation_truth"])
    assert packet["best_validated_model"]["status"] == "NONE_FORWARD_VALIDATED"
    assert packet["research_gates"]["TRADING_EDGE_GATE"] == "UNPROVEN"
    assert packet["research_gates"]["STRONG_DIRECTION_WITHOUT_PREDICTIVE_GAIN"] == "BLOCKED"
