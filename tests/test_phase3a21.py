"""Phase 3A.2.1 — adversarial probability contract closure tests。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, "src")
ROOT = Path(__file__).resolve().parents[1]


def _prov(family="TAIWAN_STOCK", instrument="X", horizon="1d", method="EMPIRICAL",
          cal_method="isotonic", cal_version="c1"):
    from market_ai_hub.research.price_probability_map import ProbabilityProvenance

    return ProbabilityProvenance(
        model_id="m", model_version="v1", dataset_version="d1", feature_version="f1",
        protocol_version="p1", distribution_method=method, calibration_method=cal_method,
        calibration_version=cal_version, evaluation_window="w", generated_at="t",
        target_family=family, instrument=instrument, horizon=horizon,
        distribution_id="d1", distribution_version="v1")


def _pv(**kw):
    from market_ai_hub.research.price_probability_map import ProbabilityValue

    base = dict(value=0.61, status="AVAILABLE", calibration_status="CALIBRATED",
                sample_sufficiency_status="SUFFICIENT", sample_count=100,
                effective_sample_count=100, minimum_required_sample=50)
    base.update(kw)
    return ProbabilityValue(**base)


def _pbm(*, zones=None, dist=None, cal="CALIBRATED", prov=None, scope="SINGLE_INSTRUMENT",
         scope_ev=None, family="TAIWAN_STOCK", instrument="X", horizon="1d"):
    from market_ai_hub.research.price_probability_map import (
        DistributionRecord, ProbabilityMap, ZoneProbability)

    if dist is None:
        dist = DistributionRecord(
            method="EMPIRICAL", capability="TERMINAL_SAMPLES",
            target_family=family, instrument=instrument, horizon=horizon,
            distribution_id="d1", distribution_version="v1",
            sample_count=100, effective_sample_count=100, minimum_required_sample=50,
            sample_sufficiency_status="SUFFICIENT")
    return ProbabilityMap(
        instrument, family, horizon,
        zones=zones or [ZoneProbability(zone="BUY_ZONE", terminal=_pv())],
        distribution=dist,
        calibration_status=cal, calibration_scope=scope, calibration_scope_evidence=scope_ev or {},
        provenance=prov if prov is not None else _prov(family, instrument, horizon),
    )


# ── §25：scope mismatch ──

def test_adversarial_scope_mismatch_blocked():
    pbm = _pbm(prov=_prov("OTHER", "OTHER", "5d"))
    pub = pbm.public_view()["zones"][0]
    assert "terminal_probability" not in pub
    assert pub["terminal_status"] == "NOT_AVAILABLE_SCOPE_MISMATCH"
    assert any(r in pub["terminal_reason_codes"] for r in
               ("TARGET_SCOPE_MISMATCH", "INSTRUMENT_SCOPE_MISMATCH", "HORIZON_SCOPE_MISMATCH"))


def test_horizon_normalization_matches():
    # 1D == 1d
    pbm = _pbm(horizon="1D", prov=_prov("TAIWAN_STOCK", "X", "1d"))
    assert "terminal_probability" in pbm.public_view()["zones"][0]


def test_instrument_normalization_matches():
    # 3706 == 3706.TW
    pbm = _pbm(instrument="3706", prov=_prov("TAIWAN_STOCK", "3706.TW", "1d"))
    assert "terminal_probability" in pbm.public_view()["zones"][0]


# ── §26：zero sample fake sufficient ──

def test_adversarial_zero_sample_fake_sufficient():
    pv = _pv(sample_count=0, effective_sample_count=0, minimum_required_sample=0,
             sample_sufficiency_status="SUFFICIENT")
    pbm = _pbm(zones=[__import__("market_ai_hub.research.price_probability_map", fromlist=["ZoneProbability"]).ZoneProbability(zone="BUY_ZONE", terminal=pv)])
    pub = pbm.public_view()["zones"][0]
    assert "terminal_probability" not in pub
    assert "INSUFFICIENT_SAMPLE" in pub["terminal_reason_codes"]


# ── §27：AVAILABLE + UNCALIBRATED ──

def test_adversarial_available_but_uncalibrated():
    pv = _pv(calibration_status="UNCALIBRATED")
    from market_ai_hub.research.price_probability_map import ZoneProbability

    pbm = _pbm(zones=[ZoneProbability(zone="BUY_ZONE", terminal=pv)])
    pub = pbm.public_view()["zones"][0]
    assert pub["terminal_status"] != "AVAILABLE"
    assert "terminal_probability" not in pub
    assert "UNCALIBRATED" in pub["terminal_reason_codes"]


# ── §28：invalid enum ──

def test_adversarial_invalid_evaluation_enum_normalized():
    from market_ai_hub.research.price_probability_map import EvaluationEvidence

    # VALID → normalize EVALUATED（backward compat）
    ev = EvaluationEvidence(status="VALID")
    assert ev.status == "EVALUATED"
    assert "VALID" not in __import__("market_ai_hub.research.price_probability_map",
                                     fromlist=["EVALUATION_STATUSES"]).EVALUATION_STATUSES


def test_adversarial_unknown_evaluation_enum_rejected():
    from market_ai_hub.research.price_probability_map import EvaluationEvidence

    with pytest.raises(ValueError):
        EvaluationEvidence(status="TOTALLY_MADE_UP")


def test_evaluation_evidence_completeness():
    from market_ai_hub.research.price_probability_map import EvaluationEvidence

    # status EVALUATED 但缺 method_version/data_version/evaluated_at/source → not valid
    assert EvaluationEvidence(status="EVALUATED", method="m", sample_count=1).is_valid() is False
    assert EvaluationEvidence(status="EVALUATED", method="m", method_version="v", data_version="d",
                              sample_count=1, evaluated_at="t", source="s").is_valid() is True


# ── §29：method/capability mismatch ──

def test_adversarial_method_capability_mismatch_rejected():
    from market_ai_hub.research.price_probability_map import DistributionRecord

    with pytest.raises(ValueError):
        DistributionRecord(method="QUANTILES_ONLY", capability="PATH_SAMPLES")


def test_gaussian_not_public_calibrated_source():
    from market_ai_hub.research.price_probability_map import METHOD_CAPABILITY_RULES

    assert METHOD_CAPABILITY_RULES["GAUSSIAN_BASELINE_DIAGNOSTIC"] == {"NONE", "QUANTILES_ONLY"}


# ── §30/§31：path capability ──

def test_terminal_distribution_cannot_produce_touch():
    from market_ai_hub.research.price_probability_map import capability_supports

    assert capability_supports("TERMINAL_DISTRIBUTION", "terminal") is True
    assert capability_supports("TERMINAL_DISTRIBUTION", "touch") is False
    assert capability_supports("TERMINAL_DISTRIBUTION", "first_passage") is False


def test_full_distribution_not_path_capability():
    from market_ai_hub.research.price_probability_map import CAPABILITY_MATRIX

    # §16：FULL_DISTRIBUTION 不得自行代表 path
    assert CAPABILITY_MATRIX["FULL_DISTRIBUTION"]["touch"] is False
    assert CAPABILITY_MATRIX["FULL_DISTRIBUTION"]["first_passage"] is False


def test_path_metadata_missing_blocks_touch():
    from market_ai_hub.research.price_probability_map import DistributionRecord, ZoneProbability

    # Taiwan semantics correct，但缺 path metadata
    dist = DistributionRecord(
        method="EMPIRICAL", capability="PATH_SAMPLES",
        target_family="TAIWAN_STOCK", instrument="X", horizon="1d",
        instrument_role="DIRECT", forecast_scope="DIRECT_INSTRUMENT",
        target_market_calendar="XTAI", session_semantics="day",
        distribution_id="d1", distribution_version="v1",
        sample_count=1000, effective_sample_count=1000, minimum_required_sample=100,
        sample_sufficiency_status="SUFFICIENT")
    pbm = _pbm(dist=dist, zones=[ZoneProbability(zone="BUY_ZONE", touch=_pv())])
    pub = pbm.public_view()["zones"][0]
    assert "touch_probability" not in pub
    assert "PATH_METADATA_MISSING" in pub["touch_reason_codes"]


def test_path_metadata_present_allows_touch():
    from market_ai_hub.research.price_probability_map import DistributionRecord, ZoneProbability

    # §9/§26：正確 Taiwan path = XTAI / day（不得用 OSE_DERIVATIVES）
    dist = DistributionRecord(
        method="EMPIRICAL", capability="PATH_SAMPLES", path_count=1000,
        steps_per_path=5, bar_frequency="1d", generation_method="block_bootstrap",
        target_family="TAIWAN_STOCK", instrument="X", horizon="1d",
        instrument_role="DIRECT", forecast_scope="DIRECT_INSTRUMENT",
        target_market_calendar="XTAI", session_semantics="day",
        distribution_id="d1", distribution_version="v1",
        sample_count=1000, effective_sample_count=1000, minimum_required_sample=100,
        sample_sufficiency_status="SUFFICIENT")
    pbm = _pbm(dist=dist, zones=[ZoneProbability(zone="BUY_ZONE", touch=_pv())])
    assert pbm.public_view()["zones"][0].get("touch_probability") == 0.61


# ── §20：provenance distribution method consistency ──

def test_provenance_method_mismatch_blocked():
    pbm = _pbm(prov=_prov(method="MODEL_DISTRIBUTION"))  # dist method EMPIRICAL
    pub = pbm.public_view()["zones"][0]
    assert "terminal_probability" not in pub
    assert "DISTRIBUTION_METHOD_MISMATCH" in pub["terminal_reason_codes"]


# ── §21：calibration provenance ──

def test_calibration_provenance_missing_blocked():
    pbm = _pbm(prov=_prov(cal_method="", cal_version=""))
    pub = pbm.public_view()["zones"][0]
    assert "terminal_probability" not in pub
    assert "CALIBRATION_PROVENANCE_MISSING" in pub["terminal_reason_codes"]


# ── §3/§22：calibration scope enforcement ──

def test_panel_scope_requires_universe():
    pbm = _pbm(scope="PANEL", scope_ev={})  # no universe
    assert "terminal_probability" not in pbm.public_view()["zones"][0]


def test_panel_scope_member_mismatch_blocked():
    pbm = _pbm(scope="PANEL", scope_ev={"universe_id": "u1", "universe_version": "v1", "members": ["OTHER"]})
    assert "terminal_probability" not in pbm.public_view()["zones"][0]


def test_global_scope_requires_definition():
    pbm = _pbm(scope="GLOBAL", scope_ev={})
    assert "terminal_probability" not in pbm.public_view()["zones"][0]


# ── §8：public status derived ──

def test_public_status_derived_not_echoed():
    from market_ai_hub.research.price_probability_map import ZoneProbability

    pv = _pv(calibration_status="UNCALIBRATED")
    pbm = _pbm(zones=[ZoneProbability(zone="BUY_ZONE", terminal=pv)])
    pub = pbm.public_view()["zones"][0]
    # internal status = AVAILABLE 但 public 不得 echo
    assert pv.status == "AVAILABLE"
    assert pub["terminal_status"] != "AVAILABLE"
    assert pub["terminal_status"] == "NOT_AVAILABLE_UNCALIBRATED"


# ── §33：current probability all unavailable ──

def test_current_all_probabilities_unavailable():
    from market_ai_hub.research.price_probability_map import probability_from_quantiles_only

    pub = probability_from_quantiles_only(["BUY_ZONE", "PROFIT_ZONE"], "X", "TAIWAN_STOCK", "1d").public_view()
    for z in pub["zones"]:
        for t in ("terminal", "touch", "first_passage"):
            assert f"{t}_probability" not in z
            assert z[f"{t}_status"].startswith("NOT_AVAILABLE")


# ── §35：version ──

def test_version_3a21():
    from market_ai_hub.research.price_probability_map import PRICE_PROBABILITY_MAP_VERSION

    assert PRICE_PROBABILITY_MAP_VERSION == "3A.2.2"


# ── §32：existing invariants ──

def test_existing_invariants_preserved():
    from market_ai_hub.research.price_probability_map import empty_price_map

    pm = empty_price_map("X", "OSAKA_MICRO", "1d", 1.0)
    assert pm.state_is_trade_instruction is False
    assert pm.actionability_status == "NOT_VALIDATED"
    assert pm.market_state is None and pm.market_state_status == "NOT_EVALUATED"
