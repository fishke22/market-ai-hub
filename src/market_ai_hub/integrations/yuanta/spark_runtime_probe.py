"""Phase 2Y-C — Spark runtime probe（只輸出 runtime metadata + interop status，無 credential）。

用法：python -m market_ai_hub.integrations.yuanta.spark_runtime_probe
輸出：YUANTA_INTEROP_DIAGNOSTIC.json（runtime / assembly / enum / status；不含 account/password）。
"""
from __future__ import annotations

import json
import platform
import sys

DIAG_PATH = "YUANTA_INTEROP_DIAGNOSTIC.json"


def _dotnet_runtime() -> str:
    import subprocess

    try:
        out = subprocess.run(["dotnet", "--list-runtimes"], capture_output=True, text=True, timeout=15).stdout
        versions = [line.split()[1] for line in out.splitlines() if "Microsoft.NETCore.App" in line]
        # 回報 8.x（SPARK 需 .NET 8）；若無 8.x 則回報全部
        v8 = [v for v in versions if v.startswith("8.")]
        return v8[0] if v8 else (", ".join(versions) or "unknown")
    except Exception:
        return "unknown"


def main() -> int:
    import importlib.metadata

    result = {
        "python_version": platform.python_version(),
        "architecture": platform.architecture()[0],
        "pythonnet_version": importlib.metadata.version("pythonnet"),
        "dotnet_runtime": _dotnet_runtime(),
        "spark_package_version": "2.2026.0918.0",
        "interop_status": "UNKNOWN",
        "enum_values": {},
    }
    try:
        from market_ai_hub.integrations.yuanta.spark_runtime import SparkRuntime

        rt = SparkRuntime()
        result["enum_values"] = rt.enum_values
        rt.instantiate()
        result["interop_status"] = "READY"  # 可 instantiate + 註冊 callback（未 login）
        rt.cleanup()
    except Exception as e:
        result["interop_status"] = "BLOCKED"
        result["error_type"] = type(e).__name__

    with open(DIAG_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\nwritten -> {DIAG_PATH}")
    return 0 if result["interop_status"] == "READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
