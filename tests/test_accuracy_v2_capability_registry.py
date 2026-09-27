import market_ai_hub.services.capability_registry as cr


class Card:
    def __init__(self, status="PASS", predictive="UNVALIDATED"):
        self.engineering_status = status
        self.predictive_validation_status = predictive


def test_capability_registry_is_machine_readable_and_fail_closed(monkeypatch):
    monkeypatch.setattr(
        cr,
        "jnu_data_continuity_status",
        lambda: {
            "mode": "DATA_CONTINUITY_MODE",
            "target_reference_available": True,
            "reason": "EXPECTED_PUBLISHED_OBSERVATION_OVERDUE",
            "context_confidence_grade": "LOW",
        },
    )
    monkeypatch.setattr(
        cr,
        "live_model_cards",
        lambda: {
            "chronos-2": Card(),
            "timesfm-3.0": Card(),
        },
    )
    monkeypatch.setattr(
        cr,
        "p5_forward_evidence_summary",
        lambda: {
            "settled_canonical_origin_count": 0,
            "CALIBRATED": False,
        },
    )
    monkeypatch.setattr(
        cr,
        "future_data_readiness",
        lambda: {
            "active_public_collectors": ["jpx_ose_micro", "taifex_tmf"],
        },
    )
    monkeypatch.setattr(
        cr,
        "open_source_adapter_status",
        lambda: {
            "nautilus_trader": {
                "configured_executable_exists": True,
                "status": "READY_TO_EXECUTE",
            },
        },
    )
    out = cr.capability_registry_snapshot()
    rows = {c["capability_id"]: c for c in out["capabilities"]}
    assert rows["jnu_exact_contract_analysis"]["data_ready"] is False
    assert rows["jnu_exact_contract_analysis"]["blocked_reason"] == "EXPECTED_PUBLISHED_OBSERVATION_OVERDUE"
    assert rows["jnu_data_continuity_context"]["available"] is True
    assert rows["jnu_data_continuity_context"]["details"]["not_probability"] is True
    assert rows["calibrated_public_probability"]["available"] is False
    assert rows["trading_edge_claim"]["available"] is False
    assert rows["live_trading"]["available"] is False
    assert rows["system_engineering_completion"]["available"] is True
    assert rows["taiex_official_daily_reference"]["available"] is True
    assert rows["taiex_official_daily_reference"]["details"]["cash_index_executable"] is False
    assert rows["jpx_micro_investor_flow_weekly_context"]["available"] is True
    assert (
        rows["jpx_micro_investor_flow_weekly_context"]["details"][
            "historical_backfill_allowed"
        ]
        is False
    )
    assert out["summary"]["predictive_gain_established"] is False
    assert out["summary"]["trading_edge_established"] is False
    assert out["summary"]["all_currently_actionable_engineering_complete"] is True


def test_capability_registry_marks_normal_target_ready(monkeypatch):
    monkeypatch.setattr(
        cr,
        "jnu_data_continuity_status",
        lambda: {
            "mode": "NORMAL_TARGET_DATA",
            "target_reference_available": True,
            "reason": "",
            "context_confidence_grade": "HIGH",
        },
    )
    monkeypatch.setattr(
        cr,
        "live_model_cards",
        lambda: {
            "chronos-2": Card(),
            "timesfm-3.0": Card(),
        },
    )
    monkeypatch.setattr(
        cr,
        "p5_forward_evidence_summary",
        lambda: {
            "settled_canonical_origin_count": 0,
            "CALIBRATED": False,
        },
    )
    monkeypatch.setattr(cr, "future_data_readiness", lambda: {"active_public_collectors": ["jpx"]})
    monkeypatch.setattr(
        cr,
        "open_source_adapter_status",
        lambda: {"nautilus_trader": {"configured_executable_exists": False, "status": "NOT_INSTALLED"}},
    )
    rows = {
        c["capability_id"]: c
        for c in cr.capability_registry_snapshot()["capabilities"]
    }
    assert rows["jnu_exact_contract_analysis"]["data_ready"] is True
    assert rows["p5_forward_evidence_accumulation"]["data_ready"] is True
    assert rows["chronos_price_research"]["available"] is True
    assert rows["chronos_price_research"]["blocked_reason"] == "PREDICTIVE_GAIN_NOT_ESTABLISHED_CURRENT_ACCURACY_V2"
    assert rows["system_engineering_completion"]["available"] is True
