# Phase 2Y-C — Yuanta SPARK Interop Wiring + Real Authentication

- Gate: **PHASE2YC_READY_FOR_USER_AUTH**（interop 完成；真實 login 待使用者本機輸入密碼）
- build_id：`ccabe1e1552d9ae7`（未變）
- 測試：**415 passed**（396 + 19 2Y-C；5 live deselected）

## .NET runtime / pythonnet / Spark package
- .NET 8 x64：`Microsoft.NETCore.App 8.0.28/8.0.29` + `Microsoft.AspNetCore.App 8.0.29` ✅
- pythonnet 3.1.0（64bit Python 3.12.13）✅
- Spark package：`vendor/yuanta_spark/2.2026.0918.0/YuantaSparkAPI_win-x64_Python`（完整 package，含 gRPC/ASP.NET 相依）✅

## interop method：PYTHONNET_OFFICIAL_PATH（非 C# fallback）
- 依官方 `YSendOrder.py` 載入法：`load("coreclr")` → `import clr` → `os.add_dll_directory(pkg)` →
  `sys.path.append(pkg)` → `clr.AddReference("YuantaSparkAPI")` → `from YuantaOneAPI import (...)`。
- **未使用** `Assembly.GetTypes()` 完整 reflection（那是上一棒錯誤方向；ReflectionTypeLoadException 不阻擋公開 API）。

## YuantaOneAPI import：PASS
- `from YuantaOneAPI import YuantaSparkAPITrader, enumEnvironmentMode, enumMarketType, enumLogType, OnResponseEventHandler` ✅

## YuantaSparkAPITrader instantiate：PASS
- `YuantaSparkAPITrader()` 成功 instantiate；`OnResponse += OnResponseEventHandler(...)` 註冊成功；`SetLogType` 成功。

## enum（runtime 反射驗證，非猜值）
| enum | 任務假設值 | **實際 installed DLL 值** |
|---|---|---|
| enumEnvironmentMode.PROD | 1 | **2**（⚠️ 與假設不同） |
| enumEnvironmentMode.UAT | 2 | **1**（⚠️ 與假設不同） |
| enumMarketType.OSE | 207 | **207** ✅ |

**重要**：任務 §5 假設 PROD=1/UAT=2 是錯的。依「以實際 installed package 為準」原則，
code 使用 `enumEnvironmentMode.PROD` 符號（runtime 值=2），**不硬 cast 猜值**。

## Real Login：NOT_RUN（待使用者）
- 真實 Login 需使用者本機執行 `python -m market_ai_hub.integrations.yuanta.auth_probe --profile futures`，
  getpass 輸入密碼一次。
- 流程已接線：WinCred preset → masked 顯示 → OrderApiExposureGuard → Open(PROD) →
  Login(account,password) → wait OnResponse → sanitize → Logout/Close/Dispose（finally）。
- Login() bool 只代表 accepted；真正結果 = `LoginResult.LoginStatus.MsgCode`（0001=成功、0102/0112=abort）。

## Security：PASS
- OrderApiExposureGuard PASS；無 generic invoke、無 order method、無 C# sidecar。
- password 只存 process memory（`del password` 立即丟棄），不持久保存、不寫 WinCred。
- sanitize：不回 Name/InvestorID/SellerNo/full Account；`_write_result` 只寫 masked account。
- `YUANTA_INTEROP_DIAGNOSTIC.json`：只含 runtime/enum/status，無 credential。

## 已交付
- `spark_runtime.py`（官方 pythonnet 載入 + RealYuantaSparkClient：open_prod/login/logout/close/dispose/cleanup）
- `spark_runtime_probe.py`（runtime metadata probe → YUANTA_INTEROP_DIAGNOSTIC.json）
- `auth_probe.py` 重寫（真實 login flow，取代 NOT_WIRED）
- 19 unit tests

## 下一步（使用者）
1. 執行 `python -m market_ai_hub.integrations.yuanta.auth_probe --profile futures`，輸入密碼。
2. 若 MsgCode=0001 → `YUANTA_REAL_AUTH_RESULT.json` 產生 → PHASE2YC_AUTH_PASS。
3. 之後才做 OSE symbol discovery + quote probe（下一 phase）。

## 驗證
- `pytest tests/ -q` → 415 passed
- `python -m market_ai_hub.integrations.yuanta.spark_runtime_probe` → interop_status=READY、enum PROD=2/UAT=1/OSE=207
- build_id 維持 `ccabe1e1552d9ae7`
- 全程未下單/改單/查帳/持倉/餘額/損益；未做 Recorder；未 Live Trading。
