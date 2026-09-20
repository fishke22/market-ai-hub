"""Phase 2D — GPU memory guard。記錄 peak VRAM / 避免多模型同時常駐。

只測量，不管理排程（orchestration 層逐模型 release）。
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)

try:
    import torch

    _HAS_TORCH = True
except Exception:  # pragma: no cover
    _HAS_TORCH = False


class GpuGuard:
    def __init__(self) -> None:
        self._baseline = self._current_vram()

    def _current_vram(self) -> float:
        if not _HAS_TORCH or not torch.cuda.is_available():
            return 0.0
        return float(torch.cuda.memory_allocated() / (1024 ** 2))

    def peak_vram(self) -> float:
        """目前為止（本次 process）已配置 VRAM 的峰值（MB）。"""
        if not _HAS_TORCH or not torch.cuda.is_available():
            return 0.0
        return float(torch.cuda.max_memory_allocated() / (1024 ** 2))

    def reset(self) -> None:
        if _HAS_TORCH and torch.cuda.is_available():
            torch.cuda.reset_peak_memory_stats()
            torch.cuda.empty_cache()

    def release(self, model=None) -> None:
        """釋放 CUDA cache（模型多時避免 VRAM 常駐）。"""
        if _HAS_TORCH and torch.cuda.is_available():
            torch.cuda.empty_cache()
        del model

    def snapshot(self, model_name: str) -> dict:
        return {"model": model_name, "peak_vram_mb": self.peak_vram()}
