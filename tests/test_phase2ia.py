"""Phase 2I-A — performance + accuracy hardening tests。"""
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, "src")

from market_ai_hub.packet.builder import (
    _cached,
    _load_latest_micro_settlement,
    build_analysis_packet,
    clear_caches,
)
from market_ai_hub.packet.context import AnalysisExecutionContext
from market_ai_hub.packet.schema import PRICE_TYPE_SETTLEMENT
from market_ai_hub.services.model_runtime_manager import ModelRuntimeManager, VRAMPressureError
from market_ai_hub.services.data_consistency import DataConsistencyValidator
from market_ai_hub.services.cross_source import DATA_CONFLICT, cross_source_check
from market_ai_hub.targets.contract import TARGET, role_of
from market_ai_hub.automation.incremental import dedupe_and_write, missing_ranges


def _tmp_settlement_root(tmp_path) -> Path:
    root = tmp_path / "data"
    dest = root / "raw" / "jpx" / "settlement" / "OSE" / "all" / "2026" / "09"
    dest.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame([{
        "product": "Nikkei 225 Micro Futures", "contract": "202612",
        "settlement_price": 65100.0, "final_settlement_price": None, "date": "20260918",
        "source_url": "x", "source_hash": "h",
    }])
    df.to_parquet(dest / "rb20260918.parquet", index=False)
    return root


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """stub 掉 yfinance 網路（packet build 快 + deterministic）。"""
    import market_ai_hub.packet.builder as b

    def panel():
        idx = pd.date_range("2024-01-01", periods=300, freq="B", tz="UTC")
        base = 39000.0 + pd.Series(range(300), dtype=float)
        return pd.DataFrame({
            "^N225": base,
            "^VIX": 15.0 + pd.Series([0.0] * 300, dtype=float),
            "US10Y": 4.0 + pd.Series([0.0] * 300, dtype=float),
            "USDJPY=X": 150.0 + pd.Series([0.0] * 300, dtype=float),
        }, index=idx)

    monkeypatch.setattr(b, "_regime_panel", panel)
    monkeypatch.setattr(b, "_proxy_reference", lambda: None)


# --- 2: data fetch optimization ---
def test_request_dedup():
    cache: dict = {}
    assert _cached("k", cache, ttl=300) is None
    cache["k"] = (time.time(), "v")
    assert _cached("k", cache, ttl=300) == "v"


def test_datalake_cache_reuse(tmp_path, monkeypatch):
    monkeypatch.setenv("MARKET_AI_DATA_ROOT", str(_tmp_settlement_root(tmp_path)))
    clear_caches()
    a = _load_latest_micro_settlement()
    b = _load_latest_micro_settlement()  # cache hit
    assert a == b and b["price_type"] == PRICE_TYPE_SETTLEMENT


def test_stale_cache_rejection():
    cache: dict = {}
    cache["k"] = (time.time() - 1000, "old")
    assert _cached("k", cache, ttl=300) is None  # TTL 過期 → 不重用


# --- 3: shared execution context ---
def test_shared_execution_context():
    ctx = AnalysisExecutionContext()
    ctx.set_panel(pd.DataFrame({"a": [1, 2, 3]}))
    s1 = ctx.feature_snapshot()
    s2 = ctx.feature_snapshot()
    assert s1 is s2  # memoized，不重算


# --- 4: feature incremental update ---
def test_feature_incremental_update():
    gaps = missing_ranges(("2024-01-10", "2024-01-20"), ("2024-01-01", "2024-01-31"))
    assert gaps == [("2024-01-01", "2024-01-09"), ("2024-01-21", "2024-01-31")]
    # 已覆蓋區段不重抓
    assert missing_ranges(("2024-01-01", "2024-01-31"), ("2024-01-05", "2024-01-10")) == []


# --- 5/6/7: model runtime ---
def _fake_loader(name):
    def _load():
        return {"model": name}
    return _load


def test_model_lazy_load():
    m = ModelRuntimeManager()
    m.get("chronos", _fake_loader("chronos"), vram_estimate_mb=2000)
    assert m.load_count == 1 and m.cache_hits == 0


def test_model_reuse():
    m = ModelRuntimeManager()
    m.get("chronos", _fake_loader("chronos"), vram_estimate_mb=2000)
    m.get("chronos", _fake_loader("chronos"), vram_estimate_mb=2000)  # reuse
    assert m.load_count == 1 and m.cache_hits == 1


def test_gpu_memory_guard():
    m = ModelRuntimeManager(vram_budget_mb=10000)
    m.get("a", _fake_loader("a"), vram_estimate_mb=6000)
    m.get("b", _fake_loader("b"), vram_estimate_mb=3000)
    with pytest.raises(VRAMPressureError):
        m.get("c", _fake_loader("c"), vram_estimate_mb=3000)  # 超出預算


# --- 8: duckdb filtered read ---
def test_duckdb_filtered_read(tmp_path):
    from market_ai_hub.automation.archive import AnalysisArchive, AnalysisRecord, AnalysisOutcome
    a = AnalysisArchive(tmp_path)
    a.save(AnalysisRecord(analysis_id="A1", information_cutoff="2024-06-01T00:00:00+00:00"))
    a.save(AnalysisRecord(analysis_id="A2", information_cutoff="2024-06-02T00:00:00+00:00"))
    a.settle(AnalysisOutcome(analysis_id="A1", actual_close=100, actual_high=101, actual_low=99,
                             center_absolute_error=1.0, direction_hit=True, core_range_hit=True))
    # 只回 unsettled（filtered，非 SELECT * 全表）
    assert a.unsettled_ids() == ["A2"]


# --- 9/10: cross-source + consistency ---
def test_data_conflict_detection():
    r = cross_source_check("VIX", authoritative=15.0, proxy=25.0, threshold=0.05)
    assert r["status"] == DATA_CONFLICT


def test_settlement_semantics():
    v = DataConsistencyValidator()
    s = pd.Series([100.0, 101.0, 102.0])
    c = pd.Series([100.0, 101.0, 102.0])  # 全等 → 可能是 settlement 被當 close
    rep = v.validate_settlement_semantics(s, c)
    assert any("SETTLEMENT" in i for i in rep.issues)


def test_consistency_validator():
    v = DataConsistencyValidator()
    df = pd.DataFrame({"timestamp": pd.date_range("2024-01-01", periods=5),
                       "close": [100.0, -5.0, 102.0, 103.0, 104.0]})
    rep = v.validate_bars(df)
    assert any("non-positive" in i for i in rep.issues)


# --- 12: target/proxy separation ---
def test_target_proxy_separation():
    assert role_of("^N225") != TARGET
    assert role_of("OSE_NIKKEI225_MICRO_FUTURES") == TARGET


# --- 13: compact lazy compute ---
def test_packet_compact_lazy_compute(tmp_path, monkeypatch):
    monkeypatch.setenv("MARKET_AI_DATA_ROOT", str(_tmp_settlement_root(tmp_path)))
    compact = build_analysis_packet(market="osaka", detail_level="compact", save_analysis=False)
    audit = build_analysis_packet(market="osaka", detail_level="audit", save_analysis=False)
    assert len(compact["data_coverage_summary"]) <= len(audit["data_coverage_summary"])
    assert compact["data_coverage_summary"]  # 仍保留關鍵覆蓋


# --- 14: failure isolation ---
def test_failure_isolation(tmp_path, monkeypatch):
    monkeypatch.setenv("MARKET_AI_DATA_ROOT", str(_tmp_settlement_root(tmp_path)))

    def boom():
        raise RuntimeError("provider down")

    import market_ai_hub.packet.builder as b
    orig = b._regime_panel
    b._regime_panel = boom
    try:
        p = build_analysis_packet(market="osaka", detail_level="normal", save_analysis=False)
        assert p["execution_target"] == "OSE_NIKKEI225_MICRO_FUTURES"
        assert p["regime"].get("status") == "ERROR" or "INSUFFICIENT" in str(p["regime"])
    finally:
        b._regime_panel = orig


# --- 15: optimization output equivalence ---
def test_optimization_output_equivalence(tmp_path, monkeypatch):
    monkeypatch.setenv("MARKET_AI_DATA_ROOT", str(_tmp_settlement_root(tmp_path)))
    clear_caches()
    cold = build_analysis_packet(market="osaka", detail_level="normal", save_analysis=False)
    warm = build_analysis_packet(market="osaka", detail_level="normal", save_analysis=False)
    for k in ("execution_target", "reference_price", "reference_price_type",
              "ensemble_validation", "strategy_research_state", "target_data_status"):
        assert cold[k] == warm[k]
