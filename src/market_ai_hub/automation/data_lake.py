"""Phase 2E — Smart Data Lake（DataLakeManager + Manifest）。"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

DATA_ROOT_ENV = "MARKET_AI_DATA_ROOT"
LEGACY_DATA_ROOT_ENV = "MARKET_AI_HUB_DATA_ROOT"

SUB_DIRS = ["raw", "normalized", "features", "predictions", "analysis_archive", "cache", "manifests"]


class DataManifest(BaseModel):
    provider: str
    dataset: str
    instrument: str
    frequency: str
    start: str
    end: str
    row_count: int
    source: str
    source_hash: str
    downloaded_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    available_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    schema_version: str = "1"


def default_data_root() -> Path:
    """Use the canonical runtime path resolver; legacy env is migration-only fallback."""
    from market_ai_hub.config.runtime_paths import data_root
    from market_ai_hub.config.settings import project_root

    canonical = os.environ.get(DATA_ROOT_ENV, "").strip()
    if canonical:
        return data_root()
    legacy = os.environ.get(LEGACY_DATA_ROOT_ENV, "").strip()
    if legacy:
        p = Path(legacy).expanduser()
        return p if p.is_absolute() else project_root() / p
    return data_root()


class DataLakeManager:
    """統一 data lake。data_root 可設定（未來大量 tick 可搬其他磁碟）。"""

    def __init__(self, data_root: Path | None = None) -> None:
        self.root = data_root or default_data_root()
        for d in SUB_DIRS:
            (self.root / d).mkdir(parents=True, exist_ok=True)

    def raw_path(self, provider: str, dataset: str, market: str, instrument: str,
                 year: int, month: int, filename: str) -> Path:
        p = self.root / "raw" / provider / dataset / market / instrument / f"{year:04d}" / f"{month:02d}"
        p.mkdir(parents=True, exist_ok=True)
        return p / filename

    def manifest_path(self, provider: str, dataset: str, instrument: str) -> Path:
        p = self.root / "manifests" / provider / dataset
        p.mkdir(parents=True, exist_ok=True)
        return p / f"{instrument}.json"

    def save_manifest(self, m: DataManifest) -> Path:
        p = self.manifest_path(m.provider, m.dataset, m.instrument)
        p.write_text(m.model_dump_json(indent=2), encoding="utf-8")
        return p

    def load_manifest(self, provider: str, dataset: str, instrument: str) -> DataManifest | None:
        p = self.manifest_path(provider, dataset, instrument)
        if not p.exists():
            return None
        return DataManifest(**json.loads(p.read_text(encoding="utf-8")))

    def coverage(self, provider: str, dataset: str, instrument: str) -> tuple[str, str] | None:
        m = self.load_manifest(provider, dataset, instrument)
        if m is None:
            return None
        return (m.start, m.end)


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
