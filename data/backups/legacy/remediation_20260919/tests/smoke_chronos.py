"""Chronos-2 smoke test（spec §5）：CPU 載入、CUDA 載入、synthetic forecast、quantiles。"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone


def main() -> int:
    sys.path.insert(0, r"D:\MARKET_AI_HUB\src")
    import numpy as np
    import torch

    from market_ai_hub.models.chronos_model import ChronosAdapter

    results: dict = {}
    t = np.arange(0, 128)
    synthetic = np.sin(t / 8.0) * 10 + 100 + t * 0.05

    print("=== Chronos-2 smoke test ===")
    print("cuda_available:", torch.cuda.is_available())

    # 1. CPU load
    cpu = ChronosAdapter(device="cpu")
    try:
        cpu.load()
        results["cpu_load"] = "PASS"
        print("[1] CPU load: PASS")
    except Exception as e:
        results["cpu_load"] = f"FAIL: {e}"
        print("[1] CPU load: FAIL:", e)

    # 2. CUDA load
    if torch.cuda.is_available():
        gpu = ChronosAdapter(device="cuda")
        try:
            gpu.load()
            results["cuda_load"] = "PASS"
            print("[2] CUDA load: PASS")
        except Exception as e:
            results["cuda_load"] = f"FAIL: {e}"
            print("[2] CUDA load: FAIL:", e)
    else:
        results["cuda_load"] = "SKIP (no CUDA)"
        print("[2] CUDA load: SKIP (no CUDA)")

    # 3. synthetic forecast + 4. quantiles 0.1/0.5/0.9
    try:
        adapter = cpu
        pred = adapter.predict(synthetic, horizon=7, quantiles=[0.1, 0.5, 0.9])
        qs = sorted(pred.keys())
        ok = qs == ["p10", "p50", "p90"] and pred["p10"] <= pred["p50"] <= pred["p90"]
        results["forecast_quantiles"] = "PASS" if ok else f"FAIL: {pred}"
        print("[3][4] forecast + quantiles:", "PASS" if ok else "FAIL", pred)
    except Exception as e:
        results["forecast_quantiles"] = f"FAIL: {e}"
        print("[3][4] forecast FAIL:", e)

    summary = {"test": "chronos_smoke", "at": datetime.now(timezone.utc).isoformat(), "results": results}
    out = r"D:\MARKET_AI_HUB\reports\chronos_smoke.json"
    import os

    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)
    print("saved:", out)
    return 0 if all(v == "PASS" or v.startswith("SKIP") for v in results.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
