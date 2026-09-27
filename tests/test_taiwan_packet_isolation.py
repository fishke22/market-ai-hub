import json

import market_ai_hub.packet.builder as builder


def _packet(monkeypatch):
    monkeypatch.setattr(builder, "_taiwan_stock_reference", lambda target: None)
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
    assert support["model_result_in_packet"] is False
    assert support["model_result_integration_status"] == "SEPARATE_ANALYZER_NOT_YET_PACKET_INTEGRATED"
    text = json.dumps(support, ensure_ascii=False)
    assert "get_itrader_advisory" not in text
    assert "settlement_and_trading_path" not in text
