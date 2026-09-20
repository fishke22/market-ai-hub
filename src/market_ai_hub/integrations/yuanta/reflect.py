"""Phase 2Y-B — Yuanta SPARK 反射 helper（唯讀，不登入）。

實測結論（2026-09-19）：
- YuantaSparkAPI.dll 可 LoadFrom：`YuantaSparkAPI, Version=2.0.0.1, PublicKeyToken=1a9c65c55c74e5b3`。
- namespace = `NX_ShareInterface`（IServiceAPI interface 成功載入）。
- 完整 enum 反射（enumMarketType / enumEnvironment）在 pythonnet 下**受限**：
  assembly 型別相依 gRPC / ASP.NET Core，pythonnet 無法解析相依 → ReflectionTypeLoadException。
- 因此 environment enum 的 numeric value **不得猜**，需在完整 self-contained runtime（auth_probe 執行）反射。

此模組記錄上述 finding，並提供 runtime reflection 的呼叫骨架（供 auth_probe 使用）。
"""
from __future__ import annotations

SPARK_ASSEMBLY_NAME = "YuantaSparkAPI"
SPARK_NAMESPACE = "NX_ShareInterface"
SPARK_SERVICE_INTERFACE = "NX_ShareInterface.IServiceAPI"
SPARK_ASSEMBLY_VERSION = "2.0.0.1"
SPARK_ASSEMBLY_PUBLIC_KEY_TOKEN = "1a9c65c55c74e5b3"

# pythonnet 反射限制（honest finding）
REFLECTION_STATUS = "PARTIAL"
REFLECTION_NOTE = (
    "Assembly loads; namespace NX_ShareInterface resolved; but full enum reflection "
    "fails under pythonnet (gRPC/ASP.NET Core deps unresolvable). Environment enum "
    "numeric value must be resolved at runtime by auth_probe, NOT guessed."
)


def reflect_environment_enum() -> dict:
    """runtime reflection 骨架（auth_probe 於完整 runtime 呼叫）。"""
    return {
        "status": REFLECTION_STATUS,
        "note": REFLECTION_NOTE,
        "assembly": SPARK_ASSEMBLY_NAME,
        "namespace": SPARK_NAMESPACE,
        "environment_enum_value": None,  # 未解析，不猜
    }
