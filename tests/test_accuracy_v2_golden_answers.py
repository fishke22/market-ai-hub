"""Golden-answer semantic regression tests for public/user-facing financial language."""
from market_ai_hub.mcp.server import get_research_gates, get_target_instrument_state
from market_ai_hub.packet.builder import build_analysis_packet
from market_ai_hub.services.jnu_direct import jnu_user_summary
from market_ai_hub.services.research_truth import research_evidence_summary


def _synthetic_jnu_result():
    return {
        "status": "OK",
        "data": {
            "contract_month": "202610",
            "latest_date": "2026-09-25",
            "latest_settlement": 66140.0,
        },
        "ensemble": {
            "p10": 64000.0,
            "p50": 66140.0,
            "p90": 68000.0,
            "expected_return": 0.0,
        },
        "research_stance": "NEUTRAL",
        "historical_validation": {"status": "NOT_RUN"},
        "historical_prequential": {"status": "BLOCKED_HORIZON_MISMATCH"},
        "robust_analysis": {
            "point_reference": {"price": 66140.0},
            "volatility": {"ewma_return_volatility": 0.01, "regime": "LOW_VOLATILITY"},
            "empirical_interval": {
                "lower_price": 64000.0,
                "upper_price": 68000.0,
                "not_probability": True,
            },
            "lightgbm_quantile_challenger": {"price_quantiles": {}},
        },
    }


def test_golden_jnu_target_is_published_observation_not_next_session():
    out = jnu_user_summary(_synthetic_jnu_result())
    assert "下一筆官方發布的清算價觀測" in out["預測目標"]
    assert "下一交易日的官方清算價" not in str(out)


def test_golden_interval_is_never_presented_as_probability():
    out = jnu_user_summary(
        _synthetic_jnu_result(),
        calibration_status={"public_calibrated": False, "settled_samples": 0},
    )
    assert "不能提供可靠的校準機率" in out["機率狀態"]
    assert "不升級為預測增益、校準機率或交易優勢" in out["無新前向資料時的穩健分析"]["證據限制"]


def test_golden_current_truth_does_not_promote_legacy_var():
    truth = research_evidence_summary()
    assert truth["source"] == "ACCURACY_V2_CURRENT"
    assert truth["direct_micro_historical"] == "BLOCKED_HORIZON_MISMATCH"
    assert truth["direct_micro_development"] == "NO_IMPROVEMENT_BASELINE_RETAINED"
    assert "STATISTICAL_FORECAST_EVIDENCE" not in truth["direct_micro_historical"]
    assert "VAR(1)" not in str({
        "direct_micro_historical": truth["direct_micro_historical"],
        "direct_micro_development": truth["direct_micro_development"],
        "causal": truth["causal"],
    })


def test_golden_analysis_packet_never_says_no_direct_path():
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


def test_golden_proxy_is_not_target():
    state = get_target_instrument_state()
    assert state["roles"]["OSE_NIKKEI225_MICRO_FUTURES"] != state["roles"]["^N225"]
    assert "PROXY" in state["note"]


def test_golden_unproven_edge_remains_unproven():
    gates = get_research_gates()["gates"]
    assert gates["MODEL_PREDICTIVE_GATE"]["status"] == "UNPROVEN"
    assert gates["TRADING_EDGE_GATE"]["result"] == "NO_ECONOMIC_EDGE"
