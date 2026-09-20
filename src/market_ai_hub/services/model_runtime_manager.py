"""Phase 2I-A — ModelRuntimeManager（lazy load + reuse + VRAM pressure policy）。

Heavy models 不得 MCP 啟動時全部載入 GPU。同 process 重複分析應重用已載 model。
16GB RTX 4060 Ti：禁止多個大型 foundation models 無限制常駐。
OOM → graceful fallback（VRAMPressureError）。
"""
from __future__ import annotations

import threading
from typing import Callable


class VRAMPressureError(Exception):
    """載入會超過 VRAM 預算 → 由呼叫方 graceful fallback。"""


class ModelRuntimeManager:
    def __init__(self, vram_budget_mb: float = 12000.0) -> None:
        self._models: dict[str, object] = {}
        self._vram: dict[str, float] = {}
        self._lock = threading.RLock()  # reentrant：current_vram_mb 於 get 內呼叫
        self.vram_budget_mb = vram_budget_mb
        self.load_count = 0
        self.cache_hits = 0

    def current_vram_mb(self) -> float:
        with self._lock:
            return sum(self._vram.values())

    def get(self, name: str, loader: Callable[[], object], vram_estimate_mb: float = 0.0) -> object:
        """lazy load + 重用；超過 VRAM 預算 → VRAMPressureError（不硬塞 GPU）。"""
        with self._lock:
            if name in self._models:
                self.cache_hits += 1
                return self._models[name]
            if vram_estimate_mb > 0 and self.current_vram_mb() + vram_estimate_mb > self.vram_budget_mb:
                raise VRAMPressureError(
                    f"{name} needs {vram_estimate_mb}MB but only "
                    f"{self.vram_budget_mb - self.current_vram_mb():.0f}MB left"
                )
            model = loader()
            self._models[name] = model
            self._vram[name] = vram_estimate_mb
            self.load_count += 1
            return model

    def stats(self) -> dict:
        with self._lock:
            return {
                "load_count": self.load_count,
                "cache_hits": self.cache_hits,
                "resident_models": list(self._models.keys()),
                "vram_used_mb": self.current_vram_mb(),
                "vram_budget_mb": self.vram_budget_mb,
            }


# 全域 singleton（與 model_runtime 一致，供統計）
GLOBAL_MANAGER = ModelRuntimeManager()
