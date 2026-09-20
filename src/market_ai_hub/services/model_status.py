"""Phase 2Q-D — lightweight model status（不 import torch / 不 load weights）。

health / system_info / gates 用之。只查 package installability（find_spec）
與 model cache/checkpoint presence。不得 import torch / numpy / 模型模組。
"""
from __future__ import annotations

import importlib.util

from market_ai_hub.config.settings import project_root

MODEL_SPECS = {
    "chronos": {"package": "chronos", "cache": "models/cache/chronos-2"},
    "timesfm": {"package": "timesfm3", "cache": "models/cache/timesfm-3.0"},
}


def shallow_status(name: str) -> str:
    """AVAILABLE_NOT_LOADED / UNAVAILABLE（不 load）。"""
    spec = MODEL_SPECS.get(name)
    if spec is None:
        return "UNKNOWN"
    pkg_ok = importlib.util.find_spec(spec["package"]) is not None
    cache = project_root() / spec["cache"]
    cache_ok = cache.exists() and any(cache.rglob("*"))
    if pkg_ok or cache_ok:
        return "AVAILABLE_NOT_LOADED"
    return "UNAVAILABLE"


def torch_installed() -> bool:
    return importlib.util.find_spec("torch") is not None
