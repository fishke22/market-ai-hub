import json

import market_ai_hub.packet.builder as builder
from market_ai_hub.services.public_view import packet_target_model_analysis


def _analysis_summary(symbol="3706.TW", horizon="4d"):
    return {
        "status": "OK",
        "target_family": "TAIWAN_STOCK",
        "symbol": symbol,
        "horizon": horizon,
        "data_integrity": {
            "status": "PASS",
            "corporate_action_integrity": "CORPORATE_ACTION_NORMALIZED",
        },
        "dataset_semantics": "TAIWAN_STOCK_REFERENCE_RESET_CONTINUITY_V1",
        "adjustment_semantics": "FORWARD_EFFECTIVE_DATE_REFERENCE_RESET_V1",
        "source_semantics": "RAW_DAILY_PLUS_FINMIND_REFERENCE_EVENTS_V1",
        "feature_version": "base-v1",
        "price_basis": "RAW_CURRENT_BASIS",
        "reference_price": 81.8,
        "reference_price_type": "CLOSE",
        "reference_price_timestamp": "2026-09-24T05:30:00+00:00",
        "reference_price_source": "finmind:TaiwanStockPrice",
        "reference_data_grade": "RESEARCH_PROXY",
        "models": {},
        "price_forecast_ensemble": {},
        "validation_claims": {
            "PREDICTIVE_GAIN": False,
            "CALIBRATED": False,
            "TRADING_EDGE": False,
        },
    }


def _context_summary(symbol="3706.TW"):
    return {
        "schema_version": "TAIWAN_STOCK_CONTEXT_V2",
        "source_semantics_version": "FINMIND_FREE_TARGET_CONTEXT_ASOF_V2",
        "freshness_policy_version": "TAIWAN_STOCK_CONTEXT_FRESHNESS_V2",
        "symbol": symbol,
        "role": "TARGET_CONTEXT_ONLY_NOT_PREDICTIVE_FEATURE",
        "predictive_feature_eligible": False,
        "historical_revision_safe": False,
        "channels": {
            "valuation": {
                "status": "AVAILABLE",
                "values": {"pe_ratio": 12.0, "pbr": 1.5},
                "pit_usable": True,
            },
            "eps": {
                "status": "AVAILABLE_NON_PIT_CONTEXT",
                "values": {"eps": 1.48},
                "pit_usable": False,
            },
            "monthly_revenue": {
                "status": "AVAILABLE",
                "values": {"revenue": 120.0, "yoy_growth": 0.2},
                "pit_usable": True,
            },
            "institutional_flow": {
                "status": "AVAILABLE",
                "values": {"total_net": 200.0},
                "pit_usable": True,
            },
            "news": {
                "status": "NOT_AVAILABLE",
                "generic_web_news_fallback_allowed": False,
            },
        },
        "coverage": {
            "status": "PARTIAL",
            "context_data_ready": True,
            "predictive_experiment_data_ready": False,
        },
        "validation_claims": {
            "PREDICTIVE_GAIN": False,
            "CALIBRATED": False,
            "TRADING_EDGE": False,
        },
    }


def _packet(monkeypatch, analysis=None):
    monkeypatch.setattr(
        builder,
        "_taiwan_stock_analysis",
        lambda target, horizon: analysis or _analysis_summary(target, horizon),
    )
    monkeypatch.setattr(
        builder,
        "_taiwan_stock_context",
        lambda target, as_of: _context_summary(target),
    )
    monkeypatch.setattr(builder, "_factor_observation_summary", lambda family, cutoff: [])
    monkeypatch.setattr(builder, "_model_input_readiness", lambda family, cutoff: {})
    monkeypatch.setattr(builder, "_regime_panel", lambda family: None)
    monkeypatch.setattr(builder, "_event_snapshot", lambda top_n=5: [])
    return builder.build_analysis_packet(
        market="taiwan_stock",
        target="3706.TW",
        horizon="4d",
        detail_level="normal",
        save_analysis=False,
    )


def test_taiwan_packet_has_no_jnu_specific_forward_gates(monkeypatch):
    packet = _packet(monkeypatch)
    gates = packet["research_gates"]
    assert gates["TARGET_FAMILY_SCOPE"] == "TAIWAN_STOCK"
    assert "TAIWAN_STOCK_VALIDATION" in gates
    assert "ACCURACY_V2_P5_FORWARD" not in gates
    assert "FUTURE_DATA_ACQUISITION" not in gates
    context_gate = gates["TAIWAN_TARGET_CONTEXT"]
    assert context_gate["predictive_experiment_data_ready"] is False
    assert context_gate["historical_revision_safe"] is False
    assert context_gate["predictive_feature_use"] == (
        "BLOCKED_UNTIL_PREREGISTERED_IMMUTABLE_SNAPSHOT_PROTOCOL"
    )
    assert context_gate["news_status"] == "NOT_AVAILABLE"

    text = json.dumps(gates, ensure_ascii=False)
    for forbidden in (
        "jnu_forward_publication_monitor_v1",
        "JPX Micro",
        "JPX OSE Daily Report",
        "TAIFEX TMF",
    ):
        assert forbidden not in text


def test_taiwan_economic_edge_is_not_borrowed_from_osaka(monkeypatch):
    packet = _packet(monkeypatch)
    edge = packet["economic_edge_summary"]
    assert edge["status"] == "ECONOMIC_EDGE_NOT_EVALUATED"
    assert edge["evidence_scope"] == "TAIWAN_STOCK"
    assert "Phase2V-C" not in json.dumps(edge, ensure_ascii=False)


def test_taiwan_decision_support_is_family_scoped(monkeypatch):
    packet = _packet(monkeypatch)
    support = packet["research_decision_support"]
    assert support["target_family_scope"] == "TAIWAN_STOCK"
    assert support["broker_ui_text_translation_allowed"] is False
    assert support["corporate_action_integrity_required"] is True
    assert support["model_result_in_packet"] is True
    assert support["model_result_status"] == "OK"
    assert support["model_result_integrity_status"] == "PASS"
    assert support["research_stance_allowed"] is True
    assert support["model_result_integration_status"] == "GOVERNED_TAIWAN_ANALYZER_INTEGRATED"
    text = json.dumps(support, ensure_ascii=False)
    assert "get_itrader_advisory" not in text
    assert "settlement_and_trading_path" not in text


def test_taiwan_packet_embeds_same_target_governed_model_result(monkeypatch):
    packet = _packet(monkeypatch)
    model = packet["target_model_analysis"]

    assert packet["reference_price"] == 81.8
    assert packet["target_data_status"] == "RESEARCH_PROXY"
    assert packet["target_price_source"] == "finmind:TaiwanStockPrice"
    assert model["symbol"] == "3706.TW"
    assert model["data_integrity"]["status"] == "PASS"
    assert model["validation_claims"] == {
        "PREDICTIVE_GAIN": False,
        "CALIBRATED": False,
        "TRADING_EDGE": False,
    }
    assert packet["target_semantics"]["direct_stock_forecast_status"] == (
        "RESEARCH_AVAILABLE_FORWARD_UNVALIDATED"
    )
    assert packet["display_policy"]["may_present_as_direct_forecast"] is True
    context = packet["target_context_snapshot"]
    assert context["schema_version"] == "TAIWAN_STOCK_CONTEXT_V2"
    assert context["channels"]["valuation"]["values"]["pe_ratio"] == 12.0
    assert context["channels"]["eps"]["pit_usable"] is False
    assert context["channels"]["news"]["status"] == "NOT_AVAILABLE"
    assert context["coverage"]["predictive_experiment_data_ready"] is False
    assert packet["target_semantics"]["target_context_contract"]["predictive_feature_eligible"] is False
    assert packet["research_decision_support"]["target_context_in_packet"] is True
    assert packet["research_decision_support"]["target_context_news_status"] == "NOT_AVAILABLE"


def test_taiwan_packet_data_integrity_block_never_falls_back_to_weaker_reference(monkeypatch):
    blocked = {
        "status": "DATA_INTEGRITY_BLOCKED",
        "target_family": "TAIWAN_STOCK",
        "symbol": "3706.TW",
        "horizon": "4d",
        "data_integrity": {
            "status": "BLOCKED",
            "reason": "CORPORATE_ACTION_REFERENCE_CHANNEL_INCOMPLETE",
        },
        "reference_price": None,
        "models": {},
        "price_forecast_ensemble": {},
        "validation_claims": {
            "PREDICTIVE_GAIN": False,
            "CALIBRATED": False,
            "TRADING_EDGE": False,
        },
    }
    packet = _packet(monkeypatch, analysis=blocked)

    assert packet["reference_price"] is None
    assert packet["target_data_status"] == "DATA_INTEGRITY_BLOCKED"
    assert packet["target_price_source"] == "unavailable"
    assert packet["target_model_analysis"]["status"] == "DATA_INTEGRITY_BLOCKED"
    assert packet["display_policy"]["may_present_as_direct_forecast"] is False
    assert packet["display_policy"]["may_present_research_stance"] is False
    assert packet["research_decision_support"]["research_stance_allowed"] is False
    assert packet["research_decision_support"]["model_result_integrity_status"] == "BLOCKED"


def test_packet_model_summary_removes_raw_direction_scores_and_internal_errors():
    raw = {
        "status": "OK",
        "symbol": "3706.TW",
        "horizon": "4d",
        "data_integrity": {"status": "PASS"},
        "dataset_semantics": "TAIWAN_STOCK_REFERENCE_RESET_CONTINUITY_V1",
        "adjustment_semantics": "FORWARD_EFFECTIVE_DATE_REFERENCE_RESET_V1",
        "source_semantics": "RAW_DAILY_PLUS_FINMIND_REFERENCE_EVENTS_V1",
        "feature_version": "base-v1",
        "price_basis": "RAW_CURRENT_BASIS",
        "reference_price": 81.8,
        "reference_price_type": "CLOSE",
        "reference_price_timestamp": "2026-09-24T05:30:00+00:00",
        "reference_price_source": "finmind:TaiwanStockPrice",
        "reference_data_grade": "RESEARCH_PROXY",
        "chronos": {
            "model": "chronos-2",
            "model_task": "PRICE_FORECAST",
            "symbol": "3706.TW",
            "horizon": "4d",
            "point_forecast": 83.0,
            "terminal_forecast": 83.0,
            "expected_return": 0.014,
            "forecast_dates": ["2026-09-30"],
            "forecast_path": [],
            "quantiles": {"p10": 78.0, "p50": 83.0, "p90": 88.0},
            "target_calendar": "XTAI",
            "calendar_grade": "VERIFIED",
            "engineering_status": "PASS",
            "predictive_validation_status": "UNVALIDATED",
            "data_grade": "RESEARCH_PROXY",
            "direction": "up",
            "class_probabilities": {"up": 0.9},
        },
        "timesfm": {"status": "unavailable", "error": "internal stack detail"},
        "price_forecast_ensemble": {
            "status": "OK",
            "expected_return": 0.014,
            "quantiles": {"p10": 78.0, "p50": 83.0, "p90": 88.0},
        },
        "direction_classification_ensemble": {
            "class_probabilities": {"up": 0.9},
            "raw_direction_research": {"raw_argmax": {"xgb": "up"}},
        },
        "ensemble": {
            "model": "ensemble",
            "model_task": "ENSEMBLE",
            "symbol": "3706.TW",
            "horizon": "4d",
            "point_forecast": 83.0,
            "terminal_forecast": 83.0,
            "expected_return": 0.014,
            "forecast_dates": [],
            "forecast_path": [],
            "quantiles": {},
            "target_calendar": "XTAI",
            "calendar_grade": "VERIFIED",
            "engineering_status": "PASS",
            "predictive_validation_status": "UNVALIDATED",
            "data_grade": "RESEARCH_PROXY",
            "model_metadata": {
                "direction_status": "NO_VALIDATED_MODEL_CONSENSUS",
                "direction_value": None,
                "eligible_direction_vote_count": 0,
            },
        },
        "used_base_models": ["chronos-2"],
        "used_ensemble": True,
        "confidence_inputs": {},
        "warnings": [],
    }

    summary = packet_target_model_analysis(raw, market="taiwan")

    assert summary["models"]["chronos"]["model_name"] == "chronos-2"
    assert "direction" not in summary["models"]["chronos"]
    assert "class_probabilities" not in summary["models"]["chronos"]
    assert summary["models"]["timesfm"] == {"status": "unavailable"}
    assert "error" not in summary["models"]["timesfm"]
    assert "direction_classification_ensemble" not in summary
    assert summary["validation_claims"]["PREDICTIVE_GAIN"] is False
    assert summary["validation_claims"]["CALIBRATED"] is False
    assert summary["validation_claims"]["TRADING_EDGE"] is False
