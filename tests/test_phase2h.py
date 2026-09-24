"""Phase 2H — analysis packet / MCP / skills / archive auto-hook tests。"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, "src")

from market_ai_hub.packet.builder import build_analysis_packet
from market_ai_hub.packet.schema import (
    ENSEMBLE_RESEARCH_QUANTILE_SUMMARY,
    PRICE_TYPE_SETTLEMENT,
    UNVALIDATED_FORWARD,
    AnalysisPacket,
)
from market_ai_hub.packet.benchmark import token_benchmark
from market_ai_hub.targets.contract import EXECUTION_TARGET, role_of
from market_ai_hub.targets.events import OfficialEvent, event_visible
from market_ai_hub.automation.archive import AnalysisArchive, AnalysisRecord
from market_ai_hub.automation.incremental import atomic_write


def _tmp_settlement_root(tmp_path) -> Path:
    """建一個含 Micro settlement parquet 的 tmp data root。"""
    root = tmp_path / "data"
    dest = root / "raw" / "jpx" / "settlement" / "OSE" / "all" / "2026" / "09"
    dest.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame([{
        "product": "Nikkei 225 Micro Futures", "contract": "202612",
        "settlement_price": 65100.0, "final_settlement_price": None, "date": "20260918",
        "source_url": "x", "source_hash": "h",
    }])
    atomic_write(dest / "rb20260918.parquet", df.to_parquet(index=False))
    return root


# --- schema + target ---
def test_analysis_packet_schema():
    p = AnalysisPacket(horizon="1d")
    d = p.model_dump()
    for k in ("analysis_packet_id", "execution_target", "reference_price_type",
              "horizon", "strategy_research_state", "analysis_id"):
        assert k in d


def test_micro_default_target():
    p = build_analysis_packet(market="osaka", save_analysis=False)
    assert p["execution_target"] == EXECUTION_TARGET


def test_proxy_not_execution_target():
    assert role_of("^N225") != "TARGET"
    assert role_of(EXECUTION_TARGET) == "TARGET"


def test_settlement_not_live_close():
    p = build_analysis_packet(market="osaka", save_analysis=False)
    # 無 Micro settlement 時用 proxy；有 settlement 時是 SETTLEMENT，不得 LIVE_PRICE/CLOSE
    assert p["reference_price_type"] in ("SETTLEMENT", "PROXY", "REFERENCE")


# --- detail levels ---
def test_compact_packet():
    p = build_analysis_packet(market="osaka", detail_level="compact", save_analysis=False)
    assert p["execution_target"] == EXECUTION_TARGET
    assert "upcoming_events" in p  # compact 保留，但精簡


def test_normal_packet():
    p = build_analysis_packet(market="osaka", detail_level="normal", save_analysis=False)
    assert "data_coverage_summary" in p and "regime" in p


def test_audit_packet():
    p = build_analysis_packet(market="osaka", detail_level="audit", save_analysis=False)
    assert "audit" in p and "coverage" in p["audit"]


# --- data lake reuse ---
def test_data_lake_reuse(tmp_path, monkeypatch):
    root = _tmp_settlement_root(tmp_path)
    monkeypatch.setenv("MARKET_AI_DATA_ROOT", str(root))
    p = build_analysis_packet(market="osaka", save_analysis=False)
    assert p["reference_price_type"] == PRICE_TYPE_SETTLEMENT
    assert "jpx_micro_settlement" in p["data_reused"]


# --- events ---
def test_event_top_n():
    from market_ai_hub.packet.builder import _event_snapshot
    ev = _event_snapshot(top_n=3)
    assert len(ev) <= 3


def test_event_information_cutoff():
    e = OfficialEvent(event_name="CPI", scheduled_at=datetime(2024, 6, 10, tzinfo=timezone.utc),
                      released_at=datetime(2024, 6, 12, tzinfo=timezone.utc), source="BLS")
    assert event_visible([e], datetime(2024, 6, 11, tzinfo=timezone.utc)) == []
    assert event_visible([e], datetime(2024, 6, 13, tzinfo=timezone.utc)) == [e]


# --- quantile / research center ---
def test_ensemble_quantile_semantics():
    p = build_analysis_packet(market="osaka", save_analysis=False)
    assert p["ensemble_quantile_method"] == ENSEMBLE_RESEARCH_QUANTILE_SUMMARY
    assert p["ensemble_distribution_validated"] is False
    assert p["ensemble_validation"] == UNVALIDATED_FORWARD


def test_research_center_reproducible():
    from market_ai_hub.forecast.synthesis import compute_research_center
    a = compute_research_center("weighted_median", {"values": [1, 2, 3, 4], "weights": [1, 1, 1, 1]})
    b = compute_research_center("weighted_median", {"values": [1, 2, 3, 4], "weights": [1, 1, 1, 1]})
    assert a == b


# --- archive ---
def test_analysis_archive_auto_save(tmp_path, monkeypatch):
    root = _tmp_settlement_root(tmp_path)
    monkeypatch.setenv("MARKET_AI_DATA_ROOT", str(root))
    p = build_analysis_packet(market="osaka", detail_level="normal", save_analysis=True)
    assert p["saved_to_archive"] is True and p["analysis_id"]


def test_analysis_archive_immutable(tmp_path):
    a = AnalysisArchive(tmp_path)
    rec = AnalysisRecord(analysis_id="A1", information_cutoff="2024-06-01T00:00:00+00:00")
    a.save(rec)
    with pytest.raises(ValueError):
        a.save(rec)  # 不可變


def test_event_reanalysis_new_id(tmp_path):
    a = AnalysisArchive(tmp_path)
    a.save(AnalysisRecord(analysis_id="old", information_cutoff="2024-06-01T00:00:00+00:00"))
    a.save(AnalysisRecord(analysis_id="new", information_cutoff="2024-06-02T00:00:00+00:00"))
    a.record_reanalysis("new", "old", reason="FORECAST_STALE_AFTER_EVENT")
    links = a.reanalysis_of("old")
    assert len(links) == 1 and links[0]["analysis_id"] == "new"
    assert links[0]["reason"] == "FORECAST_STALE_AFTER_EVENT"


# --- V1 MCP backward compat ---
def test_V1_MCP_backward_compat():
    import asyncio
    from market_ai_hub.mcp.server import mcp

    async def main():
        names = [t.name for t in await mcp.list_tools()]
        return names

    names = asyncio.run(main())
    for want in ("health_check", "get_system_info", "get_market_data", "predict_chronos",
                 "predict_timesfm", "predict_ensemble", "get_model_performance",
                 "backtest", "analyze_osaka_nikkei", "analyze_taiwan_stock"):
        assert want in names
    for want in ("get_analysis_packet", "get_data_coverage", "get_event_calendar",
                 "get_official_release_snapshot", "get_target_instrument_state",
                 "get_model_leaderboard", "get_forward_test_status", "get_analysis_archive_status"):
        assert want in names


# --- skills ---
def _skill_text(name: str) -> str:
    return (Path(__file__).resolve().parents[1] / "cherry_skills" / name / "SKILL.md").read_text(encoding="utf-8")


def test_osaka_skill_target():
    t = _skill_text("osaka-micro-analysis")
    assert "OSE Nikkei 225 Micro Futures" in t and "PROXY" in t


def test_taiwan_skill():
    t = _skill_text("taiwan-stock-v28")
    assert "get_analysis_packet" in t and "公司行動校正" in t


def test_model_audit_skill():
    t = _skill_text("model-validation-audit")
    assert "MASE" in t and "不得用" in t


# --- token benchmark ---
def test_token_benchmark(tmp_path, monkeypatch):
    root = _tmp_settlement_root(tmp_path)
    monkeypatch.setenv("MARKET_AI_DATA_ROOT", str(root))
    full = build_analysis_packet(market="osaka", detail_level="normal", save_analysis=False)
    bm = token_benchmark(full)
    assert bm["compact"]["mcp_calls"] == 1
    assert bm["old_style_workflow"]["mcp_calls"] > 1
    assert bm["compact"]["response_bytes"] <= bm["normal"]["response_bytes"]
    assert bm["reduction_vs_old_style"]["core_risk_preserved"] is True


# --- live smoke（§25）：大阪 packet 不依賴 TradingView/Yuanta ---
@pytest.mark.live
def test_live_smoke_osaka_packet():
    try:
        import httpx
        httpx.get("https://www.jpx.co.jp/", timeout=5)
    except Exception as e:  # noqa: BLE001
        pytest.skip(f"network unavailable: {e}")

    from market_ai_hub.targets.jpx_settlement import JPXSettlementProvider
    from market_ai_hub.targets.jpx_market_data import JPXMarketDataProvider

    d = "20260918"
    getter = lambda u: httpx.get(u, timeout=30, follow_redirects=True).content
    rows = JPXSettlementProvider().fetch_parse(d, getter=getter)
    assert any(r.product == "Nikkei 225 Micro Futures" for r in rows)
    vols = JPXMarketDataProvider().fetch_whole_day(d, getter=getter)
    assert any("Micro" in v.product for v in vols)

    # 建 packet（不依賴 TradingView/Yuanta）
    p = build_analysis_packet(market="osaka", detail_level="normal", save_analysis=False)
    assert p["execution_target"] == EXECUTION_TARGET
    assert p["target_data_status"] == "REFERENCE_AVAILABLE"  # V2-A.2: dated settlement != LIVE_VERIFIED
    assert p["reference_price_type"] == PRICE_TYPE_SETTLEMENT
