"""Phase 3A.2.2 — distribution evidence closure + scope + market semantics tests。"""
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


def _path_dist(**kw):
    from market_ai_hub.research.price_probability_map import DistributionRecord

    base = dict(
        method="EMPIRICAL", capability="PATH_SAMPLES",
        target_family="TAIWAN_STOCK", instrument="X", horizon="1d",
        instrument_role="DIRECT", forecast_scope="DIRECT_INSTRUMENT",
        target_market_calendar="XTAI", session_semantics="day",
        path_count=1000, steps_per_path=5, bar_frequency="1d", generation_method="block_bootstrap",
        distribution_id="d1", distribution_version="v1",
        sample_count=1000, effective_sample_count=1000, minimum_required_sample=100,
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


def _cal_ev(ptype="TERMINAL", family="TAIWAN_STOCK", instrument="X", horizon="1d"):
    from market_ai_hub.research.price_probability_map import CalibrationEvidence

    return CalibrationEvidence(
        status="CALIBRATED", calibration_domain="PRICE_DISTRIBUTION", probability_type=ptype,
        method="isotonic", method_version="v1", calibration_version="c1",
        model_id="m", model_version="v1", distribution_id="d1", distribution_version="v1",
        dataset_version="d1", protocol_version="p1",
        target_family=family, instrument=instrument, horizon=horizon, scope="SINGLE_INSTRUMENT",
        fit_window_start="2026-01-01", fit_window_end="2026-06-30",
        evaluation_window_start="2026-07-01", evaluation_window_end="2026-09-21",
        fit_partition_role="CALIBRATION",
        sample_count=100, effective_sample_count=100, minimum_required_sample=50,
        sample_sufficiency_status="SUFFICIENT", evaluated_at="t", source="synthetic")


def _prov(family="TAIWAN_STOCK", instrument="X", horizon="1d", did="d1", dver="v1"):
    from market_ai_hub.research.price_probability_map import ProbabilityProvenance

    return ProbabilityProvenance(
        model_id="m", model_version="v1", dataset_version="d1", feature_version="f1",
        protocol_version="p1", distribution_method="EMPIRICAL", calibration_method="isotonic",
        calibration_version="c1", evaluation_window="w", generated_at="t",
        target_family=family, instrument=instrument, horizon=horizon,
        distribution_id=did, distribution_version=dver)


def _pbm(*, zones, dist, family="TAIWAN_STOCK", instrument="X", horizon="1d",
         prov=None, cal="CALIBRATED", scope="SINGLE_INSTRUMENT", scope_ev=None):
    from market_ai_hub.research.price_probability_map import ProbabilityMap

    return ProbabilityMap(
        instrument, family, horizon, zones=zones, distribution=dist,
        calibration_status=cal, calibration_scope=scope, calibration_scope_evidence=scope_ev or {},
        provenance=prov if prov is not None else _prov(family, instrument, horizon))


def _touch_map(dist, *, family="TAIWAN_STOCK", instrument="X", horizon="1d"):
    from market_ai_hub.research.price_probability_map import ZoneProbability

    touch = _pv(calibration_evidence=_cal_ev("TOUCH", family, instrument, horizon))
    return _pbm(zones=[ZoneProbability(zone="BUY_ZONE", touch=touch)], dist=dist,
                family=family, instrument=instrument, horizon=horizon)


# ── §23：Taiwan map + Osaka distribution（verified HIGH defect）──

def test_23_taiwan_map_osaka_distribution_blocked():
    dist = _path_dist(target_family="OSAKA_MICRO", instrument="JNU", horizon="5d",
                      instrument_role="DIRECT", forecast_scope="DIRECT_INSTRUMENT",
                      target_market_calendar="OSE_DERIVATIVES", session_semantics="day+night")
    pub = _touch_map(dist).public_view()["zones"][0]
    assert "touch_probability" not in pub
    assert any(r.startswith("DISTRIBUTION_") for r in pub["touch_reason_codes"])


# ── §24：zero distribution sample（verified HIGH defect）──

def test_24_zero_distribution_sample_blocked():
    from market_ai_hub.research.price_probability_map import ZoneProbability

    dist = _dist(sample_count=0, effective_sample_count=0, minimum_required_sample=0,
                 sample_sufficiency_status="NOT_EVALUATED")
    pbm = _pbm(zones=[ZoneProbability(zone="BUY_ZONE", terminal=_pv())], dist=dist)
    pub = pbm.public_view()["zones"][0]
    assert "terminal_probability" not in pub
    assert "DISTRIBUTION_INSUFFICIENT_SAMPLE" in pub["terminal_reason_codes"]


# ── §25：probability sample > distribution sample ──

def test_25_probability_sample_exceeds_source_blocked():
    from market_ai_hub.research.price_probability_map import ZoneProbability

    dist = _dist(sample_count=80, effective_sample_count=70, minimum_required_sample=50)
    pv = _pv(sample_count=100, effective_sample_count=90, minimum_required_sample=50)
    pbm = _pbm(zones=[ZoneProbability(zone="BUY_ZONE", terminal=pv)], dist=dist)
    pub = pbm.public_view()["zones"][0]
    assert "terminal_probability" not in pub
    assert "PROBABILITY_SAMPLE_EXCEEDS_SOURCE" in pub["terminal_reason_codes"]


# ── §26：correct Taiwan path may pass ──

def test_26_correct_taiwan_path_passes():
    pub = _touch_map(_path_dist()).public_view()["zones"][0]
    assert pub.get("touch_probability") == 0.61


# ── §27：wrong Taiwan OSE path fails closed ──

def test_27_taiwan_with_ose_calendar_blocked():
    dist = _path_dist(target_market_calendar="OSE_DERIVATIVES", session_semantics="day+night")
    pub = _touch_map(dist).public_view()["zones"][0]
    assert "touch_probability" not in pub
    assert "MARKET_CALENDAR_MISMATCH" in pub["touch_reason_codes"]


# ── §28：correct Osaka direct may pass ──

def test_28_correct_osaka_direct_passes():
    dist = _path_dist(target_family="OSAKA_MICRO", instrument="JNU", horizon="1d",
                      instrument_role="DIRECT", forecast_scope="DIRECT_INSTRUMENT",
                      target_market_calendar="OSE_DERIVATIVES", session_semantics="day+night")
    pub = _touch_map(dist, family="OSAKA_MICRO", instrument="JNU").public_view()["zones"][0]
    assert pub.get("touch_probability") == 0.61


# ── §29：correct Osaka proxy may pass（^N225 / XTKS）──

def test_29_correct_osaka_proxy_passes():
    dist = _path_dist(target_family="OSAKA_MICRO", instrument="^N225", horizon="1d",
                      instrument_role="PROXY", forecast_scope="PROXY_MODEL_REFERENCE",
                      target_market_calendar="XTKS", session_semantics="day")
    pub = _touch_map(dist, family="OSAKA_MICRO", instrument="^N225").public_view()["zones"][0]
    assert pub.get("touch_probability") == 0.61


# ── §30：wrong Osaka direct XTKS fails closed ──

def test_30_osaka_direct_with_xtks_blocked():
    dist = _path_dist(target_family="OSAKA_MICRO", instrument="JNU", horizon="1d",
                      instrument_role="DIRECT", forecast_scope="DIRECT_INSTRUMENT",
                      target_market_calendar="XTKS", session_semantics="day")
    pub = _touch_map(dist, family="OSAKA_MICRO", instrument="JNU").public_view()["zones"][0]
    assert "touch_probability" not in pub
    assert "MARKET_CALENDAR_MISMATCH" in pub["touch_reason_codes"]


def test_proxy_wrong_forecast_scope_blocked():
    dist = _path_dist(target_family="OSAKA_MICRO", instrument="^N225", horizon="1d",
                      instrument_role="PROXY", forecast_scope="DIRECT_INSTRUMENT",
                      target_market_calendar="XTKS", session_semantics="day")
    pbm = _pbm(zones=[__import__("market_ai_hub.research.price_probability_map",
                                 fromlist=["ZoneProbability"]).ZoneProbability(
        zone="BUY_ZONE", touch=_pv())],
        dist=dist, family="OSAKA_MICRO", instrument="^N225",
        prov=_prov("OSAKA_MICRO", "^N225", "1d"))
    pub = pbm.public_view()["zones"][0]
    assert "touch_probability" not in pub
    assert "FORECAST_SCOPE_MISMATCH" in pub["touch_reason_codes"]


# ── §3：distribution scope cannot be empty ──

def test_3_missing_distribution_scope_blocked():
    from market_ai_hub.research.price_probability_map import ZoneProbability

    dist = _dist(target_family="", instrument="", horizon="")
    pbm = _pbm(zones=[ZoneProbability(zone="BUY_ZONE", terminal=_pv())], dist=dist)
    pub = pbm.public_view()["zones"][0]
    assert "terminal_probability" not in pub
    assert "MISSING_DISTRIBUTION_SCOPE" in pub["terminal_reason_codes"]


# ── §8：distribution sample status validation ──

def test_8_invalid_distribution_sample_status_rejected():
    with pytest.raises(ValueError):
        _dist(sample_sufficiency_status="TOTALLY_ENOUGH")


def test_8_sufficient_string_without_numbers_fails_closed():
    from market_ai_hub.research.price_probability_map import ZoneProbability

    dist = _dist(sample_count=0, effective_sample_count=0, minimum_required_sample=0,
                 sample_sufficiency_status="SUFFICIENT")
    pbm = _pbm(zones=[ZoneProbability(zone="BUY_ZONE", terminal=_pv())], dist=dist)
    assert "terminal_probability" not in pbm.public_view()["zones"][0]


# ── §16：distribution scope == provenance scope ──

def test_16_distribution_scope_must_match_provenance():
    from market_ai_hub.research.price_probability_map import ZoneProbability

    dist = _dist(instrument="Y")  # map/prov = X
    pbm = _pbm(zones=[ZoneProbability(zone="BUY_ZONE", terminal=_pv())], dist=dist)
    pub = pbm.public_view()["zones"][0]
    assert "terminal_probability" not in pub
    assert "DISTRIBUTION_INSTRUMENT_SCOPE_MISMATCH" in pub["terminal_reason_codes"]


# ── §17：distribution identity traceability ──

def test_17_distribution_identity_mismatch_blocked():
    from market_ai_hub.research.price_probability_map import ZoneProbability

    dist = _dist(distribution_id="other")
    pbm = _pbm(zones=[ZoneProbability(zone="BUY_ZONE", terminal=_pv())], dist=dist)
    pub = pbm.public_view()["zones"][0]
    assert "terminal_probability" not in pub
    assert "DISTRIBUTION_IDENTITY_MISMATCH" in pub["terminal_reason_codes"]


def test_17_missing_distribution_identity_blocked():
    from market_ai_hub.research.price_probability_map import ZoneProbability

    dist = _dist(distribution_id="", distribution_version="")
    pbm = _pbm(zones=[ZoneProbability(zone="BUY_ZONE", terminal=_pv())], dist=dist)
    pub = pbm.public_view()["zones"][0]
    assert "terminal_probability" not in pub
    assert "MISSING_DISTRIBUTION_IDENTITY" in pub["terminal_reason_codes"]


# ── §18/§20/§21：calibration scope typed reasons ──

def test_18_panel_scope_missing_evidence_typed_reason():
    from market_ai_hub.research.price_probability_map import ZoneProbability

    pbm = _pbm(zones=[ZoneProbability(zone="BUY_ZONE", terminal=_pv())], dist=_dist(),
               scope="PANEL", scope_ev={})
    pub = pbm.public_view()["zones"][0]
    assert "terminal_probability" not in pub
    assert "CALIBRATION_SCOPE_EVIDENCE_MISSING" in pub["terminal_reason_codes"]
    assert pub["terminal_status"] != "NOT_AVAILABLE_INSUFFICIENT_DISTRIBUTION"
    assert pbm.public_view()["calibration_scope_reason_codes"]


def test_20_panel_scope_universe_mismatch_typed_reason():
    from market_ai_hub.research.price_probability_map import ZoneProbability

    pbm = _pbm(zones=[ZoneProbability(zone="BUY_ZONE", terminal=_pv())], dist=_dist(),
               scope="PANEL", scope_ev={"universe_id": "u1", "universe_version": "v1",
                                        "members": ["OTHER"],
                                        "target_families": ["TAIWAN_STOCK"],
                                        "supported_horizons": ["1d"],
                                        "calibration_domain": "PRICE_DISTRIBUTION",
                                        "scope_version": "v1"})
    pub = pbm.public_view()["zones"][0]
    assert "CALIBRATION_UNIVERSE_MISMATCH" in pub["terminal_reason_codes"]


def test_21_global_scope_mismatch_typed_reason():
    from market_ai_hub.research.price_probability_map import ZoneProbability

    pbm = _pbm(zones=[ZoneProbability(zone="BUY_ZONE", terminal=_pv())], dist=_dist(),
               scope="GLOBAL", scope_ev={"scope_definition": "d", "scope_version": "v1",
                                         "supported_target_families": ["OSAKA_MICRO"],
                                         "supported_horizons": ["1d"],
                                         "calibration_domain": "PRICE_DISTRIBUTION"})
    pub = pbm.public_view()["zones"][0]
    assert "CALIBRATION_GLOBAL_SCOPE_MISMATCH" in pub["terminal_reason_codes"]


# ── §31：quantiles only ──

def test_31_quantiles_only_all_unavailable():
    from market_ai_hub.research.price_probability_map import probability_from_quantiles_only

    pub = probability_from_quantiles_only(["BUY_ZONE"], "X", "TAIWAN_STOCK", "1d").public_view()
    for z in pub["zones"]:
        for t in ("terminal", "touch", "first_passage"):
            assert f"{t}_probability" not in z
            assert z[f"{t}_status"].startswith("NOT_AVAILABLE")


# ── §32：current runtime truth ──

@pytest.mark.parametrize("family,instrument", [
    ("TAIWAN_STOCK", "3706.TW"), ("TAIWAN_STOCK", "2330.TW"),
    ("TAIWAN_INDEX", "TAIEX"), ("OSAKA_MICRO", "JNU"),
])
def test_32_current_runtime_no_public_probability(family, instrument):
    from market_ai_hub.research.price_probability_map import empty_price_map

    pm = empty_price_map(instrument, family, "1d", 100.0)
    assert pm.probability_map is None


# ── §33：existing invariants preserved ──

def test_33_full_distribution_terminal_only():
    from market_ai_hub.research.price_probability_map import CAPABILITY_MATRIX

    assert CAPABILITY_MATRIX["FULL_DISTRIBUTION"]["touch"] is False
    assert CAPABILITY_MATRIX["FULL_DISTRIBUTION"]["first_passage"] is False


def test_33_actionability_and_instruction_invariants():
    from market_ai_hub.research.price_probability_map import empty_price_map

    pm = empty_price_map("JNU", "OSAKA_MICRO", "1d", 100.0)
    assert pm.state_is_trade_instruction is False
    assert pm.actionability_status == "NOT_VALIDATED"


# ── §35：version ──

def test_35_version_3a22():
    from market_ai_hub.research.price_probability_map import PRICE_PROBABILITY_MAP_VERSION

    assert PRICE_PROBABILITY_MAP_VERSION == "3A.2.3"
