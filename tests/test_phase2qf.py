"""Phase 2Q-F — runtime output routing + workspace hygiene tests。"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, "src")
ROOT = Path(__file__).resolve().parents[1]


def test_runtime_outputs_not_project_root(monkeypatch, tmp_path):
    from market_ai_hub.config import runtime_paths as rp

    monkeypatch.setenv("MARKET_AI_DATA_ROOT", str(tmp_path))
    # 所有 runtime output 目錄都在 DATA_ROOT 下，不是 project root
    assert rp.forward_outputs_root().is_relative_to(tmp_path)
    assert rp.status_outputs_root().is_relative_to(tmp_path)
    assert rp.performance_outputs_root().is_relative_to(tmp_path)
    assert rp.diagnostics_root().is_relative_to(tmp_path)
    assert rp.lightning_logs_root().is_relative_to(tmp_path)
    assert rp.db_root().is_relative_to(tmp_path)


def test_resource_governor_status_not_root(monkeypatch, tmp_path):
    from market_ai_hub.services.resource_governor import ResourceGovernor

    monkeypatch.setenv("MARKET_AI_DATA_ROOT", str(tmp_path))
    rg = ResourceGovernor.__new__(ResourceGovernor)
    rg._status_path = None
    # 重建 status path（經 resolver）
    from market_ai_hub.config.runtime_paths import status_outputs_root

    assert str(status_outputs_root()).startswith(str(tmp_path))


def test_forward_summary_not_root(monkeypatch, tmp_path):
    from market_ai_hub.data import ylab225_ingest as ing

    monkeypatch.setenv("MARKET_AI_DATA_ROOT", str(tmp_path))
    cov = {"freshness": "STALE", "last_bar_date": None}
    created = {"status": "FORECAST_SKIPPED_DATA_QUALITY"}
    settled = {"settled": []}
    status = {"forecasts_created": 0, "settled": 0, "pending": 0}
    out = ing.write_daily_summary(cov, created, settled, status)
    assert "# FORWARD DAILY SUMMARY" in out
    # 輸出檔在 DATA_ROOT/research_outputs/forward/，不是 project root
    assert (tmp_path / "research_outputs" / "forward" / "FORWARD_DAILY_SUMMARY.md").exists()
    assert not (ROOT / "FORWARD_DAILY_SUMMARY.md").exists()


def test_system_manifest_no_osaka_only_singular_primary():
    import yaml

    d = yaml.safe_load((ROOT / "config" / "system_manifest.yaml").read_text(encoding="utf-8"))
    assert "first_class_targets" in d
    assert set(d["first_class_targets"]) == {"OSAKA_MICRO", "TAIWAN_STOCK", "TAIWAN_INDEX"}
    # 不得有 global singular primary
    assert "targets" not in d or "primary" not in d.get("targets", {})


def test_lightning_logs_root_resolver(monkeypatch, tmp_path):
    from market_ai_hub.config import runtime_paths as rp

    monkeypatch.setenv("MARKET_AI_DATA_ROOT", str(tmp_path))
    assert rp.lightning_logs_root() == tmp_path / "logs" / "lightning"
