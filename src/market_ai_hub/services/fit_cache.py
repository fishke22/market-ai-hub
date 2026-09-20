"""Phase 2Q-D — request-time research fit cache（§23）。

XGB/LGBM 等 classifier 在相同 data / horizon / feature_version 下不得每 request 重新 fit。
key：model / symbol / horizon / training_data_hash / feature_version / build_id。
資料不變 → reuse fitted artifact；資料更新 → invalidates/refit。

這是 request-time research fit cache，不是 AUTO_TRAIN，不是 model promotion。
"""
from __future__ import annotations

import hashlib
import time

from market_ai_hub.services.build_info import build_fingerprint

_FIT_CACHE: dict[str, tuple[float, object]] = {}
_TTL_SECONDS = 600
_FEATURE_VERSION = "base-v1"


def _training_data_hash(df) -> str:
    import pandas as pd

    if "close" in df.columns:
        tail = df["close"].tail(200).to_list()
        payload = "close|" + ",".join(f"{v:.6f}" for v in tail)
    else:
        payload = f"shape|{df.shape}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def fit_cache_key(name: str, symbol: str, horizon: str, df) -> str:
    fp = build_fingerprint()
    return f"{name}|{symbol}|{horizon}|{_training_data_hash(df)}|{_FEATURE_VERSION}|{fp['build_id']}"


def get_fitted(key: str):
    hit = _FIT_CACHE.get(key)
    if hit is not None and (time.time() - hit[0]) <= _TTL_SECONDS:
        from market_ai_hub.services.instrumentation import incr

        incr("classifier_fit_cache_hit")
        return hit[1]
    if hit is not None:
        _FIT_CACHE.pop(key, None)
    return None


def set_fitted(key: str, fitted) -> None:
    from market_ai_hub.services.instrumentation import incr

    incr("classifier_fit_count")
    _FIT_CACHE[key] = (time.time(), fitted)


def clear_fit_cache() -> None:
    _FIT_CACHE.clear()


def fit_cache_stats() -> dict:
    return {"size": len(_FIT_CACHE), "ttl_seconds": _TTL_SECONDS}
