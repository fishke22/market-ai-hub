# Phase 2Y-A — Yuanta Component Inventory + Secure Credential Infrastructure + Quote-Only Boundary

- Gate: **PHASE2YA_PASS**
- build_id：`ccabe1e1552d9ae7`（未變）
- 測試：**380 passed**（365 + 15 2Y-A；5 live deselected）
- **本棒完全未登入元大**（NO LOGIN / NO QUOTE / NO ACCOUNT / NO ORDER）。

## 1. 找到哪些 component
- 證券：`YuantaSparkAPI_win-x64_Python.zip`（Spark gRPC API）、`YuantaSparkAPI_CSharp.zip`、`YuantaOneAPI_Com/Delphi/WPF.zip`。
- 期貨：`API_Yuanta2.1.2.7.zip`（legacy COM）、`YuantaQuoteAPI_py.zip`、期貨元件簡介。

## 2. DLL version
- `YuantaSparkAPI.dll` = **2.2026.0918.0**（FileVersion = ProductVersion），SHA256 `4E124E718B40BAEDA8A61A515F32E24037F4FFB67F6739F8194250EC095BA01C`。

## 3. FunctionList
- `FunctionList.xlsx` 3.4MB，SHA256 `39B0F224...`。Sheets：功能對照表 / 股票代碼總表(74559) /
  委託回報資料 / 期貨下單錯誤代碼 / 市場類。

## 4. architecture / runtime
- Spark API：x64，.NET 8 self-contained（coreclr/hostfxr/hostpolicy）+ gRPC + ASP.NET Core 本地 server。
- 期貨 legacy：COM（YuantaQuoteLib / YuantaOrderAPI / GWMktAPLib），與 Spark 不同世代，DLL 不互覆蓋。

## 5. vendor package selection
- 未複製 DLL（證券/期貨不同世代 + 本棒無登入需求）。只提交 `vendor_manifest.json`（file/version/SHA256）。

## 6. enum OSE
- **OSE = enumMarketType 207**（FunctionList 市場類 sheet 確認）。SGX=202、CME=203、CBOT=204、TCE=205。

## 7. instrument candidates found
- SGX 日經 `NKN`、SGX 微型日經 `SNS`；CME 微型日經 `MNIK/MNK`、CME 日經 `NIY`（USD）/`NK`（JPY）。
- **OSE Nikkei Micro/Mini/Large 的 SPARK StkCode 不在 FunctionList** → 不猜，標 UNVERIFIED。

## 8. quote API inventory
- 見 `docs/YUANTA_QUOTE_API_INVENTORY.md`：SubscribeWatchlist*/FiveTickA/Stocktick、GetStkTickDetail、
  GetStkClassifyPrice、GetQuoteList(100001)、SubscribeMarketInformation、GetKLine（僅 TWSE/TWOTC）。
- 全部未 tested（NO LOGIN），不標 SUPPORTED_BY_ACCOUNT。

## 9. credential backend
- Windows Credential Manager（win32cred）。非 WinCred → **FAIL CLOSED**。
- targets：`MARKET_AI_HUB/YUANTA/FUTURES`、`/SECURITIES`。
- CLI：`python -m market_ai_hub.integrations.yuanta.credentials status|setup|remove`（getpass，不 echo）。

## 10. sanitizer
- `sanitize_login_result()`：只回 connected/masked_account/status_code/permission_state/timestamp。
  **不回 Name / InvestorID / SellerNo**。

## 11. order API guard
- `OrderApiExposureGuard` 掃描 yuanta/mcp/skills/examples → PASS（無 order method）。
- `YuantaQuoteOnlyGateway` 架構上無 login/subscribe/order 方法。

## 12. secret scan
- `secret_scan.py` 偵測帳號格式/password/InvestorID/PFX/certificate；只輸出 path + rule + masked match。

## 13. tests（15 新增）
wincred_backend_contract / credential_no_plaintext / credential_fake_roundtrip / credential_log_redaction /
login_result_sanitizer / no_name_in_mcp / no_investorid_in_mcp / quote_gateway_no_order_methods /
order_api_exposure_guard / function_list_parser / instrument_resolver_no_guess /
market_enum_local_validation / capability_unknown_before_login / vendor_gitignored / secret_scan_masked_output。

## 14. blockers
- 無（foundation 完成）。未來「真實 login / entitlement / OSE Micro quote / recorder」需新指令（本棒禁止）。

## 驗證
- `pytest tests/ -q` → 380 passed
- build_id 維持 `ccabe1e1552d9ae7`
- 全程未登入、未訂閱、未查帳、未下單。
