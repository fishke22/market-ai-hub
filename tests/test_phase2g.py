"""Phase 2G — joint forecast / scenario / ensemble / router tests。"""
import numpy as np
import pandas as pd
import pytest

from market_ai_hub.forecast.contract import (
    CALIBRATED_PROBABILITY,
    UNVALIDATED_WEIGHT,
    JointForecastResult,
    ResearchState,
)
from market_ai_hub.forecast.dynamic_ensemble import DynamicEnsembleEngine
from market_ai_hub.forecast.joint_baselines import var_baseline
from market_ai_hub.forecast.leakage import (
    FutureLeakageError,
    assert_no_future_leak,
    is_known_future,
    validate_covariate_source,
)
from market_ai_hub.forecast.regime_router import RegimeModelRouter
from market_ai_hub.forecast.scenario import SCENARIO_TYPES, ScenarioEngine
from market_ai_hub.forecast.synthesis import (
    compute_research_center,
    derive_research_state,
    integrate_historical_edge,
    synthesize,
)
from market_ai_hub.forecast.weights import compute_weights
from market_ai_hub.forecast.backtest import assert_same_exam, same_exam_comparison
from market_ai_hub.forecast.registration import register_joint_forecast
from market_ai_hub.research.registry import PredictionRegistry


def _panel(n=80, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2023-01-01", periods=n, freq="B", tz="UTC")
    cols = ["NQ", "ES", "SOX", "USDJPY", "VIX", "US10Y", "^N225"]
    data = {}
    for i, c in enumerate(cols):
        data[c] = 100 * np.exp(np.cumsum(rng.normal(0.0003, 0.01 + 0.002 * i, n)))
    return pd.DataFrame(data, index=idx)


# --- C: leakage ---
def test_joint_no_future_leak():
    assert_no_future_leak({"NQ_tomorrow": "JOINT_MODEL", "VIX_tomorrow": "SCENARIO"})
    with pytest.raises(FutureLeakageError):
        assert_no_future_leak({"NQ_tomorrow": "ACTUAL_FUTURE"})


def test_known_future_covariate_allowed():
    assert is_known_future("fomc_schedule")
    assert is_known_future("holiday")
    assert not is_known_future("NQ_tomorrow")


def test_unknown_future_actual_rejected():
    with pytest.raises(FutureLeakageError):
        validate_covariate_source("USDJPY_tomorrow", "ACTUAL_FUTURE")
    validate_covariate_source("USDJPY_tomorrow", "JOINT_MODEL")  # ok


# --- B: contract ---
def test_joint_forecast_contract():
    jf = JointForecastResult(joint_forecast_id="j1", information_cutoff="2024-01-01T00:00:00+00:00",
                             target="^N225", horizon="5d", p50=30000.0, seed=0, sample_count=200)
    assert jf.p50 == 30000.0 and jf.calibration_status == "UNVALIDATED"


def test_joint_baseline_var():
    jf = var_baseline(_panel(60), target="^N225", horizon=5, n_paths=50, seed=0)
    assert jf.target_distribution and jf.p50 is not None
    assert len(jf.future_paths) == 50


# --- E/F/G: scenario ---
def test_scenario_generation():
    state = {"NQ": 18000, "ES": 5000, "SOX": 500, "USDJPY": 150, "VIX": 15, "US10Y": 4.0, "^N225": 39000}
    paths = ScenarioEngine().generate(state, horizon=5, seed=0)
    assert {p.scenario_id for p in paths} == set(SCENARIO_TYPES)
    for p in paths:
        assert p.scenario_source == "regime_rule"


def test_scenario_unvalidated_weight_not_probability():
    paths = ScenarioEngine().generate({"^N225": 39000}, scenario_types=["BASE"], seed=0)
    p = paths[0]
    assert p.weight_calibration_status == UNVALIDATED_WEIGHT
    assert p.weight_calibration_status != CALIBRATED_PROBABILITY


# --- H/O: direct/joint separation ---
def test_direct_joint_separation():
    r = synthesize(target="^N225", horizon="5d",
                   direct_forecast={"model": "chronos", "point": 39100},
                   joint_forecast={"model": "var", "p50": 39000})
    assert r.direct_forecast["model"] == "chronos"
    assert r.joint_forecast["model"] == "var"


# --- I/M: dynamic weight ---
def test_dynamic_weight_deterministic():
    stats = [{"model": "a", "loss": 0.1, "calibration_error": 0.1, "failure_rate": 0.0, "sample_size": 100},
             {"model": "b", "loss": 0.2, "calibration_error": 0.2, "failure_rate": 0.1, "sample_size": 50}]
    w1 = compute_weights(stats)
    w2 = compute_weights(stats)
    assert w1 == w2 and abs(sum(w1.values()) - 1.0) < 1e-9


# --- J: best baseline eligible + dominant ---
def test_best_baseline_eligible():
    stats = [{"model": "best_baseline", "loss": 0.15, "calibration_error": 0.1, "failure_rate": 0.0, "sample_size": 100},
             {"model": "ai_model", "loss": 0.3, "calibration_error": 0.2, "failure_rate": 0.05, "sample_size": 80}]
    w = DynamicEnsembleEngine().compute_weights(stats)
    assert "best_baseline" in w and w["best_baseline"] > w["ai_model"]


def test_baseline_dominant_allowed():
    s = derive_research_state("bullish", "bullish", "bullish", "EDGE_FOUND",
                              baseline_dominant=True)
    assert s == ResearchState.BASELINE_DOMINANT


# --- K/L: regime router sample safety ---
def test_regime_insufficient_sample_fallback():
    perf = [
        {"model": "m1", "regime": "VOL_HIGH", "sample_size": 4, "loss": 0.01,
         "calibration_error": 0.0, "failure_rate": 0.0},
        {"model": "m1", "regime": "ALL", "sample_size": 100, "loss": 0.5,
         "calibration_error": 0.2, "failure_rate": 0.1},
    ]
    r = RegimeModelRouter(min_regime_sample=30).route("^N225", "5d", "VOL_HIGH", perf)
    assert r["evidence_state"]["m1"] == "REGIME_EVIDENCE_INSUFFICIENT"
    assert r["fallback_model"] == "m1"


# --- N: model runtime failure skip ---
def test_model_runtime_failure_skip():
    stats = [{"model": "ok", "loss": 0.1, "calibration_error": 0.0, "failure_rate": 0.0, "sample_size": 100},
             {"model": "bad", "loss": 0.1, "calibration_error": 0.0, "failure_rate": 0.0, "sample_size": 100}]

    class Boom:
        pass
    components = [
        {"model": "ok", "samples": [1.0, 2.0, 3.0]},
        {"model": "bad", "samples": Boom()},  # 會 raise
    ]
    # 用 samples 型別錯誤觸發 skip：把 samples 換成會拋的物件
    components[1]["samples"] = "not-a-list"
    out = DynamicEnsembleEngine().run_safe(components, stats)
    assert any("bad" in s["model"] for s in out["skipped"])


# --- P: ensemble quantile semantics ---
def test_ensemble_quantile_no_fake_distribution():
    e = DynamicEnsembleEngine()
    q = e.quantile_summary({"a": {"p10": 1, "p50": 2, "p90": 3}}, {"a": 1.0})
    assert q["method"] == "ENSEMBLE_RESEARCH_QUANTILE_SUMMARY" and q["validated"] is False


def test_validated_distribution_quantile():
    e = DynamicEnsembleEngine()
    q = e.mixture_quantiles({"a": [1.0, 2.0, 3.0, 4.0, 5.0]}, {"a": 1.0})
    assert q["method"] == "SAMPLE_LEVEL_MIXTURE" and q["validated"] is True


# --- Q: research center reproducible ---
def test_research_center_reproducible():
    a = compute_research_center("weighted_median", {"values": [1, 2, 3, 4], "weights": [1, 1, 1, 1]})
    b = compute_research_center("weighted_median", {"values": [1, 2, 3, 4], "weights": [1, 1, 1, 1]})
    assert a == b
    with pytest.raises(ValueError):
        compute_research_center("llm_guess", {})


# --- R: historical edge not modify forecast ---
def test_historical_edge_not_modify_forecast():
    out = integrate_historical_edge("bullish", "UNPROVEN")
    assert out["model_direction"] == "bullish"
    assert out["evidence"] == "BULLISH + EDGE_UNPROVEN"


# --- S: research states ---
def test_research_wait_valid():
    assert derive_research_state("", "", "", "EDGE_FOUND") in ("WAIT", "MIXED")


def test_research_no_edge_valid():
    assert derive_research_state("bullish", "bullish", "bullish", "NO_EDGE") == ResearchState.NO_EDGE


# --- V: prediction registry joint registration ---
def test_prediction_registry_joint_registration(tmp_path):
    reg = PredictionRegistry(root=tmp_path)
    jf = var_baseline(_panel(60), target="^N225", horizon=5, n_paths=50, seed=0)
    fid = register_joint_forecast(reg, jf, origin_price=39000.0)
    assert reg.get(fid)["model_task"] == "joint_forecast"


# --- T/U: same-exam comparison ---
def test_same_exam_ensemble_comparison():
    rng = np.random.default_rng(0)
    actual = list(100 + rng.normal(0, 1, 100))
    methods = {
        "best_model": {"point": list(np.asarray(actual) + rng.normal(0, 0.5, 100))},
        "best_baseline": {"point": list(np.asarray(actual) + rng.normal(0, 1.0, 100))},
        "dynamic_ensemble": {"point": list(np.asarray(actual) + rng.normal(0, 0.3, 100))},
    }
    assert assert_same_exam(methods)
    cmp = same_exam_comparison(methods, actual)
    assert set(cmp) == set(methods) and "mae" in cmp["dynamic_ensemble"]
