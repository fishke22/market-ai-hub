"""Phase 2Q-C.1 — product spec truth + data root hygiene + filesystem side-effect tests."""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, "src")
ROOT = Path(__file__).resolve().parents[1]


# ── §1/§2 product spec truth ──

def test_ose_micro_multiplier_is_10():
    import yaml

    data = yaml.safe_load((ROOT / "config" / "primary_targets.yaml").read_text(encoding="utf-8"))
    ose = next(t for t in data["targets"] if t["target"] == "OSE_NIKKEI225_MICRO_FUTURES")
    assert ose["multiplier_if_applicable"] == 10
    assert ose["tick_size_if_applicable"] == 5


def test_taiwan_index_multipliers():
    import yaml

    data = yaml.safe_load((ROOT / "config" / "primary_targets.yaml").read_text(encoding="utf-8"))
    by_target = {t["target"]: t for t in data["targets"]}
    assert by_target["TX"]["multiplier_if_applicable"] == 200
    assert by_target["MTX"]["multiplier_if_applicable"] == 50
    assert by_target["TMF"]["multiplier_if_applicable"] == 10


def test_ose_micro_notional_sanity():
    # 65,000 × 10 = 650,000 JPY（不得 6,500,000）
    price = 65_000
    multiplier = 10
    assert price * multiplier == 650_000


def test_contract_spec_verified_not_guessed():
    from market_ai_hub.services.primary_targets import targets_of

    # 只檢查可成交 futures（TAIEX 是 cash index，multiplier 合法為 null）
    futures = [t for t in targets_of("OSAKA_MICRO") + targets_of("TAIWAN_INDEX")
               if t["instrument_type"] != "cash_index"]
    for t in futures:
        assert t["multiplier_if_applicable"] is not None, f"{t['target']} multiplier must be set"


# ── §3/§4 data root resolver ──

def test_data_root_env_override(monkeypatch, tmp_path):
    from market_ai_hub.config import runtime_paths as rp

    monkeypatch.setenv("MARKET_AI_DATA_ROOT", str(tmp_path))
    assert rp.data_root() == tmp_path
    assert rp.private_inbox_dir() == tmp_path / "private" / "inbox" / "225labo"
    assert rp.raw_archive_dir() == tmp_path / "raw" / "ylab225" / "archive"


def test_data_root_default_is_project_data(monkeypatch):
    from market_ai_hub.config import runtime_paths as rp

    monkeypatch.delenv("MARKET_AI_DATA_ROOT", raising=False)
    assert rp.data_root() == ROOT / "data"


def test_data_root_no_hardcoded_drive_root():
    from market_ai_hub.config import runtime_paths as rp

    # resolver 產生的路徑不得含 D:\ 或 C:\ drive-root sibling 資料夾
    for d in (rp.private_inbox_dir(), rp.raw_archive_dir(), rp.normalized_ose_micro_dir()):
        s = str(d)
        assert "MARKET_AI_HUB_PRIVATE_INBOX" not in s
        assert not s.startswith(("D:\\MARKET_AI_HUB_PRIVATE_INBOX", "C:\\MARKET_AI_HUB_"))


# ── §5 no filesystem side effect on import ──

def test_import_has_no_filesystem_side_effect(monkeypatch, tmp_path):
    from market_ai_hub.config import runtime_paths as rp

    monkeypatch.setenv("MARKET_AI_DATA_ROOT", str(tmp_path))
    import market_ai_hub.data.ylab225_ingest as ing  # noqa: F401

    # import 後不應建立任何 directory
    assert not rp.private_inbox_dir().exists()
    assert not rp.raw_archive_dir().exists()
    assert not rp.normalized_ose_micro_dir().exists()


def test_coverage_has_no_filesystem_side_effect(monkeypatch, tmp_path):
    from market_ai_hub.config import runtime_paths as rp
    import market_ai_hub.data.ylab225_ingest as ing

    monkeypatch.setenv("MARKET_AI_DATA_ROOT", str(tmp_path))
    cov = ing.coverage_summary()
    assert cov["freshness"] in ("MISSING_CURRENT_SESSION", "STALE")
    # 讀 coverage 不應建立 directory
    assert not rp.private_inbox_dir().exists()


def test_missing_inbox_does_not_pollute_drive_root(monkeypatch, tmp_path):
    import market_ai_hub.data.ylab225_ingest as ing

    monkeypatch.setenv("MARKET_AI_DATA_ROOT", str(tmp_path))
    r = ing.ingest_from_inbox()  # 空 inbox → 建立 tmp data root 下的目錄，不建 D:\
    assert r["imported"] == []
    # 建立的目錄必須在 tmp data root 下（resolver 產生），非 hardcode D:\
    assert (tmp_path / "private" / "inbox" / "225labo").exists()
    assert (tmp_path / "raw" / "ylab225" / "archive").exists()


# ── §9 legacy detection ──

def test_legacy_inbox_detected(monkeypatch, tmp_path):
    from market_ai_hub.config import runtime_paths as rp

    legacy = tmp_path / "legacy_inbox"
    legacy.mkdir(parents=True)
    monkeypatch.setattr(rp, "LEGACY_PRIVATE_INBOX", legacy)
    assert rp.legacy_inbox_status() == "LEGACY_EMPTY_INBOX"


def test_legacy_nonempty_not_deleted(monkeypatch, tmp_path):
    from market_ai_hub.config import runtime_paths as rp

    legacy = tmp_path / "legacy_inbox"
    legacy.mkdir(parents=True)
    (legacy / "data.zip").write_bytes(b"x")
    monkeypatch.setattr(rp, "LEGACY_PRIVATE_INBOX", legacy)
    assert rp.legacy_inbox_status() == "LEGACY_PRIVATE_DATA_FOUND"
    # 不得自動刪除有資料的 legacy
    assert legacy.exists() and (legacy / "data.zip").exists()


def test_legacy_empty_safe_cleanup(monkeypatch, tmp_path):
    from market_ai_hub.config import runtime_paths as rp

    legacy = tmp_path / "legacy_inbox"
    legacy.mkdir(parents=True)
    monkeypatch.setattr(rp, "LEGACY_PRIVATE_INBOX", legacy)
    assert rp.legacy_inbox_status() == "LEGACY_EMPTY_INBOX"
    # empty 才可安全移除（由 operator 執行，resolver 只回狀態不刪除）
    legacy.rmdir()
    assert not legacy.exists()


# ── §11/§30 private data never git candidate ──

def test_private_data_never_git_candidate():
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    manifest = (ROOT / "research/phase2/publication/PUBLICATION_EXCLUDE_MANIFEST.txt").read_text(encoding="utf-8")
    combined = gitignore + "\n" + manifest
    # private inbox / raw / normalized 必須被排除，且不再硬編 D:\
    assert "data/private/" in combined or "data\\private\\" in combined
    assert "data/raw/" in combined or "data\\raw\\" in combined
    assert "data/normalized/" in combined or "data\\normalized\\" in combined
    assert "MARKET_AI_HUB_PRIVATE_INBOX" not in manifest  # 已移除 hardcode D:\


def test_ps1_uses_resolver_not_hardcoded():
    ps1 = (ROOT / "scripts" / "import_latest_225labo_micro.ps1").read_text(encoding="utf-8")
    assert "MARKET_AI_HUB_PRIVATE_INBOX" not in ps1
    assert "runtime_paths" in ps1


def test_env_example_has_data_root():
    env = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "MARKET_AI_DATA_ROOT" in env
