# Yuanta Securities Spark API（已驗證）

## 驗證狀態
- ✅ 真實 Login 成功，`MsgCode=0001`。
- DLL：`YuantaSparkAPI.dll` **v2.2026.0918.0**（SHA256 `4E124E...`）。
- Interop：pythonnet 3.1.0 + .NET 8（x64）。

## 正確載入流程
```python
from pythonnet import load
load("coreclr")                       # 必須在 import clr 之前
import clr, os, sys
sys.path.append(PKG_ROOT); os.add_dll_directory(PKG_ROOT)
clr.AddReference("YuantaSparkAPI")
from YuantaOneAPI import (
    YuantaSparkAPITrader, enumEnvironmentMode, enumMarketType,
    enumLogType, OnResponseEventHandler,
)
api = YuantaSparkAPITrader()
api.OnResponse += OnResponseEventHandler(handler)
api.SetLogType(enumLogType.NONE)      # 最小 log
```

## 禁止
- ❌ 用 `Assembly.GetTypes()` 完整 reflection 當必要前置（會 `ReflectionTypeLoadException`，但不代表公開 API 不能用）。
- ❌ 硬 cast enum 數值（用 symbolic enum）。

## Runtime enum（本機反射實測，非猜）
| enum | 值 |
|---|---|
| `enumEnvironmentMode.UAT` | 1 |
| `enumEnvironmentMode.PROD` | 2 |
| `enumMarketType.OSE` | 207 |
| `enumLogType.NONE` | 0 |

## 登入流程
```
api.Open(enumEnvironmentMode.PROD)
  → 等 Connected 事件（intMark=0，首次連線 ~1-12s）
  → api.Login(account, password)   # return True 只代表 accepted
  → 等 OnResponse (strIndex='Login')
  → LoginResult.LoginStatus.MsgCode
  → LogOut() → Close() → Dispose()
```

## MsgCode 語義（官方）
| code | 意義 |
|---|---|
| 0000 | execution failed |
| 0001（或 00001） | success |
| 0102 | password frozen / not enabled |
| 0112 | no permission（**用錯 API family 也會這樣**） |

## Account
只存 Windows Credential Manager（target `MARKET_AI_HUB/YUANTA/SECURITIES` 或 fallback `QROS/Yuanta/SecuritiesReadonly`）。
**不得保存實際帳號。** 畫面只顯示 masked。
