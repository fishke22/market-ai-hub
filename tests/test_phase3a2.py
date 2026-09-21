"""Phase 3A.2 — typed evidence contract + calibration safety + distribution schema consistency tests。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, "src")
ROOT = Path(__file__).resolve().parents[1]


def _prov():
    from market_ai_hub.research.price_probability_map import ProbabilityProvenance

    return ProbabilityProvenance(
        model_id="m", model_version="v1", dataset_version="d1", feature_version="f1",
        protocol_version="p1", distribution_method="EMPIRICAL", calibration_method="isotonic",
        calibration_version="c1", evaluation_window="w", generated_at="t",
        target_family="TAIWAN_STOCK", instrument="X", horizon="1d",
        distribution_id="d1", distribution_version="v1")


# ── §1/§35：enum consistency ──

def test_distribution_methods_include_runtime_values():
    from market_ai_hub.research.price_probability_map import DISTRIBUTION_METHODS

    for v in ("NOT_ESTABLISHED", "QUANTILES_ONLY", "EMPIRICAL", "MODEL_DISTRIBUTION", "GAUSSIAN_BASELINE_DIAGNOSTIC"):
        assert v in DISTRIBUTION_METHODS


def test_capability_matrix_complete():
    from market_ai_hub.research.price_probability_map import CAPABILITY_MATRIX, DISTRIBUTION_CAPABILITIES

    for cap in DISTRIBUTION_CAPABILITIES:
        assert cap in CAPABILITY_MATRIX
        assert set(CAPABILITY_MATRIX[cap]) == {"terminal", "touch", "first_passage"}


# ── §3/§21：capability gates ──

def test_terminal_samples_cannot_produce_touch():
    from market_ai_hub.research.price_probability_map import capability_supports

    assert capability_supports("TERMINAL_SAMPLES", "terminal") is True
    assert capability_supports("TERMINAL_SAMPLES", "touch") is False
    assert capability_supports("TERMINAL_SAMPLES", "first_passage") is False


def test_path_samples_support_all():
    from market_ai_hub.research.price_probability_map import capability_supports

    for t in ("terminal", "touch", "first_passage"):
        assert capability_supports("PATH_SAMPLES", t) is True


def test_quantiles_only_supports_nothing():
    from market_ai_hub.research.price_probability_map import capability_supports

    for t in ("terminal", "touch", "first_passage"):
        assert capability_supports("QUANTILES_ONLY", t) is False


# ── §31：map calibrated but zone uncalibrated → no % ──

def test_map_calibrated_zone_uncalibrated_no_percent():
    from market_ai_hub.research.price_probability_map import (
        DistributionRecord, ProbabilityMap, ProbabilityValue, ZoneProbability)

    pbm = ProbabilityMap("X", "TAIWAN_STOCK", "1d",
                         zones=[ZoneProbability(zone="BUY_ZONE", terminal=ProbabilityValue(
                             value=0.61, status="AVAILABLE", calibration_status="UNCALIBRATED",
                             sample_sufficiency_status="SUFFICIENT"))],
                         calibration_status="CALIBRATED",
                         distribution=DistributionRecord(capability="TERMINAL_SAMPLES", method="EMPIRICAL"),
                         provenance=_prov())
    pub = pbm.public_view()
    assert "terminal_probability" not in pub["zones"][0]
    assert "61" not in str(pub)


# ── §32：mixed probability types ──

def test_mixed_probability_types_only_calibrated_output():
    from market_ai_hub.research.price_probability_map import (
        DistributionRecord, ProbabilityMap, ProbabilityValue, ZoneProbability)

    z = ZoneProbability(
        zone="BUY_ZONE",
        terminal=ProbabilityValue(value=0.61, status="AVAILABLE", calibration_status="CALIBRATED",
                                  sample_sufficiency_status="SUFFICIENT", sample_count=100,
                                  effective_sample_count=100, minimum_required_sample=50),
        touch=ProbabilityValue(value=0.8, status="AVAILABLE", calibration_status="UNCALIBRATED",
                               sample_sufficiency_status="SUFFICIENT", sample_count=100,
                               effective_sample_count=100, minimum_required_sample=50),
        first_passage=ProbabilityValue(value=0.3, status="NOT_APPLICABLE",
                                       calibration_status="INSUFFICIENT_EVIDENCE"),
    )
    pbm = ProbabilityMap("X", "TAIWAN_STOCK", "1d", zones=[z], calibration_status="CALIBRATED",
                         distribution=DistributionRecord(
                             method="EMPIRICAL", capability="TERMINAL_SAMPLES",
                             target_family="TAIWAN_STOCK", instrument="X", horizon="1d",
                             distribution_id="d1", distribution_version="v1",
                             sample_count=100, effective_sample_count=100,
                             minimum_required_sample=50, sample_sufficiency_status="SUFFICIENT"),
                         provenance=_prov())
    pub = pbm.public_view()["zones"][0]
    assert pub.get("terminal_probability") == 0.61
    assert "touch_probability" not in pub
    assert "first_passage_probability" not in pub


# ── §33：invalid values fail closed ──

@pytest.mark.parametrize("bad", [-0.2, 1.1, float("nan"), float("inf"), -float("inf")])
def test_invalid_probability_values_fail_closed(bad):
    from market_ai_hub.research.price_probability_map import (
        DistributionRecord, ProbabilityMap, ProbabilityValue, ZoneProbability)

    pbm = ProbabilityMap("X", "TAIWAN_STOCK", "1d",
                         zones=[ZoneProbability(zone="BUY_ZONE", terminal=ProbabilityValue(
                             value=bad, status="AVAILABLE", calibration_status="CALIBRATED",
                             sample_sufficiency_status="SUFFICIENT"))],
                         calibration_status="CALIBRATED",
                         distribution=DistributionRecord(capability="TERMINAL_SAMPLES", method="EMPIRICAL"),
                         provenance=_prov())
    assert "terminal_probability" not in pbm.public_view()["zones"][0]


# ── §34：EVALUATED requires evidence ──

def test_evaluated_requires_evidence():
    from market_ai_hub.research.price_probability_map import EvaluationEvidence, six_state_research_view

    pm = six_state_research_view("TAIWAN_STOCK", "3706.TW", "1d", 79.8,
                                 market_state="BUY_ZONE", regime="BULL_TREND",
                                 model_failure_state="NORMAL")
    assert pm.market_state_status == "UNVERIFIED"
    assert pm.regime_status == "UNVERIFIED"
    assert pm.model_failure_evaluation_status == "UNVERIFIED"
    assert pm.strategy_candidate == "NONE"


def test_invalid_evidence_not_evaluated():
    from market_ai_hub.research.price_probability_map import EvaluationEvidence, six_state_research_view

    bad = EvaluationEvidence(status="NOT_EVALUATED", method="", sample_count=0)
    pm = six_state_research_view("TAIWAN_STOCK", "3706.TW", "1d", 79.8,
                                 market_state="BUY_ZONE", market_state_evidence=bad)
    assert pm.market_state_status == "UNVERIFIED"


# ── §17：quantile boundary != zone probability ──

def test_quantile_boundary_not_zone_probability():
    from market_ai_hub.research.price_probability_map import ZonePolicy, probability_from_quantiles_only

    zp = ZonePolicy(buy_zone_upper_quantile=0.25)
    assert zp.buy_zone_upper_quantile == 0.25
    # zone probability 不得因 boundary=0.25 而變成 25%
    pbm = probability_from_quantiles_only(["BUY_ZONE"])
    assert pbm.zones[0].terminal.value is None
    assert "0.25" not in str(pbm.public_view())


# ── §18：QUANTILES_ONLY record ──

def test_quantiles_only_record():
    from market_ai_hub.research.price_probability_map import quantiles_only_distribution

    d = quantiles_only_distribution("TAIWAN_STOCK", "X", "1d")
    assert d.method == "QUANTILES_ONLY"
    assert d.capability == "QUANTILES_ONLY"
    assert d.is_full_distribution is False


# ── §23：calibration domain ──

def test_calibration_domain_separated():
    from market_ai_hub.research.price_probability_map import CALIBRATION_DOMAINS, ProbabilityValue

    assert "PRICE_DISTRIBUTION" in CALIBRATION_DOMAINS
    assert "DIRECTION_CLASSIFICATION" in CALIBRATION_DOMAINS
    assert ProbabilityValue().calibration_domain == "PRICE_DISTRIBUTION"


# ── §28：current public probability honest ──

def test_current_public_probability_not_available():
    from market_ai_hub.research.price_probability_map import probability_from_quantiles_only

    pub = probability_from_quantiles_only(["BUY_ZONE", "PROFIT_ZONE"], "X", "TAIWAN_STOCK", "1d").public_view()
    for z in pub["zones"]:
        assert "terminal_probability" not in z
        assert z["terminal_status"].startswith("NOT_AVAILABLE")
        assert "QUANTILES_ONLY" in z["terminal_reason_codes"]


# ── §22：calibration metrics interface (not fitted) ──

def test_calibration_metrics_interface_only():
    from market_ai_hub.research.price_probability_map import calibration_metrics_contract

    c = calibration_metrics_contract()
    assert c["status"] == "INTERFACE_ONLY_NOT_FITTED"
    assert "coverage_calibration" in c["metrics"]


# ── §37：version bump ──

def test_version_bumped():
    from market_ai_hub.research.price_probability_map import PRICE_PROBABILITY_MAP_VERSION

    assert PRICE_PROBABILITY_MAP_VERSION == "3A.2.2"
