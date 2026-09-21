"""Phase 3A.1 — target profile isolation + fail-closed defaults tests。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, "src")
ROOT = Path(__file__).resolve().parents[1]


# ── §2/§13：three first-class profiles ──

def test_taiwan_index_profile_not_osaka():
    from market_ai_hub.research.price_probability_map import profile_for

    idx = profile_for("TAIWAN_INDEX")
    osaka = profile_for("OSAKA_MICRO")
    assert idx != osaka
    assert idx["forecast_reference_target"] == "TAIEX"
    assert idx["execution_instruments"] == ["TX", "MTX", "TMF"]
    assert idx["cash_index_executable"] is False
    assert idx["execution_validation"] == "NOT_ESTABLISHED"
    # 不得繼承 Osaka 的 long/short symmetry（structural_asymmetry 不同）
    assert idx["structural_asymmetry"] != osaka["structural_asymmetry"]
    # profile keys 不得含 Osaka/Micro 專屬欄位
    for k in ("ose_session", "micro_params", "holiday_trading", "long_short_symmetric"):
        assert k not in idx


def test_three_families_have_profiles():
    from market_ai_hub.research.price_probability_map import profile_for

    for fam in ("TAIWAN_STOCK", "TAIWAN_INDEX", "OSAKA_MICRO"):
        p = profile_for(fam)
        assert p["target_family"] == fam


# ── §3/§14：unknown family fail closed ──

def test_unknown_profile_fails_closed():
    from market_ai_hub.research.price_probability_map import profile_for

    with pytest.raises(ValueError):
        profile_for("UNKNOWN_FAMILY")
    with pytest.raises(ValueError):
        profile_for("")


def test_no_cross_family_fallback():
    from market_ai_hub.research.price_probability_map import profile_for

    # TAIWAN_INDEX 不得回 Osaka profile
    assert profile_for("TAIWAN_INDEX")["structural_asymmetry"] != profile_for("OSAKA_MICRO")["structural_asymmetry"]


# ── §4/§15：no fake NEUTRAL default ──

def test_no_fake_default_state():
    from market_ai_hub.research.price_probability_map import empty_price_map

    pm = empty_price_map("3706.TW", "TAIWAN_STOCK", "1d", 79.8)
    assert pm.market_state is None
    assert pm.market_state_status == "NOT_EVALUATED"


# ── §5/§16：no fake RANGE default ──

def test_no_fake_default_regime():
    from market_ai_hub.research.price_probability_map import empty_price_map

    pm = empty_price_map("3706.TW", "TAIWAN_STOCK", "1d", 79.8)
    assert pm.regime is None
    assert pm.regime_status == "NOT_EVALUATED"


# ── §6/§17：no fake NORMAL default ──

def test_no_fake_normal_model():
    from market_ai_hub.research.price_probability_map import empty_price_map

    pm = empty_price_map("3706.TW", "TAIWAN_STOCK", "1d", 79.8)
    assert pm.model_failure_state is None
    assert pm.model_failure_evaluation_status == "NOT_EVALUATED"


# ── §7/§18：no fake EMPIRICAL distribution ──

def test_no_fake_empirical_distribution():
    from market_ai_hub.research.price_probability_map import DistributionDiagnostics, ProbabilityMap

    d = DistributionDiagnostics()  # sample_size=0
    assert d.method == "NOT_ESTABLISHED"
    assert d.method != "EMPIRICAL"
    pbm = ProbabilityMap("X", "TAIWAN_STOCK", "1d")
    assert pbm.distribution_method == "NOT_ESTABLISHED"
    assert pbm.calibration_status == "INSUFFICIENT_EVIDENCE"


# ── §8：calibration semantics ──

def test_calibration_distinguishes_no_distribution():
    from market_ai_hub.research.price_probability_map import ProbabilityMap, probability_from_quantiles_only

    # distribution does not exist → INSUFFICIENT_EVIDENCE (not UNCALIBRATED)
    assert ProbabilityMap("X", "TAIWAN_STOCK", "1d").calibration_status == "INSUFFICIENT_EVIDENCE"
    assert probability_from_quantiles_only(["BUY_ZONE"]).calibration_status == "INSUFFICIENT_EVIDENCE"


# ── §9：empty price map ──

def test_empty_price_map_fail_closed():
    from market_ai_hub.research.price_probability_map import empty_price_map

    pm = empty_price_map("TAIEX", "TAIWAN_INDEX", "1d", 47718.84)
    assert pm.market_state is None and pm.market_state_status == "NOT_EVALUATED"
    assert pm.regime is None and pm.regime_status == "NOT_EVALUATED"
    assert pm.model_failure_state is None
    assert pm.probability_map is None
    assert pm.actionability_status == "NOT_VALIDATED"
    assert pm.state_is_trade_instruction is False


# ── §10：six_state_research_view omitted → NOT_EVALUATED ──

def test_six_state_view_omitted_not_evaluated():
    from market_ai_hub.research.price_probability_map import six_state_research_view

    pm = six_state_research_view("TAIWAN_STOCK", "3706.TW", "1d", 79.8)
    assert pm.market_state is None and pm.market_state_status == "NOT_EVALUATED"
    assert pm.regime is None and pm.regime_status == "NOT_EVALUATED"


def test_six_state_view_explicit_evaluated():
    from market_ai_hub.research.price_probability_map import six_state_research_view

    pm = six_state_research_view("TAIWAN_STOCK", "3706.TW", "1d", 79.8,
                                 market_state="BUY_ZONE", regime="RANGE_LOW_VOL")
    assert pm.market_state == "BUY_ZONE" and pm.market_state_status == "EVALUATED"
    assert pm.regime == "RANGE_LOW_VOL" and pm.regime_status == "EVALUATED"
    assert pm.strategy_candidate == "mean_reversion_candidate"


# ── §12：strategy candidate absent when regime unevaluated ──

def test_strategy_candidate_absent_when_regime_unevaluated():
    from market_ai_hub.research.price_probability_map import empty_price_map

    pm = empty_price_map("3706.TW", "TAIWAN_STOCK", "1d", 79.8)
    assert pm.strategy_candidate == "NONE"


# ── §11：NOT_EVALUATED 不在 MARKET_STATES ──

def test_not_evaluated_not_in_market_states():
    from market_ai_hub.research.price_probability_map import MARKET_STATES, REGIMES

    assert "NOT_EVALUATED" not in MARKET_STATES
    assert "NOT_EVALUATED" not in REGIMES


# ── §20：existing invariants preserved ──

def test_existing_invariants_preserved():
    from market_ai_hub.research.price_probability_map import empty_price_map, probability_from_quantiles_only

    pm = empty_price_map("X", "OSAKA_MICRO", "1d", 1.0)
    assert pm.state_is_trade_instruction is False
    assert pm.actionability_status == "NOT_VALIDATED"
    pbm = probability_from_quantiles_only(["BUY_ZONE"])
    z = pbm.zones[0]
    assert hasattr(z, "terminal_probability") and hasattr(z, "touch_probability") and hasattr(z, "first_passage_probability")
    assert pbm.public_view()["zones"][0]["availability_status"] == "NOT_AVAILABLE_INSUFFICIENT_DISTRIBUTION"
