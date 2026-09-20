"""Phase 2Q-D — performance engineering correctness tests（build identity / shallow health / cache / n_jobs）。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, "src")
ROOT = Path(__file__).resolve().parents[1]


# ── §4 build identity ──

def test_build_identity_changes_on_runtime_source_change(tmp_path, monkeypatch):
    import market_ai_hub.services.build_info as bi

    fake_root = tmp_path
    src = fake_root / "src" / "market_ai_hub"
    (src / "services").mkdir(parents=True)
    (src / "services" / "a.py").write_text("x=1\n")
    monkeypatch.setattr(bi, "SOURCE_ROOT", fake_root)
    id1 = bi._compute_build_id()
    (src / "services" / "a.py").write_text("x=2\n")
    id2 = bi._compute_build_id()
    assert id1 != id2


def test_build_identity_changes_on_runtime_config_change(tmp_path, monkeypatch):
    import market_ai_hub.services.build_info as bi

    fake_root = tmp_path
    src = fake_root / "src" / "market_ai_hub"
    (src / "services").mkdir(parents=True)
    (src / "services" / "a.py").write_text("x=1\n")
    cfg = fake_root / "config"
    cfg.mkdir(parents=True)
    (cfg / "primary_targets.yaml").write_text("a: 1\n")
    monkeypatch.setattr(bi, "SOURCE_ROOT", fake_root)
    id1 = bi._compute_build_id()
    (cfg / "primary_targets.yaml").write_text("a: 2\n")
    id2 = bi._compute_build_id()
    assert id1 != id2


def test_docs_change_does_not_change_runtime_build(tmp_path, monkeypatch):
    import market_ai_hub.services.build_info as bi

    fake_root = tmp_path
    src = fake_root / "src" / "market_ai_hub"
    (src / "services").mkdir(parents=True)
    (src / "services" / "a.py").write_text("x=1\n")
    monkeypatch.setattr(bi, "SOURCE_ROOT", fake_root)
    id1 = bi._compute_build_id()
    # docs 改變不影響 runtime build（docs 不在 fingerprint 路徑）
    (fake_root / "docs").mkdir(exist_ok=True)
    (fake_root / "docs" / "note.md").write_text("hello\n")
    id2 = bi._compute_build_id()
    assert id1 == id2


# ── §45 shallow health no heavy load ──

def test_health_does_not_load_chronos(monkeypatch):
    import market_ai_hub.mcp.server as s
    import market_ai_hub.models.chronos_model as cm

    called = {"n": 0}

    def _boom_load(self):
        called["n"] += 1
        raise AssertionError("health_check 不得 load chronos")

    monkeypatch.setattr(cm.ChronosAdapter, "load", _boom_load)
    h = s.health_check()
    assert called["n"] == 0
    assert h["chronos"] == "AVAILABLE_NOT_LOADED"


def test_health_does_not_load_timesfm(monkeypatch):
    import market_ai_hub.mcp.server as s
    import market_ai_hub.models.timesfm_model as tm

    called = {"n": 0}

    def _boom_load(self):
        called["n"] += 1
        raise AssertionError("health_check 不得 load timesfm")

    monkeypatch.setattr(tm.TimesFM3Adapter, "load", _boom_load)
    h = s.health_check()
    assert called["n"] == 0
    assert h["timesfm"] == "AVAILABLE_NOT_LOADED"


def test_system_info_does_not_load_heavy_models(monkeypatch):
    import market_ai_hub.mcp.server as s
    import market_ai_hub.models.chronos_model as cm
    import market_ai_hub.models.timesfm_model as tm

    called = {"n": 0}

    def _boom(self):
        called["n"] += 1
        raise AssertionError("get_system_info 不得 load model")

    monkeypatch.setattr(cm.ChronosAdapter, "load", _boom)
    monkeypatch.setattr(tm.TimesFM3Adapter, "load", _boom)
    s.get_system_info()
    assert called["n"] == 0


def test_research_gates_does_not_load_heavy_models(monkeypatch):
    import market_ai_hub.mcp.server as s
    import market_ai_hub.models.chronos_model as cm
    import market_ai_hub.models.timesfm_model as tm

    called = {"n": 0}

    def _boom(self):
        called["n"] += 1
        raise AssertionError("get_research_gates 不得 load model")

    monkeypatch.setattr(cm.ChronosAdapter, "load", _boom)
    monkeypatch.setattr(tm.TimesFM3Adapter, "load", _boom)
    s.get_research_gates()
    assert called["n"] == 0


def test_model_runtime_singleton_no_reload():
    from market_ai_hub.services import model_runtime as mr

    a = mr.get_chronos()
    b = mr.get_chronos()
    assert a is b  # same process 同一 instance，不 reload


# ── §44 cache correctness ──

def test_fit_cache_data_change_invalidates():
    import numpy as np
    import pandas as pd

    from market_ai_hub.services.fit_cache import fit_cache_key

    df1 = pd.DataFrame({"close": np.arange(300.0)})
    df2 = pd.DataFrame({"close": np.arange(300.0) + 1.0})
    k1 = fit_cache_key("xgb", "3706.TW", "1d", df1)
    k2 = fit_cache_key("xgb", "3706.TW", "1d", df2)
    assert k1 != k2  # 資料變 → key 變 → invalidates


def test_fit_cache_same_data_same_key():
    import numpy as np
    import pandas as pd

    from market_ai_hub.services.fit_cache import fit_cache_key

    df = pd.DataFrame({"close": np.arange(300.0)})
    assert fit_cache_key("xgb", "3706.TW", "1d", df) == fit_cache_key("xgb", "3706.TW", "1d", df)


def test_forecast_cache_model_revision_invalidates():
    from market_ai_hub.services.forecast_cache import forecast_cache_key

    closes = __import__("pandas").Series([100.0] * 100)
    k1 = forecast_cache_key("chronos-2", "^N225", "1d", closes, "buildA")
    k2 = forecast_cache_key("chronos-2", "^N225", "1d", closes, "buildB")
    assert k1 != k2  # build/revision 變 → invalidates


def test_interactive_n_jobs_bounded():
    from market_ai_hub.services.resource_governor import interactive_n_jobs

    n = interactive_n_jobs()
    assert 1 <= n <= 4  # bounded，非 -1（unbounded）


# ── §42 correctness equivalence：packet reference price 不因 optimization 改變語義 ──

def test_packet_reference_routing_unchanged_semantics():
    from market_ai_hub.packet.builder import build_analysis_packet

    p = build_analysis_packet(market="osaka", target="OSE_NIKKEI225_MICRO_FUTURES",
                              detail_level="compact", save_analysis=False)
    assert p["exchange"] == "OSE"
    assert "target_semantics" in p
    assert p["target_semantics"]["direct_target"] == "OSE_NIKKEI225_MICRO_FUTURES"
