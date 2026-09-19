"""V1.1 runtime identity + build fingerprint tests。"""
import pytest

from market_ai_hub.services.build_info import (
    BUILD_ID,
    MARKET_AI_VERSION,
    SCHEMA_VERSION,
    SOURCE_ROOT,
    build_fingerprint,
)


def test_fingerprint_fields():
    fp = build_fingerprint()
    for k in ("market_ai_version", "build_id", "git_commit", "source_root",
              "python_executable", "server_started_at", "schema_version"):
        assert k in fp, k
        assert fp[k], f"{k} empty"


def test_source_root_is_market_ai_hub():
    # portable: source_root must be a real dir containing the package (not a hardcoded path)
    assert (SOURCE_ROOT / "src" / "market_ai_hub").exists()
    assert SOURCE_ROOT.name == "MARKET_AI_HUB" or (SOURCE_ROOT / "pyproject.toml").exists()


def test_build_id_stable_within_process():
    assert build_fingerprint()["build_id"] == BUILD_ID


def test_build_id_changes_when_source_changes(tmp_path, monkeypatch):
    """build_id 由 source 內容 hash 產生：檔案內容變 → id 變。"""
    import market_ai_hub.services.build_info as bi

    fake_root = tmp_path / "src" / "market_ai_hub"
    fake_root.mkdir(parents=True)
    (fake_root / "mcp").mkdir()
    (fake_root / "mcp" / "server.py").write_text("x=1\n")
    (fake_root / "services").mkdir()
    (fake_root / "services" / "analysis.py").write_text("y=2\n")
    monkeypatch.setattr(bi, "SOURCE_ROOT", tmp_path)
    id1 = bi._compute_build_id()
    (fake_root / "mcp" / "server.py").write_text("x=2\n")
    id2 = bi._compute_build_id()
    assert id1 != id2


def test_forecast_output_carries_build():
    import numpy as np
    import pandas as pd

    from market_ai_hub.models.chronos_model import chronos_forecast
    from tests.test_horizon_integrity import FakeChronosAdapter as FC

    closes = pd.Series(100 + np.sin(np.arange(50) / 8), index=pd.date_range("2026-09-01", periods=50, freq="B", tz="UTC"))
    fo = chronos_forecast(FC(), "X", closes, horizon="1d", horizon_steps=1)
    d = fo.model_dump()
    assert d["market_ai_version"] == MARKET_AI_VERSION
    assert d["build_id"] == BUILD_ID
    assert d["schema_version"] == SCHEMA_VERSION
    assert d["python_executable"]
