"""Forecast reproducibility（V1.3）。

同一「模型版本 + input_data_hash + horizon + forecast_config + seed」→ 相同 forecast。
- deterministic 模型（Chronos-2 / TimesFM-3 為 deterministic quantile，無 MC sampling）：
  deterministic_mode=true、sampling_config 標明無 sampling。
- 若模型本質使用 MC sampling：不得隱藏隨機性 → deterministic_mode=false +
  forecast_stochastic=true（STOCHASTIC_FORECAST），保留 sample count 與 seed，
  不得拿不同抽樣結果直接比較模型優劣。
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

DEFAULT_SEED = 42


def input_hash(series: pd.Series | np.ndarray | list) -> str:
    """輸入序列的內容 hash（float32 取樣以跨平台穩定）。"""
    arr = np.asarray(series, dtype=np.float32)
    payload = arr.tobytes()
    return hashlib.sha256(payload).hexdigest()[:16]


def forecast_config_hash(
    model_id: str,
    horizon: str,
    steps: int,
    quantiles: list[float] | None,
    seed: int | None,
    data_frequency: str,
) -> str:
    """forecast config 的 hash（model + horizon + quantiles + seed + freq）。"""
    cfg = {
        "model_id": model_id,
        "horizon": horizon,
        "steps": steps,
        "quantiles": sorted(quantiles or []),
        "seed": seed,
        "data_frequency": data_frequency,
    }
    payload = json.dumps(cfg, sort_keys=True).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def model_revision_local(model_id: str, cache_dir: Path) -> str:
    """從 HF 本地 cache 的 snapshots/<sha> 讀 commit hash（離線，無網路依賴）。"""
    try:
        slug = "models--" + model_id.replace("/", "--")
        snap = cache_dir / slug / "snapshots"
        if snap.exists():
            dirs = [d.name for d in snap.iterdir() if d.is_dir()]
            if dirs:
                return sorted(dirs)[0]
    except Exception:
        pass
    return "unknown"


def model_revision_remote(model_id: str) -> str:
    """HF API 查 model commit（需網路；失敗回 unknown）。"""
    try:
        from huggingface_hub import HfApi

        info = HfApi().model_info(model_id)
        return str(info.sha)
    except Exception:
        return "unknown"


def sampling_metadata(deterministic: bool, method: str = "none", n_samples: int | None = None) -> dict:
    if deterministic:
        return {"method": "none", "deterministic_quantiles": True, "n_samples": None}
    return {"method": method, "n_samples": n_samples, "deterministic_quantiles": False}
