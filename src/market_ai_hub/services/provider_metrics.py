"""Phase 2Z — Provider request instrumentation（關閉 2I-A observability gap）。

不靠 global monkey patch 數 socket；由 provider wrapper 記錄「logical request」：
provider / operation / cache_hit / cache_miss / request_started / request_success /
request_failure / duration_ms。目標：知道 MARKET_AI_HUB 要求 provider 做了幾次資料取得。
"""
from __future__ import annotations

import threading
import time
from contextlib import contextmanager

DEFAULT_METRICS = "provider_metrics"


class ProviderMetrics:
    def __init__(self) -> None:
        self._records: list[dict] = []
        self._lock = threading.Lock()

    def record(self, provider: str, operation: str, *, cache_hit: bool,
               success: bool, duration_ms: float) -> None:
        with self._lock:
            self._records.append({
                "provider": provider,
                "operation": operation,
                "cache_hit": cache_hit,
                "cache_miss": not cache_hit,
                "request_started": True,
                "request_success": success,
                "request_failure": not success,
                "duration_ms": round(duration_ms, 3),
            })

    def logical_calls(self, provider: str | None = None) -> int:
        with self._lock:
            recs = self._records if provider is None else [r for r in self._records if r["provider"] == provider]
        return len(recs)

    def cache_hits(self, provider: str | None = None) -> int:
        with self._lock:
            recs = self._records if provider is None else [r for r in self._records if r["provider"] == provider]
        return sum(1 for r in recs if r["cache_hit"])

    def cache_misses(self, provider: str | None = None) -> int:
        with self._lock:
            recs = self._records if provider is None else [r for r in self._records if r["provider"] == provider]
        return sum(1 for r in recs if r["cache_miss"])

    def summary(self, provider: str | None = None) -> dict:
        return {
            "logical_calls": self.logical_calls(provider),
            "cache_hits": self.cache_hits(provider),
            "cache_misses": self.cache_misses(provider),
        }

    def reset(self) -> None:
        with self._lock:
            self._records.clear()


_global = ProviderMetrics()


def get_provider_metrics() -> ProviderMetrics:
    return _global


@contextmanager
def tracked(provider: str, operation: str, *, cache_hit: bool):
    """provider 包一層：記錄一次 logical request（含 cache_hit/miss + 成敗 + 耗時）。"""
    t0 = time.perf_counter()
    success = False
    try:
        yield
        success = True
    except Exception:
        success = False
        raise
    finally:
        _global.record(provider, operation, cache_hit=cache_hit,
                       success=success, duration_ms=(time.perf_counter() - t0) * 1000)
