"""Phase 2D tournament package."""

from __future__ import annotations

from pathlib import Path

import yaml

from market_ai_hub.config.settings import project_root


def load_model_registry() -> dict:
    p = project_root() / "config" / "model_registry.yaml"
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f)


def get_model_entry(name: str) -> dict:
    reg = load_model_registry()
    for m in reg["models"]:
        if m["name"] == name:
            return m
    raise KeyError(name)
