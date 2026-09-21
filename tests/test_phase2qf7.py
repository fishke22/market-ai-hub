"""Phase 2Q-F.7 — target-scoped research truth + fresh sample tests。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, "src")
ROOT = Path(__file__).resolve().parents[1]

_OSAKA_MARKERS = ("VAR(1)", "OSE", "Micro", "225LABO", "NON_EXECUTABLE_FORECAST_EDGE")


# ── §A2/§A3：Taiwan truth 不得繼承 Osaka ──

def test_taiwan_stock_no_osaka_contamination():
    from market_ai_hub.services.research_truth import evidence_for

    ev = evidence_for("TAIWAN_STOCK", "3706.TW")
    s = str(ev)
    for m in _OSAKA_MARKERS:
        assert m not in s, f"Taiwan stock evidence contaminated with {m}"
    assert ev["historical_oos"] == "NOT_YET_VALIDATED"
    assert ev["causal"] == "NOT_ESTABLISHED"


def test_taiwan_index_no_osaka_contamination():
    from market_ai_hub.services.research_truth import evidence_for

    ev = evidence_for("TAIWAN_INDEX", "TAIEX")
    s = str(ev)
    for m in _OSAKA_MARKERS:
        assert m not in s, f"Taiwan index evidence contaminated with {m}"
    assert ev["historical_oos"] == "NOT_YET_VALIDATED"
    assert ev["execution_validation"] == "NOT_ESTABLISHED"


def test_osaka_keeps_own_evidence():
    from market_ai_hub.services.research_truth import evidence_for

    ev = evidence_for("OSAKA_MICRO", "OSE_NIKKEI225_MICRO_FUTURES")
    assert "STATISTICAL_FORECAST_EVIDENCE" in ev["direct_micro_historical"]
    assert ev["causal"] == "NON_EXECUTABLE_FORECAST_EDGE"


def test_packet_validation_truth_target_scoped():
    from market_ai_hub.packet.builder import build_analysis_packet

    taiwan = build_analysis_packet(market="taiwan_index", target="TAIEX", detail_level="compact", save_analysis=False)
    s = str(taiwan["validation_truth"])
    for m in _OSAKA_MARKERS:
        assert m not in s, f"TAIEX packet contaminated with {m}"

    osaka = build_analysis_packet(market="osaka", detail_level="compact", save_analysis=False)
    assert "STATISTICAL_FORECAST_EVIDENCE" in str(osaka["validation_truth"])


def test_unknown_family_not_contaminated():
    from market_ai_hub.services.research_truth import evidence_for

    ev = evidence_for("UNKNOWN_FAMILY", "X")
    assert ev["historical_oos"] == "NOT_YET_VALIDATED"
    assert "VAR(1)" not in str(ev)


# ── §A4/§A11：fresh sample not evidence ──

def test_fresh_sample_metadata_not_evidence():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "capture_fresh", ROOT / "scripts" / "capture_fresh_validation_sample.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    m = mod.SAMPLE_META
    assert m["sample_role"] == "ENGINEERING_RUNTIME_VALIDATION_ONLY"
    assert m["not_training_data"] is True
    assert m["not_model_selection_data"] is True
    assert m["not_predictive_evidence"] is True


def test_fresh_sample_does_not_upgrade_gates():
    # fresh sample 不得讓 MODEL_PREDICTIVE_GATE / TRADING_EDGE_GATE 變 PASS
    from market_ai_hub.mcp import server as s

    gates = s.get_research_gates()["gates"]
    assert gates["MODEL_PREDICTIVE_GATE"]["status"] != "PASS"
    assert gates["TRADING_EDGE_GATE"]["result"] == "NO_ECONOMIC_EDGE"


# ── §A8/§A12：calendar separation ──

def test_ose_holiday_trading_calendar_truth():
    from market_ai_hub.services.calendar import next_ose_derivatives_sessions

    sessions = next_ose_derivatives_sessions("2026-09-18", 5)
    assert sessions[:3] == ["2026-09-21", "2026-09-22", "2026-09-23"]


def test_health_family_calendars():
    from market_ai_hub.packet.builder import build_analysis_packet

    osaka = build_analysis_packet(market="osaka", detail_level="compact", save_analysis=False)["target_semantics"]
    assert osaka["direct_market_calendar"] == "OSE/JPX_DERIVATIVES"
    assert osaka["proxy_model_calendar"] == "XTKS"

    tw = build_analysis_packet(market="taiwan_index", target="TAIEX", detail_level="compact", save_analysis=False)["target_semantics"]
    assert tw["direct_market_calendar"] == "XTAI"
