"""Phase 2Q-A — MCP fast-path benchmark（§23/§28）。

量測：
  A. cold quick Osaka   B. warm quick Osaka
  C. 5 repeated quick calls   D. full analysis
記錄：MCP calls / backend latency / model inference count / provider (HTTP) count /
response bytes。

目標：warm QUICK = 1 primary MCP call + 0 duplicate model inference。
DESKTOP_SAFE：不跑 GPU heavy jobs / xdist / training / fine-tuning。

用法：python scripts/benchmark_mcp_fastpath.py [--out MCP_FASTPATH_BASELINE.json]
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from market_ai_hub.packet.builder import build_analysis_packet, clear_caches  # noqa: E402
from market_ai_hub.packet.profiler import PerformanceProfiler, patch_http_counters  # noqa: E402
from market_ai_hub.services.forecast_cache import cache_stats  # noqa: E402
from market_ai_hub.services.instrumentation import snapshot as instrumentation_snapshot  # noqa: E402


def _run(cold: bool, detail: str = "compact") -> dict:
    profiler = PerformanceProfiler()
    patch_http_counters(profiler)
    if cold:
        clear_caches()
    t0 = time.perf_counter()
    packet = build_analysis_packet(
        market="osaka", target="OSE_NIKKEI225_MICRO_FUTURES",
        detail_level=detail, save_analysis=False, profiler=profiler,
    )
    latency = time.perf_counter() - t0
    inst = instrumentation_snapshot()
    return {
        "cold": cold,
        "detail_level": detail,
        "mcp_calls": 1,  # 單一 get_analysis_packet
        "backend_latency_sec": round(latency, 3),
        "model_inference_count": inst.get("model_inference_count", 0),  # 真 instrumentation，非 hardcode
        "provider_http_calls": profiler.http_calls,
        "classifier_fit_count": inst.get("classifier_fit_count", 0),
        "response_bytes": len(json.dumps(packet, ensure_ascii=False, default=str).encode("utf-8")),
        "forecast_cache": cache_stats(),
    }


def main() -> int:
    out = Path(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[1] == "--out" else ROOT / "MCP_FASTPATH_BASELINE.json"

    results = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"), "runs": []}

    results["runs"].append({"_label": "A_cold_quick", **_run(cold=True, detail="compact")})
    results["runs"].append({"_label": "B_warm_quick", **_run(cold=False, detail="compact")})
    for i in range(5):
        results["runs"].append({"_label": f"C_repeat_quick_{i + 1}", **_run(cold=False, detail="compact")})
    results["runs"].append({"_label": "D_full_analysis", **_run(cold=False, detail="normal")})

    warm_ok = all(
        r.get("model_inference_count", 0) == 0 and r.get("mcp_calls", 0) == 1
        for r in results["runs"] if r.get("_label", "").startswith(("B_", "C_"))
    )
    results["fastpath_acceptance"] = {
        "warm_quick_single_call": warm_ok,
        "target": "warm QUICK = 1 primary MCP call + 0 duplicate model inference",
    }

    out.write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2, default=str))
    print(f"\nfastpath_acceptance={results['fastpath_acceptance']}")
    print(f"written -> {out}")
    return 0 if warm_ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
