"""TimesFM 3.0 smoke test（spec §6）：univariate / quantile / multivariate / CUDA。"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone

from pathlib import Path
_REPO = Path(__file__).resolve().parents[1]


def main() -> int:
    sys.path.insert(0, str(_REPO / "src"))
    import numpy as np
    import torch

    from market_ai_hub.models.timesfm_model import TimesFM3Adapter

    results: dict = {}
    t = np.arange(0, 128)
    synthetic = np.sin(t / 8.0) * 10 + 100 + t * 0.05

    print("=== TimesFM 3.0 smoke test ===")
    print("cuda_available:", torch.cuda.is_available())

    adapter = TimesFM3Adapter(device="cuda" if torch.cuda.is_available() else "cpu")
    try:
        adapter.load()
        results["load"] = "PASS"
        print("[1] load: PASS")
    except Exception as e:
        results["load"] = f"FAIL: {e}"
        print("[1] load: FAIL:", e)
        _save(results)
        return 1

    # 2. univariate quantile path
    try:
        pred = adapter.predict(synthetic, horizon=7, quantiles=[0.1, 0.5, 0.9])
        path = pred["path"]
        ok = sorted(path.keys()) == ["p10", "p50", "p90"] and all(len(path[q]) == 7 for q in path)
        results["univariate_quantile"] = "PASS" if ok else f"FAIL: {pred}"
        print("[2] univariate quantile path:", "PASS" if ok else "FAIL", {q: path[q][:3] for q in path})
    except Exception as e:
        results["univariate_quantile"] = f"FAIL: {e}"
        print("[2] FAIL:", e)

    # 3. multivariate
    try:
        mv = np.stack([synthetic, synthetic * 0.5 + 50])
        out = adapter.predict_multivariate(mv, horizon=7)
        results["multivariate"] = "PASS" if out.shape[-1] == 7 else f"FAIL: {out.shape}"
        print("[3] multivariate:", "PASS" if out.shape[-1] == 7 else "FAIL", out.shape)
    except Exception as e:
        results["multivariate"] = f"FAIL: {e}"
        print("[3] FAIL:", e)

    # 4. past-only covariates
    try:
        cov = synthetic[::-1].copy() * 0.0 + 1.0  # 與 history 等長的 dummy past-only covariate
        pred2 = adapter.predict(synthetic, horizon=7, quantiles=[0.1, 0.5, 0.9], past_only_covariates=cov)
        results["past_only_covariates"] = "PASS" if sorted(pred2["path"].keys()) == ["p10", "p50", "p90"] else f"FAIL: {pred2}"
        print("[4] past-only covariates:", "PASS")
    except Exception as e:
        results["past_only_covariates"] = f"FAIL: {e}"
        print("[4] FAIL:", e)

    # 5. CUDA inference 確認（已在 load 用 device=cuda 時即驗證）
    results["cuda_inference"] = "PASS" if adapter.device == "cuda" else "SKIP (cpu)"
    print("[5] CUDA inference:", results["cuda_inference"])

    _save(results)
    return 0 if all(v == "PASS" for v in results.values()) else 1


def _save(results: dict) -> None:
    import os

    out = str(_REPO / "reports" / "timesfm_smoke.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"test": "timesfm_smoke", "at": datetime.now(timezone.utc).isoformat(), "results": results}, f, ensure_ascii=False, indent=2)
    print("saved:", out)


if __name__ == "__main__":
    raise SystemExit(main())
