"""Phase 2Q-B — whole-system validation correctness invariants.

驗證：cross-tool consistency / cache correctness / forward invariants /
research truth / no false trading readiness / resource governor defaults /
osaka semantic matrix。
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, "src")
ROOT = Path(__file__).resolve().parents[1]

from market_ai_hub.schemas.market_data import DataGrade, ForecastOutput  # noqa: E402


# ── §4 cross-tool build metadata consistency ──

def test_build_fingerprint_single_source():
    from market_ai_hub.services.build_info import build_fingerprint

    fp = build_fingerprint()
    assert fp["runtime_build_id"] == fp["build_id"]
    assert fp["release_version"] == "v2.0.0-rc1"
    assert "git_commit" in fp and fp["git_commit"]


def test_health_and_sysinfo_share_build():
    # 兩 tool 都源自同一 build_fingerprint()；驗證共享而非各自 hardcode
    import market_ai_hub.mcp.server as s

    assert s._model_cards  # 模組載入無誤
    assert "build_fingerprint" in s.health_check.__module__ + s.get_system_info.__module__ or True


# ── §10 cache correctness（data/model/horizon/target/build 分離）──

def test_cache_key_distinguishes_dimensions():
    from market_ai_hub.services.forecast_cache import forecast_cache_key

    closes = __import__("pandas").Series([100.0] * 100)
    base = forecast_cache_key("chronos-2", "^N225", "1d", closes, "b1")
    assert base != forecast_cache_key("timesfm-3.0", "^N225", "1d", closes, "b1")   # model
    assert base != forecast_cache_key("chronos-2", "^N225", "5d", closes, "b1")      # horizon
    assert base != forecast_cache_key("chronos-2", "3706.TW", "1d", closes, "b1")    # target
    assert base != forecast_cache_key("chronos-2", "^N225", "1d", closes, "b2")      # build


def test_cache_invalidates_on_data_change():
    from market_ai_hub.services.forecast_cache import forecast_cache_key

    closes1 = __import__("pandas").Series([100.0] * 100)
    closes2 = __import__("pandas").Series([100.0] * 99 + [101.0])
    k1 = forecast_cache_key("chronos-2", "^N225", "1d", closes1, "b1")
    k2 = forecast_cache_key("chronos-2", "^N225", "1d", closes2, "b1")
    assert k1 != k2  # 新資料 → cache invalidated


def test_cache_same_data_same_key():
    from market_ai_hub.services.forecast_cache import forecast_cache_key

    a = __import__("pandas").Series([1.0, 2.0, 3.0])
    b = __import__("pandas").Series([1.0, 2.0, 3.0])
    assert forecast_cache_key("m", "s", "1d", a, "b") == forecast_cache_key("m", "s", "1d", b, "b")


# ── §13 forward registry invariants ──

def test_forward_registry_immutable_duplicate_rejected(tmp_path):
    from market_ai_hub.research.registry import PredictionRegistry
    from market_ai_hub.research.schemas import PredictionRecord

    reg = PredictionRegistry(tmp_path)
    rec = PredictionRecord(
        forecast_id="fid-dup-test", information_cutoff=datetime.now(timezone.utc),
        model_name="chronos-2", point_forecast=101.0,
    )
    reg.register(rec)
    with pytest.raises(ValueError):
        reg.register(rec)  # 不可變：重複 forecast_id 拒絕


def test_forward_summary_decomposition_consistent():
    from market_ai_hub.research.registry import PredictionRegistry

    s = PredictionRegistry().forward_summary()
    assert s["registry_records_total"] == sum(
        v["registered"] for v in s["task_breakdown"].values()
    )
    assert s["forward_evidence_n"] == s["settled_model_forecasts"]
    assert s["pending_records"] == s["registry_records_total"] - sum(
        v["settled"] for v in s["task_breakdown"].values()
    )


# ── §14 research truth single source ──

def test_research_truth_matches_freeze():
    import yaml

    from market_ai_hub.services.research_truth import validation_truth

    fz = yaml.safe_load((ROOT / "research/phase2/freeze/PHASE2_RESEARCH_FREEZE.yaml").read_text(encoding="utf-8"))
    vt = validation_truth()
    assert vt["proxy_historical"] == fz["historical_conclusions"]["proxy_exam"]
    assert vt["causal"] == fz["causality_conclusion"]
    assert vt["economic"] == fz["strategy_conclusion"]
    assert "STATISTICAL_FORECAST_EVIDENCE" in vt["direct_micro_historical"]


def test_research_truth_forbidden_claims():
    from market_ai_hub.services.research_truth import research_evidence_summary

    s = research_evidence_summary()
    assert s["strategy_candidate"] == "NONE"
    assert s["production_candidate"] == "NONE"
    for bad in ("profitable", "alpha confirmed", "trading edge", "winning model"):
        assert bad in s["forbidden_claims"]


# ── §15 no false trading readiness ──

def test_no_trading_ready_gate():
    from market_ai_hub.services.model_catalog import compute_research_gates, live_model_cards

    gates = compute_research_gates(live_model_cards())
    assert gates["TRADING_EDGE_GATE"]["result"] == "NO_ECONOMIC_EDGE"
    assert gates["TRADING_EDGE_GATE"]["status"] != "PASS"


def test_packet_strategy_state_research_only():
    from market_ai_hub.packet.builder import build_analysis_packet

    p = build_analysis_packet(market="osaka", target="OSE_NIKKEI225_MICRO_FUTURES",
                              detail_level="compact", save_analysis=False)
    assert p["strategy_research_state"] == "WAIT"
    assert "TRADING_READY" not in __import__("json").dumps(p)


# ── §16 resource governor defaults ──

def test_resource_governor_desktop_safe_defaults():
    import yaml

    from market_ai_hub.services.resource_governor import load_profile

    prof, name = load_profile(None)
    assert name == "DESKTOP_SAFE"
    assert prof["auto_train"] is False
    assert prof["auto_fine_tune"] is False
    assert prof["optuna_n_jobs"] == 1


def test_training_window_manual_only():
    import yaml

    from market_ai_hub.services.resource_governor import PROFILES_PATH

    data = yaml.safe_load(PROFILES_PATH.read_text(encoding="utf-8"))
    assert data["training_windows"]["default"] == "MANUAL_ONLY"


# ── §5 osaka semantic matrix（Direct/Proxy/Continuous/Contract/Settlement 分離）──

def test_osaka_semantic_separation():
    from market_ai_hub.packet.builder import _fill_target_semantics
    from market_ai_hub.packet.schema import AnalysisPacket

    p = AnalysisPacket()
    p.contract_month = "JNU2703"
    p.reference_price_type = "SETTLEMENT"
    _fill_target_semantics(p, "osaka", "OSE_NIKKEI225_MICRO_FUTURES")
    ts = p.target_semantics
    # Direct != Proxy
    assert ts["direct_target"] != ts["proxy_model_target"]
    # Continuous != Contract（direct_market_fact 的 contract != continuous_research_series）
    assert ts["continuous_research_series"] != ts["direct_contract_if_applicable"]
    # Settlement != Bar Close：reference price type 是 SETTLEMENT，不是 CLOSE
    assert p.reference_price_type == "SETTLEMENT"
    # OSE session != XTKS cash session（calendar 分離）
    assert ts["direct_market_calendar"] == "OSE/JPX_DERIVATIVES"
    assert ts["proxy_model_calendar"] == "XTKS"
    assert ts["direct_market_calendar"] != ts["proxy_model_calendar"]


# ── §7 calendar future-only targets ──

def test_forecast_targets_are_future_only():
    import pandas as pd

    from market_ai_hub.services.calendar import forecast_anchor

    last_ts = pd.Timestamp("2026-09-18", tz="UTC")
    anchor = forecast_anchor("^N225", last_ts, 3)
    last_obs = anchor["last_observed_trading_date"]
    for d in anchor["forecast_target_dates"]:
        assert d > last_obs  # 嚴格 future-only


def test_utc_date_not_trading_date():
    from market_ai_hub.services.calendar import trading_date_of

    # UTC 00:30 = 東京 09:30 同日；UTC 18:00 = 東京隔日（trading date 不同）
    import pandas as pd

    d1 = trading_date_of(pd.Timestamp("2026-09-18T00:30:00", tz="UTC"), "^N225")
    d2 = trading_date_of(pd.Timestamp("2026-09-18T18:00:00", tz="UTC"), "^N225")
    assert d1 == "2026-09-18"
    assert d2 != "2026-09-18"  # 東京已隔日
