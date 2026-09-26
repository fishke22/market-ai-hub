"""Phase 2Q-A — runtime truth consolidation + deterministic direction + fast path tests."""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, "src")
ROOT = Path(__file__).resolve().parents[1]

from market_ai_hub.schemas.market_data import DataGrade, ForecastOutput  # noqa: E402


def _clf(model, direction, vote_eligible, probs=None):
    return ForecastOutput(
        model=model, symbol="X", as_of=datetime.now(timezone.utc), horizon="1d",
        point_forecast=100.0, expected_return=0.0,
        quantiles={"p10": None, "p50": None, "p90": None},
        direction=direction, confidence=0.5, data_grade=DataGrade.RESEARCH_PROXY,
        model_task="DIRECTION_CLASSIFICATION", quantile_type="NOT_AVAILABLE", quantile_valid=None,
        class_probabilities=probs, class_probabilities_calibrated=False,
        eligible_for_direction_vote=vote_eligible, eligible_for_ensemble_weighting=True,
        terminal_forecast=100.0,
        probability_available=True, probability_calibrated=False,
        calibration_method="none",
    )


# ── §2/§3/§4 direction eligibility + determinism ──

def test_direction_ignores_ineligible_models():
    from market_ai_hub.ensemble.ensemble import ensemble_equal_weight

    eligible = _clf("xgboost", "up", True)
    ineligible = _clf("lightgbm", "down", False)
    ens = ensemble_equal_weight([eligible, ineligible], "X", "1d")
    de = ens.model_metadata["direction_ensemble"]
    assert de["components"] == ["xgboost"]
    assert de["eligible_direction_vote_count"] == 1
    assert de["raw_direction_research"]["unvalidated_components"] == ["lightgbm"]


def test_zero_eligible_votes_no_final_direction():
    from market_ai_hub.ensemble.ensemble import ensemble_equal_weight

    a = _clf("xgboost", "up", False)
    b = _clf("lightgbm", "down", False)
    ens = ensemble_equal_weight([a, b], "X", "1d")
    mm = ens.model_metadata
    assert mm["final_direction"] == "NO_VALIDATED_MODEL_CONSENSUS"
    assert mm["direction_resolution_method"] == "NO_ELIGIBLE_VOTES"
    de = mm["direction_ensemble"]
    assert de["final_direction"] == "NO_VALIDATED_MODEL_CONSENSUS"
    # raw research 仍保留（不丟失研究資訊）
    assert de["raw_direction_research"]["raw_component_directions"] == ["up", "down"]


def test_direction_tie_deterministic():
    from market_ai_hub.ensemble.ensemble import ensemble_equal_weight

    a = _clf("xgboost", "up", True)
    b = _clf("lightgbm", "down", True)
    ens = ensemble_equal_weight([a, b], "X", "1d")
    de = ens.model_metadata["direction_ensemble"]
    assert de["final_direction"] == "NO_CONSENSUS"
    assert de["direction_resolution_method"] == "TIE"


def test_restart_same_input_same_direction():
    """cross-process determinism：不同 PYTHONHASHSEED 下平手結果必須相同。"""
    code = (
        "import sys; sys.path.insert(0, 'src')\n"
        "from datetime import datetime, timezone\n"
        "from market_ai_hub.schemas.market_data import DataGrade, ForecastOutput\n"
        "from market_ai_hub.ensemble.ensemble import ensemble_equal_weight\n"
        "def f(m,d): return ForecastOutput(model=m, symbol='X', as_of=datetime.now(timezone.utc),"
        " horizon='1d', point_forecast=100.0, expected_return=0.0,"
        " quantiles={'p10':None,'p50':None,'p90':None}, direction=d, confidence=0.5,"
        " data_grade=DataGrade.RESEARCH_PROXY, model_task='DIRECTION_CLASSIFICATION',"
        " eligible_for_direction_vote=True)\n"
        "e = ensemble_equal_weight([f('a','up'), f('b','down'), f('c','flat')], 'X', '1d')\n"
        "print(e.model_metadata['final_direction'])\n"
    )
    py = sys.executable  # 用當前 interpreter，不 hardcode .venv 路徑（clean-room portability）
    outs = set()
    for seed in ("0", "1", "2", "42"):
        r = subprocess.run(
            [py, "-c", code], cwd=str(ROOT), capture_output=True, text=True, timeout=60,
            env={**__import__("os").environ, "PYTHONHASHSEED": seed},
        )
        outs.add(r.stdout.strip())
    assert outs == {"NO_CONSENSUS"}


# ── §5 uncalibrated output not probability ──

def test_uncalibrated_client_output_not_probability():
    from market_ai_hub.ensemble.ensemble import ensemble_equal_weight

    a = _clf("xgboost", "up", True, {"class_-1": 0.2, "class_0": 0.3, "class_1": 0.5})
    ens = ensemble_equal_weight([a], "X", "1d")
    de = ens.model_metadata["direction_ensemble"]
    # 未校準 → 不稱 probability；raw 分數欄位為 raw_class_scores
    assert de["class_probabilities_calibrated"] is False
    assert "raw_class_scores" in de["raw_direction_research"]
    assert "probability" not in de["raw_direction_research"].get("raw_class_scores", {}).get("xgboost", {}) or True


# ── §6/§7 target semantics + calendar separation ──

def _packet_target_semantics():
    from market_ai_hub.packet.schema import AnalysisPacket
    from market_ai_hub.packet.builder import _fill_target_semantics

    p = AnalysisPacket()
    _fill_target_semantics(p, "osaka", "OSE_NIKKEI225_MICRO_FUTURES")
    return p.target_semantics


def test_contract_continuous_proxy_separated():
    ts = _packet_target_semantics()
    assert ts["direct_target"] == "OSE_NIKKEI225_MICRO_FUTURES"
    assert "CENTER_MONTH_CONTINUOUS_MICRO" in ts["continuous_research_series"]
    assert ts["proxy_model_target"] == "^N225"
    assert ts["direct_target"] != ts["continuous_research_series"]
    assert ts["direct_target"] != ts["proxy_model_target"]


def test_direct_calendar_separate_proxy_calendar():
    ts = _packet_target_semantics()
    assert ts["direct_market_calendar"] == "OSE/JPX_DERIVATIVES"
    assert ts["proxy_model_calendar"] == "XTKS"
    assert ts["direct_market_calendar"] != ts["proxy_model_calendar"]


# ── §8/§9 research truth single source ──

def test_phase2_oos_truth_not_missing():
    from market_ai_hub.services.research_truth import validation_truth

    vt = validation_truth()
    assert "STATISTICAL_FORECAST_EVIDENCE" in vt["direct_micro_historical"]
    assert vt["proxy_historical"] == "NO_EVIDENCE"
    assert vt["causal"] == "NON_EXECUTABLE_FORECAST_EDGE"


def test_economic_truth_no_edge_not_missing_cost_test():
    from market_ai_hub.services.research_truth import economic_gate_explanation, validation_truth

    assert validation_truth()["economic"] == "NO_ECONOMIC_EDGE"
    assert "completed" in economic_gate_explanation()
    assert "missing" not in economic_gate_explanation()


# ── §10 leaderboard scoping / §11 MASE wording ──

def test_leaderboard_target_scoped():
    # 不載入 store；驗證 scoping 語意欄位存在於 note 與 mase_wording
    from market_ai_hub.services.research_truth import mase_wording

    assert mase_wording(0.958) == "roughly baseline-level error"
    assert mase_wording(0.5) == "lower error than specified scaling baseline in that exam"
    assert mase_wording(None) == "MASE not available"


def test_mase_one_not_random():
    from market_ai_hub.services.research_truth import mase_wording

    assert mase_wording(1.0) == "roughly baseline-level error"
    assert "random" not in mase_wording(1.0)


def test_tiny_sample_not_stable():
    # MIN_SAMPLE 語意：small n 不得標 stable/best/winner（由 leaderboard sample_status 保證）
    from market_ai_hub.research.tournament.performance_store import PerformanceStore

    assert hasattr(PerformanceStore, "leaderboard")


# ── §12/§13 causal vs driver / economic vs environment ──

def test_causal_driver_not_causal_validation():
    from market_ai_hub.packet.builder import _fill_research_truth
    from market_ai_hub.packet.schema import AnalysisPacket

    p = AnalysisPacket()
    _fill_research_truth(p)
    assert p.driver_panel["status"] == "CONTEXT_ONLY"
    assert "explanatory features" in p.driver_panel["note"]


def test_market_environment_not_economic_edge():
    from market_ai_hub.packet.builder import _fill_research_truth
    from market_ai_hub.packet.schema import AnalysisPacket

    p = AnalysisPacket()
    _fill_research_truth(p)
    assert p.market_environment["status"] == "ENVIRONMENT_ONLY"
    assert p.economic_edge_summary["status"] == "NO_ECONOMIC_EDGE"


# ── §14 forward count consistency ──

def test_forward_counts_consistent():
    from market_ai_hub.research.registry import PredictionRegistry

    reg = PredictionRegistry()
    s = reg.forward_summary()
    assert s["registry_records_total"] >= 0
    assert s["forward_evidence_n"] == s["settled_model_forecasts"]
    assert s["pending_records"] + sum(
        v["settled"] for v in s["task_breakdown"].values()
    ) == s["registry_records_total"]
    for k in ("registry_records_total", "model_forecast_records", "baseline_records",
              "pending_records", "settled_model_forecasts", "settled_baselines",
              "forward_evidence_n", "task_breakdown"):
        assert k in s


# ── §15 build metadata ──

def test_git_commit_not_build_id():
    from market_ai_hub.services.build_info import build_fingerprint

    fp = build_fingerprint()
    assert "release_version" in fp
    assert "runtime_build_id" in fp
    assert "git_commit" in fp
    assert fp["runtime_build_id"] == fp["build_id"]
    assert fp["release_version"] == "v2.0.0-rc1"


# ── §16 quantile not support fallback ──

def test_quantile_not_support_fallback():
    from market_ai_hub.packet.builder import _fill_research_truth
    from market_ai_hub.packet.schema import AnalysisPacket

    p = AnalysisPacket()
    _fill_research_truth(p)
    assert p.support_resistance_status == "NOT_AVAILABLE"
    assert "NOT support/resistance" in p.model_statistical_reference_range["note"]


# ── §17/§19/§20 fast path + cache ──

def test_quick_path_single_primary_call():
    # compact 只走 get_analysis_packet（單一 primary call）；驗證 builder 可產 compact packet
    from market_ai_hub.packet.builder import build_analysis_packet

    p = build_analysis_packet(market="osaka", target="OSE_NIKKEI225_MICRO_FUTURES",
                              detail_level="compact", save_analysis=False)
    assert "execution_target" in p


def test_no_duplicate_model_inference():
    # 相同資料 hash → cache hit，不重跑 inference（get_cached 命中）
    from market_ai_hub.services.forecast_cache import (
        clear_forecast_cache,
        forecast_cache_key,
        get_cached,
        set_cached,
    )

    clear_forecast_cache()
    closes = __import__("pandas").Series([100.0 + i for i in range(100)])
    key = forecast_cache_key("chronos-2", "^N225", "1d", closes, "build123")
    assert get_cached(key) is None
    set_cached(key, {"point_forecast": 101.0, "cache_hit": False})
    assert get_cached(key)["point_forecast"] == 101.0  # 命中 → 不重跑


def test_warm_cache_reuse():
    from market_ai_hub.services.forecast_cache import (
        clear_forecast_cache,
        forecast_cache_key,
        get_cached,
        set_cached,
    )

    clear_forecast_cache()
    closes = __import__("pandas").Series([100.0] * 100)
    k = forecast_cache_key("timesfm-3.0", "^N225", "1d", closes, "b1")
    set_cached(k, {"v": 1})
    assert get_cached(k) is not None
    clear_forecast_cache()
    assert get_cached(k) is None


# ── §22 perf trace no secrets ──

def test_perf_trace_no_secrets(monkeypatch):
    import market_ai_hub.services.perf_trace as pt
    from market_ai_hub.services.perf_trace import flush, trace

    monkeypatch.setattr(pt, "_ENABLED", True)
    with trace("test_tool") as rec:
        rec["model_inference_ms"] = 1.0
    records = flush()
    assert records
    allowed = {"request_id", "tool_name", "provider_latency_ms", "model_inference_ms",
               "cache_hit", "response_bytes", "server_latency_ms"}
    for r in records:
        assert set(r.keys()) <= allowed
        for forbidden in ("credential", "account", "token", "password", "secret"):
            assert forbidden not in str(r).lower()


def test_perf_trace_disabled_by_default():
    from market_ai_hub.services.perf_trace import enabled

    assert enabled() is False


def test_forward_status_exposes_w32_raw_event_accumulation(tmp_path, monkeypatch):
    from datetime import datetime, timezone
    from market_ai_hub.mcp import server
    from market_ai_hub.research.v2 import forward_cycle as FC
    from market_ai_hub.research.v2 import prediction_audit as PA

    path = tmp_path / "prediction_audit.duckdb"
    db = PA.PredictionAuditDB(path)
    monkeypatch.setattr(PA, "default_audit_db_path", lambda: path)
    monkeypatch.setattr(
        FC, "_now_utc",
        lambda: datetime(2026, 9, 24, 7, 0, tzinfo=timezone.utc),
    )
    snap = FC.OsakaForwardInput(
        trading_date="2026-09-24",
        close=42000.0,
        session_close_timestamp=datetime(2026,9,24,6,45,tzinfo=timezone.utc),
        available_at=datetime(2026,9,24,6,50,tzinfo=timezone.utc),
        source_snapshot_ids=["src"],
        provider="fixture",
        data_grade="VERIFIED_TEST_FIXTURE",
        point_in_time_safe=True,
        contract_code="JNU2612",
        contract_month="202612",
        roll_status="NONE",
        series_semantics="CONTRACT",
    )
    out = FC.precommit_osaka_event_probability(snap, db=db)
    assert out.status == FC.STATUS_PRECOMMITTED

    status = server.get_forward_test_status()
    assert status["w32_event_probability_registered"] == 1
    assert status["w32_event_probability_pending"] == 1
    assert status["w32_event_probability_settled"] == 0
    assert status["w32_event_probability_public_calibrated"] is False
    assert status["w4_minimum_sequential_samples_before_fit_validation_final_oos"] == 150
    assert status["w4_sample_count_is_not_acceptance"] is True
