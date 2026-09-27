"""Fail-closed boundaries for optional open-source research frameworks.

These adapters are intentionally subprocess/file boundaries. Importing this module never
imports Qlib or NautilusTrader into the MARKET_AI_HUB core environment.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from market_ai_hub.config.settings import project_root
from market_ai_hub.config.runtime_paths import data_root


MANIFEST_PATH = project_root() / "config" / "open_source_research_adapters.yaml"
SCHEMA_VERSION = "OSSA.1"


class OpenSourceAdapterError(ValueError):
    pass


@dataclass(frozen=True)
class OpenSourceAdapterSpec:
    name: str
    raw: dict[str, Any]

    @property
    def executable_env(self) -> str:
        return str(self.raw.get("executable_env") or "")

    @property
    def configured_executable(self) -> Path | None:
        if self.executable_env:
            value = os.environ.get(self.executable_env, "").strip()
            if value:
                return Path(value)
        fallback = str(self.raw.get("default_data_root_relative_executable") or "").strip()
        return data_root() / Path(fallback) if fallback else None

    def status(self) -> dict[str, Any]:
        exe = self.configured_executable
        exists = bool(exe and exe.exists() and exe.is_file())
        manifest_status = self.raw.get("status")
        effective_status = "READY_TO_EXECUTE" if exists else manifest_status
        return {
            "name": self.name,
            "status": effective_status,
            "manifest_status": manifest_status,
            "integration_stage": self.raw.get("integration_stage"),
            "integration_mode": self.raw.get("integration_mode"),
            "core_venv_install_allowed": bool(self.raw.get("core_venv_install_allowed", False)),
            "live_execution_allowed": bool(self.raw.get("live_execution_allowed", False)),
            "serving_dependency_allowed": bool(self.raw.get("serving_dependency_allowed", False)),
            "configured_executable": str(exe) if exe else None,
            "configured_executable_exists": exists,
            "ready_to_execute": bool(exists and self.raw.get("integration_mode") == "ISOLATED_SUBPROCESS_FILE_CONTRACT"),
        }


def load_open_source_manifest(path: str | Path | None = None) -> dict[str, OpenSourceAdapterSpec]:
    p = Path(path) if path is not None else MANIFEST_PATH
    payload = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    if str(payload.get("schema_version")) != SCHEMA_VERSION:
        raise OpenSourceAdapterError("open-source adapter schema mismatch")
    adapters = payload.get("adapters") or {}
    if not isinstance(adapters, dict) or not adapters:
        raise OpenSourceAdapterError("open-source adapter manifest is empty")
    out: dict[str, OpenSourceAdapterSpec] = {}
    for name, raw in adapters.items():
        if not isinstance(raw, dict):
            raise OpenSourceAdapterError(f"adapter {name} is not an object")
        if raw.get("live_execution_allowed") is not False:
            raise OpenSourceAdapterError(f"adapter {name} may not enable live execution")
        if name in {"qlib", "nautilus_trader"}:
            if raw.get("core_venv_install_allowed") is not False:
                raise OpenSourceAdapterError(f"{name} must remain outside core venv")
            if raw.get("integration_mode") != "ISOLATED_SUBPROCESS_FILE_CONTRACT":
                raise OpenSourceAdapterError(f"{name} must use isolated subprocess/file contract")
        out[str(name)] = OpenSourceAdapterSpec(str(name), dict(raw))
    return out


def open_source_adapter_status(path: str | Path | None = None) -> dict[str, dict[str, Any]]:
    return {name: spec.status() for name, spec in load_open_source_manifest(path).items()}


def export_isolated_research_dataset(
    adapter: str,
    frame: pd.DataFrame,
    destination: str | Path,
    *,
    dataset_id: str,
    source_hash: str,
    protocol_hash: str,
    task: str,
) -> dict[str, Any]:
    """Write a content-addressed file bundle for an isolated research environment.

    No third-party framework is imported or executed. The recipient adapter must read
    this immutable parquet+manifest pair and return a separate result artifact.
    """
    specs = load_open_source_manifest()
    if adapter not in specs:
        raise KeyError(adapter)
    spec = specs[adapter]
    if spec.raw.get("integration_mode") != "ISOLATED_SUBPROCESS_FILE_CONTRACT":
        raise OpenSourceAdapterError(f"{adapter} is not an isolated adapter")
    if frame.empty:
        raise OpenSourceAdapterError("research dataset cannot be empty")
    if not dataset_id or not source_hash or not protocol_hash or not task:
        raise OpenSourceAdapterError("dataset identity/provenance/task are required")

    root = Path(destination)
    root.mkdir(parents=True, exist_ok=True)
    parquet_path = root / f"{dataset_id}.parquet"
    frame.to_parquet(parquet_path, index=False)
    content_hash = hashlib.sha256(parquet_path.read_bytes()).hexdigest()
    manifest = {
        "schema_version": "OSSA.DATASET.1",
        "adapter": adapter,
        "upstream": spec.raw.get("upstream"),
        "release": spec.raw.get("release") or spec.raw.get("selected_release"),
        "commit": spec.raw.get("release_commit") or spec.raw.get("selected_commit"),
        "dataset_id": dataset_id,
        "source_hash": source_hash,
        "protocol_hash": protocol_hash,
        "task": task,
        "row_count": int(len(frame)),
        "columns": [str(x) for x in frame.columns],
        "parquet_sha256": content_hash,
        "live_execution_allowed": False,
        "orders_allowed": False,
        "serving_dependency_allowed": False,
    }
    manifest_path = root / f"{dataset_id}.manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, indent=2),
        encoding="utf-8",
    )
    return {
        **manifest,
        "parquet_path": str(parquet_path),
        "manifest_path": str(manifest_path),
    }
