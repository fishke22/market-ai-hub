"""Phase 2I-A — packet performance benchmark（before/after）。

用法：python scripts/benchmark_packet.py [--out PERFORMANCE_BASELINE.json]
量測 OSE（compact/normal/audit）+ 台股（normal）的 latency / HTTP calls /
RAM / VRAM / model loads / response bytes / tokens。冷啟動 + 暖啟動。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from market_ai_hub.packet.builder import build_analysis_packet, clear_caches  # noqa: E402
from market_ai_hub.packet.benchmark import estimate_tokens  # noqa: E402
from market_ai_hub.packet.profiler import PerformanceProfiler, patch_http_counters  # noqa: E402


def measure(market: str, target: str, detail: str, cold: bool) -> dict:
    profiler = PerformanceProfiler()
    patch_http_counters(profiler)
    if cold:
        clear_caches()
    profiler.start_ram()
    profiler.start_vram()
    t0 = time.perf_counter()
    packet = build_analysis_packet(market=market, target=target, detail_level=detail,
                                   save_analysis=False, profiler=profiler)
    total = time.perf_counter() - t0
    profiler.stop_ram()
    profiler.stop_vram()
    return {
        "market": market, "target": target, "detail_level": detail, "cold": cold,
        "total_latency_sec": round(total, 3),
        "phases": profiler.phases,
        "http_calls": profiler.http_calls,
        "http_total_sec": profiler.http_total_sec,
        "datalake_reads": profiler.datalake_reads,
        "datalake_writes": profiler.datalake_writes,
        "model_loads": profiler.model_loads,
        "model_cache_hits": profiler.model_cache_hits,
        "ram_peak_mb": profiler.ram_peak_mb,
        "vram_peak_mb": profiler.vram_peak_mb,
        "response_bytes": len(json.dumps(packet, ensure_ascii=False, default=str).encode("utf-8")),
        "estimated_tokens": estimate_tokens(packet),
    }


def main() -> int:
    out = Path(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[1] == "--out" else ROOT / "PERFORMANCE_BASELINE.json"
    runs = [
        ("osaka", "OSE_NIKKEI225_MICRO_FUTURES", "compact"),
        ("osaka", "OSE_NIKKEI225_MICRO_FUTURES", "normal"),
        ("osaka", "OSE_NIKKEI225_MICRO_FUTURES", "audit"),
        ("taiwan", "3706.TW", "normal"),
    ]
    results = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ"), "runs": []}
    for market, target, detail in runs:
        results["runs"].append(measure(market, target, detail, cold=True))
        results["runs"].append(measure(market, target, detail, cold=False))
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps(results, ensure_ascii=False, indent=2, default=str))
    print(f"\nwritten -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
