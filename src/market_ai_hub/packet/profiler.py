"""Phase 2I-A — Performance profiler（before/after benchmark）。"""
from __future__ import annotations

import time
import tracemalloc
from contextlib import contextmanager


class PerformanceProfiler:
    """記錄 phase latency / HTTP count / RAM / VRAM / model loads / response size。"""

    def __init__(self) -> None:
        self.phases: dict[str, float] = {}
        self.http_calls: int = 0
        self.http_total_sec: float = 0.0
        self.datalake_reads: int = 0
        self.datalake_writes: int = 0
        self.model_loads: int = 0
        self.model_cache_hits: int = 0
        self.ram_peak_mb: float = 0.0
        self.vram_peak_mb: float = 0.0
        self._tracemalloc_active = False

    @contextmanager
    def time(self, name: str):
        t0 = time.perf_counter()
        try:
            yield
        finally:
            self.phases[name] = self.phases.get(name, 0.0) + (time.perf_counter() - t0)

    def start_ram(self) -> None:
        tracemalloc.start()
        self._tracemalloc_active = True

    def stop_ram(self) -> None:
        if self._tracemalloc_active:
            cur, peak = tracemalloc.get_traced_memory()
            self.ram_peak_mb = round(peak / 1e6, 2)
            tracemalloc.stop()
            self._tracemalloc_active = False

    def start_vram(self) -> None:
        try:
            import torch

            torch.cuda.reset_peak_memory_stats()
        except Exception:
            pass

    def stop_vram(self) -> None:
        try:
            import torch

            if torch.cuda.is_available():
                self.vram_peak_mb = round(torch.cuda.max_memory_allocated() / 1e6, 2)
        except Exception:
            pass

    def summary(self) -> dict:
        return {
            "phases": self.phases,
            "http_calls": self.http_calls,
            "http_total_sec": round(self.http_total_sec, 3),
            "datalake_reads": self.datalake_reads,
            "datalake_writes": self.datalake_writes,
            "model_loads": self.model_loads,
            "model_cache_hits": self.model_cache_hits,
            "ram_peak_mb": self.ram_peak_mb,
            "vram_peak_mb": self.vram_peak_mb,
        }


def patch_http_counters(profiler: PerformanceProfiler):
    """monkeypatch httpx + requests 以計數 HTTP 呼叫（yfinance 用 requests）。"""
    try:
        import httpx
        _og_get, _og_post = httpx.get, httpx.post

        def _counted_get(*a, **kw):
            t0 = time.perf_counter()
            try:
                return _og_get(*a, **kw)
            finally:
                profiler.http_calls += 1
                profiler.http_total_sec += time.perf_counter() - t0

        def _counted_post(*a, **kw):
            t0 = time.perf_counter()
            try:
                return _og_post(*a, **kw)
            finally:
                profiler.http_calls += 1
                profiler.http_total_sec += time.perf_counter() - t0

        httpx.get, httpx.post = _counted_get, _counted_post
    except Exception:
        pass
    try:
        import requests
        from requests.sessions import Session
        _og_req = Session.request

        def _counted_req(self, method, url, **kw):
            t0 = time.perf_counter()
            try:
                return _og_req(self, method, url, **kw)
            finally:
                profiler.http_calls += 1
                profiler.http_total_sec += time.perf_counter() - t0

        Session.request = _counted_req
        # 也 patch module-level（yfinance 可能直接用 requests.get/post）
        for fn in ("get", "post", "request"):
            if hasattr(requests, fn):
                _og = getattr(requests, fn)

                def _mk(og):
                    def _counted(*a, **kw):
                        t0 = time.perf_counter()
                        try:
                            return og(*a, **kw)
                        finally:
                            profiler.http_calls += 1
                            profiler.http_total_sec += time.perf_counter() - t0
                    return _counted

                setattr(requests, fn, _mk(_og))
    except Exception:
        pass
