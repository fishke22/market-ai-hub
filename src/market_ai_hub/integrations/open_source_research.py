"""Fail-closed boundaries for optional open-source research frameworks.

These adapters are intentionally subprocess/file boundaries. Importing this module never
imports Qlib or NautilusTrader into the MARKET_AI_HUB core environment.
"""
from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any

import yaml

from market_ai_hub.config.settings import project_root


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
        if not self.executable_env:
            return None
        value = os.environ.get(self.executable_env, "").strip()
        return Path(value) if value else None

    def status(self) -> dict[str, Any]:
        exe = self.configured_executable
        exists = bool(exe and exe.exists() and exe.is_file())
        return {
            "name": self.name,
            "status": self.raw.get("status"),
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
