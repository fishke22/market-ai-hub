"""Phase 3A — Price/Probability Map research foundation tests。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, "src")
ROOT = Path(__file__).resolve().parents[1]


# ── §B9：p10/p50/p90 only → no fake probability ──

def test_p10_p50_p90_only_no_fake_probability():
    from market_ai_hub.research.price_probability_map import probability_from_quantiles_only

    pbm = probability_from_quantiles_only(["BUY_ZONE", "NEUTRAL_ZONE", "PROFIT_ZONE"], "X", "TAIWAN_STOCK", "1d")
    for z in pbm.zones:
        assert z.availability_status == "NOT_AVAILABLE_INSUFFICIENT_DISTRIBUTION"
        assert z.terminal_probability is None
        assert z.touch_probability is None


# ── §B15/§B27：uncalibrated → no public % ──

def test_uncalibrated_no_public_percent():
    from market_ai_hub.research.price_probability_map import ProbabilityMap, ZoneProbability

    pbm = ProbabilityMap("X", "TAIWAN_STOCK", "1d",
                         zones=[ZoneProbability(zone="BUY_ZONE", terminal_probability=0.18,
                                                availability_status="AVAILABLE", calibration_status="UNCALIBRATED")],
                         calibration_status="UNCALIBRATED")
    pub = pbm.public_view()
    assert "terminal_probability" not in pub["zones"][0]
    assert "18" not in str(pub)


def test_calibrated_public_percent_ok():
    from market_ai_hub.research.price_probability_map import ProbabilityMap, ZoneProbability

    pbm = ProbabilityMap("X", "TAIWAN_STOCK", "1d",
                         zones=[ZoneProbability(zone="BUY_ZONE", terminal_probability=0.18,
                                                availability_status="AVAILABLE", calibration_status="CALIBRATED")],
                         calibration_status="CALIBRATED")
    assert pbm.public_view()["zones"][0]["terminal_probability"] == 0.18


# ── §B9-B11：terminal / touch / first_passage separated ──

def test_terminal_not_touch():
    from market_ai_hub.research.price_probability_map import ZoneProbability

    z = ZoneProbability(zone="BUY_ZONE")
    # 三個欄位必須分開存在（不得共用同一值）
    assert hasattr(z, "terminal_probability")
    assert hasattr(z, "touch_probability")
    assert z.terminal_probability is None and z.touch_probability is None


def test_touch_not_first_passage():
    from market_ai_hub.research.price_probability_map import ZoneProbability

    z = ZoneProbability(zone="PROFIT_ZONE")
    assert hasattr(z, "touch_probability")
    assert hasattr(z, "first_passage_probability")


# ── §B13/§B14：multimodal not collapse ──

def test_multimodal_not_collapse_to_mean():
    from market_ai_hub.research.price_probability_map import DistributionDiagnostics

    d = DistributionDiagnostics(method="EMPIRICAL", sample_size=500, mode_count=2,
                                multimodality_status="MULTIMODAL", status="OK")
    assert d.mode_count == 2
    assert d.multimodality_status == "MULTIMODAL"


def test_insufficient_sample_diagnostics():
    from market_ai_hub.research.price_probability_map import DistributionDiagnostics

    d = DistributionDiagnostics(sample_size=3)
    assert d.status == "INSUFFICIENT_EVIDENCE"


# ── §B5：profiles ──

def test_stock_profile_not_osaka_profile():
    from market_ai_hub.research.price_probability_map import profile_for

    stock = profile_for("TAIWAN_STOCK")
    osaka = profile_for("OSAKA_MICRO")
    assert stock["structural_asymmetry"] is True
    assert osaka["structural_asymmetry"] is False


# ── §B2：state != trade action ──

def test_zone_state_not_trade_action():
    from market_ai_hub.research.price_probability_map import six_state_research_view

    pm = six_state_research_view("TAIWAN_STOCK", "3706.TW", "1d", 79.8, market_state="BUY_ZONE")
    assert pm.state_is_trade_instruction is False
    assert pm.actionability_status == "NOT_VALIDATED"


def test_unknown_state_rejected():
    from market_ai_hub.research.price_probability_map import six_state_research_view

    with pytest.raises(ValueError):
        six_state_research_view("TAIWAN_STOCK", "X", "1d", 1.0, market_state="BUY_ORDER")


# ── §B16：model failure != simple stop loss ──

def test_model_failure_not_simple_stop_loss():
    from market_ai_hub.research.price_probability_map import MODEL_FAILURE_STATUSES

    assert "COVERAGE_FAILURE" in MODEL_FAILURE_STATUSES
    assert "PIT_DRIFT" in MODEL_FAILURE_STATUSES
    assert "ERROR_REGIME_SHIFT" in MODEL_FAILURE_STATUSES
    assert "MODEL_FAILURE" in MODEL_FAILURE_STATUSES
    # 不得只有一個 price-level stop
    assert "STOP_LOSS" not in MODEL_FAILURE_STATUSES


# ── §B21/§B32：benchmark framework, no best ──

def test_benchmark_registry_no_best_claim():
    from market_ai_hub.research.price_probability_map import benchmark_registry

    reg = benchmark_registry()
    assert len(reg["benchmarks"]) == 7
    assert "no BEST" in reg["note"] or "OOS validation required" in reg["note"]
    assert "PROVEN PROFITABLE" not in str(reg)


# ── §B20：strategy switching is candidate, not instruction ──

def test_strategy_switching_not_instruction():
    from market_ai_hub.research.price_probability_map import strategy_candidate_for

    c = strategy_candidate_for("RANGE_LOW_VOL", regime_status="EVALUATED")
    assert c["candidate"] == "mean_reversion_candidate"
    assert c["is_instruction"] is False
    # regime 未評估 → NONE
    assert strategy_candidate_for(None)["candidate"] == "NONE"


# ── cross-ref：Taiwan truth not inherit Osaka ──

def test_taiwan_truth_not_inherit_osaka():
    from market_ai_hub.services.research_truth import evidence_for

    ev = evidence_for("TAIWAN_INDEX", "TAIEX")
    for m in ("VAR(1)", "NON_EXECUTABLE_FORECAST_EDGE", "225LABO"):
        assert m not in str(ev)


def test_fresh_sample_not_oos_evidence():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "capture_fresh", ROOT / "scripts" / "capture_fresh_validation_sample.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.SAMPLE_META["not_predictive_evidence"] is True
    assert mod.SAMPLE_META["not_model_selection_data"] is True
