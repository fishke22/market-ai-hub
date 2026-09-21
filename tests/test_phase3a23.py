"""Phase 3A.2.3 — calibration evidence closure + scope hardening + temporal contract tests。"""
from __future__ import annotations

import sys

import pytest

sys.path.insert(0, "src")


def _dist(**kw):
    from market_ai_hub.research.price_probability_map import DistributionRecord

    base = dict(
        method="EMPIRICAL", capability="TERMINAL_SAMPLES",
        target_family="TAIWAN_STOCK", instrument="X", horizon="1d",
        distribution_id="d1", distribution_version="v1",
        sample_count=100, effective_sample_count=100, minimum_required_sample=50,
        sample_sufficiency_status="SUFFICIENT")
    base.update(kw)
    return DistributionRecord(**base)


def _pv(**kw):
    from market_ai_hub.research.price_probability_map import ProbabilityValue

    base = dict(value=0.61, status="AVAILABLE", calibration_status="CALIBRATED",
                sample_sufficiency_status="SUFFICIENT", sample_count=100,
                effective_sample_count=100, minimum_required_sample=50)
    base.update(kw)
    return ProbabilityValue(**base)


def _prov(**kw):
    from market_ai_hub.research.price_probability_map import ProbabilityProvenance

    base = dict(
        model_id="m", model_version="v1", dataset_version="d1", feature_version="f1",
        protocol_version="p1", distribution_method="EMPIRICAL", calibration_method="isotonic",
        calibration_version="c1", evaluation_window="w", generated_at="t",
        target_family="TAIWAN_STOCK", instrument="X", horizon="1d",
        distribution_id="d1", distribution_version="v1")
    base.update(kw)
    return ProbabilityProvenance(**base)


def _cal_ev(**kw):
    from market_ai_hub.research.price_probability_map import CalibrationEvidence

    base = dict(
        status="CALIBRATED", calibration_domain="PRICE_DISTRIBUTION", probability_type="TERMINAL",
        method="isotonic", method_version="v1", calibration_version="c1",
        model_id="m", model_version="v1", distribution_id="d1", distribution_version="v1",
        dataset_version="d1", protocol_version="p1",
        target_family="TAIWAN_STOCK", instrument="X", horizon="1d", scope="SINGLE_INSTRUMENT",
        fit_window_start="2026-01-01", fit_window_end="2026-06-30",
        evaluation_window_start="2026-07-01", evaluation_window_end="2026-09-21",
        fit_partition_role="CALIBRATION",
        sample_count=100, effective_sample_count=100, minimum_required_sample=50,
        sample_sufficiency_status="SUFFICIENT", evaluated_at="t", source="synthetic")
    base.update(kw)
    return CalibrationEvidence(**base)


def _pbm(*, zones, dist=None, prov=None, family="TAIWAN_STOCK", instrument="X", horizon="1d",
         scope="SINGLE_INSTRUMENT", scope_ev=None, cal="CALIBRATED"):
    from market_ai_hub.research.price_probability_map import ProbabilityMap

    return ProbabilityMap(
        instrument, family, horizon, zones=zones,
        distribution=dist or _dist(),
        calibration_status=cal, calibration_scope=scope, calibration_scope_evidence=scope_ev or {},
        provenance=prov if prov is not None else _prov())


def _terminal_map(cev=_cal_ev(), **pbm_kw):
    from market_ai_hub.research.price_probability_map import ZoneProbability

    return _pbm(zones=[ZoneProbability(zone="BUY_ZONE", terminal=_pv(calibration_evidence=cev))],
                **pbm_kw)


# ── §30：strings-only CALIBRATED must fail ──

def test_30_calibrated_strings_only_blocked():
    # map calibration_status=CALIBRATED, PV CALIBRATED, prov "just-a-string", no CalibrationEvidence
    pv = _pv(calibration_status="CALIBRATED")  # no calibration_evidence
    from market_ai_hub.research.price_probability_map import ZoneProbability

    pbm = _pbm(zones=[ZoneProbability(zone="BUY_ZONE", terminal=pv)],
               prov=_prov(calibration_method="just-a-string", calibration_version="v1"))
    pub = pbm.public_view()["zones"][0]
    assert "terminal_probability" not in pub
    assert "CALIBRATION_EVIDENCE_MISSING" in pub["terminal_reason_codes"]


def test_30_map_calibrated_status_not_authoritative():
    # map calibration_status=CALIBRATED 但無 evidence → 不可公開
    pub = _terminal_map(cev=None).public_view()["zones"][0]
    assert "terminal_probability" not in pub
    assert "CALIBRATION_EVIDENCE_MISSING" in pub["terminal_reason_codes"]


# ── §31/§32：PANEL missing family/horizon ──

def test_31_panel_missing_target_families_blocked():
    pub = _terminal_map(scope="PANEL", scope_ev={
        "universe_id": "u", "universe_version": "1", "members": ["X"],
        "supported_horizons": ["1d"], "calibration_domain": "PRICE_DISTRIBUTION",
        "scope_version": "v1"}).public_view()["zones"][0]
    assert "terminal_probability" not in pub
    assert "CALIBRATION_SCOPE_EVIDENCE_MISSING" in pub["terminal_reason_codes"]


def test_32_panel_missing_supported_horizons_blocked():
    pub = _terminal_map(scope="PANEL", scope_ev={
        "universe_id": "u", "universe_version": "1", "members": ["X"],
        "target_families": ["TAIWAN_STOCK"], "calibration_domain": "PRICE_DISTRIBUTION",
        "scope_version": "v1"}).public_view()["zones"][0]
    assert "terminal_probability" not in pub
    assert "CALIBRATION_SCOPE_EVIDENCE_MISSING" in pub["terminal_reason_codes"]


# ── §33：wrong calibration type ──

def test_33_terminal_using_touch_evidence_blocked():
    pub = _terminal_map(cev=_cal_ev(probability_type="TOUCH")).public_view()["zones"][0]
    assert "terminal_probability" not in pub
    assert "CALIBRATION_TYPE_MISMATCH" in pub["terminal_reason_codes"]


# ── §34：wrong distribution id ──

def test_34_calibration_distribution_id_mismatch_blocked():
    pub = _terminal_map(cev=_cal_ev(distribution_id="D2", distribution_version="v2")).public_view()["zones"][0]
    assert "terminal_probability" not in pub
    assert "CALIBRATION_DISTRIBUTION_MISMATCH" in pub["terminal_reason_codes"]


def test_12_calibration_model_mismatch_blocked():
    pub = _terminal_map(cev=_cal_ev(model_id="other")).public_view()["zones"][0]
    assert "terminal_probability" not in pub
    assert "CALIBRATION_MODEL_MISMATCH" in pub["terminal_reason_codes"]


# ── §35：wrong horizon ──

def test_35_calibration_horizon_mismatch_blocked():
    pub = _terminal_map(cev=_cal_ev(horizon="5d")).public_view()["zones"][0]
    assert "terminal_probability" not in pub
    assert "CALIBRATION_HORIZON_SCOPE_MISMATCH" in pub["terminal_reason_codes"]


# ── §36：zero calibration sample ──

def test_36_zero_calibration_sample_blocked():
    cev = _cal_ev(sample_count=0, effective_sample_count=0, minimum_required_sample=0)
    pub = _terminal_map(cev=cev).public_view()["zones"][0]
    assert "terminal_probability" not in pub
    assert "CALIBRATION_INSUFFICIENT_SAMPLE" in pub["terminal_reason_codes"]


# ── §37：temporal leakage ──

def test_37_calibration_temporal_leakage_blocked():
    cev = _cal_ev(fit_window_start="2026-01-01", fit_window_end="2026-09-01",
                  evaluation_window_start="2026-08-01", evaluation_window_end="2026-09-21")
    pub = _terminal_map(cev=cev).public_view()["zones"][0]
    assert "terminal_probability" not in pub
    assert "CALIBRATION_TEMPORAL_LEAKAGE" in pub["terminal_reason_codes"]


# ── §19：FINAL_OOS fit partition blocked ──

def test_19_final_oos_fit_partition_blocked():
    cev = _cal_ev(fit_partition_role="FINAL_OOS")
    pub = _terminal_map(cev=cev).public_view()["zones"][0]
    assert "terminal_probability" not in pub
    assert "CALIBRATION_PARTITION_VIOLATION" in pub["terminal_reason_codes"]


# ── §7：only CALIBRATED status passes ──

def test_7_non_calibrated_evidence_status_blocked():
    pub = _terminal_map(cev=_cal_ev(status="FITTED_NOT_EVALUATED")).public_view()["zones"][0]
    assert "terminal_probability" not in pub
    assert "CALIBRATION_NOT_CALIBRATED" in pub["terminal_reason_codes"]


# ── §38：positive synthetic contract test ──

def test_38_positive_synthetic_contract_passes():
    # SYNTHETIC_CONTRACT_TEST_ONLY — 非真實市場 evidence
    pub = _terminal_map().public_view()["zones"][0]
    assert pub.get("terminal_probability") == 0.61
    assert pub["terminal_status"] == "AVAILABLE"


# ── §9：type-specific independence（terminal ≠ touch）──

def test_9_terminal_evidence_does_not_vouch_for_touch():
    from market_ai_hub.research.price_probability_map import DistributionRecord, ZoneProbability

    # terminal 有 CALIBRATED evidence，touch 沒有 → touch 不得公開
    dist = _dist(capability="PATH_SAMPLES", method="EMPIRICAL",
                 instrument_role="DIRECT", forecast_scope="DIRECT_INSTRUMENT",
                 target_market_calendar="XTAI", session_semantics="day",
                 path_count=1000, steps_per_path=5, bar_frequency="1d",
                 generation_method="block_bootstrap")
    z = ZoneProbability(
        zone="BUY_ZONE",
        terminal=_pv(calibration_evidence=_cal_ev(probability_type="TERMINAL")),
        touch=_pv(),  # no calibration evidence
    )
    from market_ai_hub.research.price_probability_map import ProbabilityMap

    pbm = ProbabilityMap("X", "TAIWAN_STOCK", "1d", zones=[z], distribution=dist,
                         calibration_status="CALIBRATED", provenance=_prov())
    pub = pbm.public_view()["zones"][0]
    assert "touch_probability" not in pub
    assert "CALIBRATION_EVIDENCE_MISSING" in pub["touch_reason_codes"]


# ── §24/§25：map-level derived calibration summary ──

def test_24_map_calibration_summary_derived():
    from market_ai_hub.research.price_probability_map import ZoneProbability

    # no evidence at all
    pbm = _pbm(zones=[ZoneProbability(zone="BUY_ZONE", terminal=_pv())])
    assert pbm.derived_calibration_summary() == "NONE_CALIBRATED"
    assert pbm.public_view()["calibration_summary"] == "NONE_CALIBRATED"


def test_25_mixed_calibration_summary_not_fully_calibrated():
    from market_ai_hub.research.price_probability_map import ZoneProbability

    z = ZoneProbability(zone="BUY_ZONE", terminal=_pv(calibration_evidence=_cal_ev(probability_type="TERMINAL")))
    pbm = _pbm(zones=[z])
    assert pbm.derived_calibration_summary() == "CALIBRATED_FOR_TERMINAL_ONLY"


# ── §29：current runtime truth still no public probability ──

@pytest.mark.parametrize("family,instrument", [
    ("TAIWAN_STOCK", "3706.TW"), ("TAIWAN_STOCK", "2330.TW"),
    ("TAIWAN_INDEX", "TAIEX"), ("OSAKA_MICRO", "JNU"),
])
def test_29_current_runtime_no_public_probability(family, instrument):
    from market_ai_hub.research.price_probability_map import empty_price_map

    pm = empty_price_map(instrument, family, "1d", 100.0)
    assert pm.probability_map is None


# ── §40：version ──

def test_40_version_3a23():
    from market_ai_hub.research.price_probability_map import PRICE_PROBABILITY_MAP_VERSION

    assert PRICE_PROBABILITY_MAP_VERSION == "3A.2.3"
