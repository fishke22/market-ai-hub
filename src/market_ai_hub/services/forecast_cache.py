"""Phase 2Q-A — forecast result cache（§20）。

進程級 TTL cache，key 含 target / horizon / data hash / model / build_id。
只要輸入資料沒改（data hash 相同），同一模型預測不得重跑 GPU inference。
新 market data → data hash 變 → 自動 invalidates。不得用 stale cache 冒充新資料。
"""
from __future__ import annotations

import hashlib
import time

_FORECAST_CACHE: dict[str, tuple[float, dict]] = {}
_TTL_SECONDS = 300

# 2Q-F.5 §14：session filter 版本進 cache key（session sanitation 變更 → 舊 unsanitized cache 不得 reuse）
SESSION_FILTER_VERSION = "XTAI_SESSION_FILTER_V1"


def _data_hash(closes) -> str:
    """最後 60 根 close 值 + 最後 timestamp 的 hash（資料改 → hash 變 → cache invalidates）。"""
    import pandas as pd

    if hasattr(closes, "index"):
        tail = closes.tail(60)
        last_ts = str(tail.index[-1]) if len(tail) else ""
        payload = last_ts + "|" + ",".join(f"{v:.6f}" for v in tail.to_list())
    else:
        payload = ",".join(f"{v:.6f}" for v in list(closes)[-60:])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def forecast_cache_key(model: str, symbol: str, horizon: str, closes, build_id: str) -> str:
    return f"{model}|{symbol}|{horizon}|{_data_hash(closes)}|{build_id}|{SESSION_FILTER_VERSION}"


def get_cached(key: str) -> dict | None:
    hit = _FORECAST_CACHE.get(key)
    if hit is not None and (time.time() - hit[0]) <= _TTL_SECONDS:
        from market_ai_hub.services.instrumentation import incr

        incr("forecast_cache_hit")
        return hit[1]
    if hit is not None:
        _FORECAST_CACHE.pop(key, None)
    return None


def set_cached(key: str, value: dict) -> None:
    _FORECAST_CACHE[key] = (time.time(), value)


def clear_forecast_cache() -> None:
    _FORECAST_CACHE.clear()


def cache_stats() -> dict:
    return {"size": len(_FORECAST_CACHE), "ttl_seconds": _TTL_SECONDS}
