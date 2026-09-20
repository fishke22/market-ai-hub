"""Phase 2Q-C — primary target registry loader（config/primary_targets.yaml）。

三大 first-class families：OSAKA_MICRO / TAIWAN_STOCK / TAIWAN_INDEX。
forecast target != execution instrument；不 hardcode 私人資料路徑。
"""
from __future__ import annotations

from pathlib import Path

import yaml

from market_ai_hub.config.settings import project_root

_PRIMARY_TARGETS_PATH = project_root() / "config" / "primary_targets.yaml"

TARGET_FAMILIES = ("OSAKA_MICRO", "TAIWAN_STOCK", "TAIWAN_INDEX")


def load_primary_targets() -> dict:
    data = yaml.safe_load(_PRIMARY_TARGETS_PATH.read_text(encoding="utf-8"))
    return data


def target_families() -> list[str]:
    return list(TARGET_FAMILIES)


def targets_of(family: str) -> list[dict]:
    return [t for t in load_primary_targets()["targets"] if t["target_family"] == family]


def resolve_target(target: str) -> dict | None:
    for t in load_primary_targets()["targets"]:
        if t["target"] == target or t.get("symbol") == target:
            return t
    return None


def execution_instrument_of(target: str) -> str | None:
    t = resolve_target(target)
    return t.get("execution_instrument") if t else None
