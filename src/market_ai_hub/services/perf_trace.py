"""Phase 2Q-A — MCP latency trace（§22）。

環境變數 MCP_PERF_TRACE=true 才開啟（預設 false）。
記錄 request_id / tool_name / server_latency_ms / provider_latency_ms /
model_inference_ms / cache_hit / response_bytes。
不得記錄 credential / account / token / PII。
"""
from __future__ import annotations

import os
import time
from contextlib import contextmanager
from uuid import uuid4

_ENABLED = os.environ.get("MCP_PERF_TRACE", "").strip().lower() in ("1", "true", "yes", "on")

_TRACES: list[dict] = []


def enabled() -> bool:
    return _ENABLED


@contextmanager
def trace(tool_name: str):
    """包住一個 tool 執行；yield 一個 dict 供記錄 provider/inference 時間。"""
    if not _ENABLED:
        yield {}
        return
    t0 = time.perf_counter()
    rec: dict = {
        "request_id": str(uuid4()),
        "tool_name": tool_name,
        "provider_latency_ms": 0.0,
        "model_inference_ms": 0.0,
        "cache_hit": None,
        "response_bytes": 0,
    }
    try:
        yield rec
    finally:
        rec["server_latency_ms"] = round((time.perf_counter() - t0) * 1000, 2)
        _TRACES.append(rec)


def flush() -> list[dict]:
    """回傳並清空 trace（不得含 secrets；欄位白名單）。"""
    out = _TRACES[:]
    _TRACES.clear()
    return out
