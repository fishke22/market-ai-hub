"""Phase 2Q-D — runtime instrumentation（真 counters，不 hardcode）。

process-global counters，供 benchmark 與 MCP_PERF_TRACE 讀取。
不得用固定數字假裝量測。
"""
from __future__ import annotations

import threading
import time

_lock = threading.Lock()
_counters: dict[str, int] = {
    "provider_call_count": 0,
    "provider_cache_hit": 0,
    "provider_cache_miss": 0,
    "model_load_count": 0,
    "model_inference_count": 0,
    "classifier_fit_count": 0,
    "classifier_fit_cache_hit": 0,
    "feature_build_count": 0,
    "packet_cache_hit": 0,
    "forecast_cache_hit": 0,
}
_timings: dict[str, float] = {
    "model_inference_ms": 0.0,
    "classifier_fit_ms": 0.0,
    "feature_build_ms": 0.0,
}


def incr(key: str, n: int = 1) -> None:
    with _lock:
        if key in _counters:
            _counters[key] += n


def add_ms(key: str, ms: float) -> None:
    with _lock:
        _timings[key] = _timings.get(key, 0.0) + ms


def snapshot() -> dict:
    with _lock:
        out = dict(_counters)
        out.update(_timings)
        return out


def reset() -> None:
    with _lock:
        for k in _counters:
            _counters[k] = 0
        for k in _timings:
            _timings[k] = 0.0


def timed(key: str, fn):
    """執行 fn 並記錄 elapsed_ms 到 key；回傳 fn 結果。"""
    t0 = time.perf_counter()
    try:
        return fn()
    finally:
        add_ms(key, (time.perf_counter() - t0) * 1000.0)
