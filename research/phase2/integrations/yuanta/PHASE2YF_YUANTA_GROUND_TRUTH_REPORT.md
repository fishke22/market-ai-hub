# Phase 2Y-F — Yuanta Integration Ground-Truth + OSE Micro Symbol Resolution + Download/Certificate/Permission Docs

- Gate: **PHASE2YF_PASS**（ground truth + 文件完成；legacy COM 不支援 OSE 不阻塞系統）
- build_id：`ccabe1e1552d9ae7`（未變）
- 測試：**465 passed**（449 + 16 2Y-F；5 live deselected）

## SPARK securities auth
- ✅ AUTH_VERIFIED（`YuantaSparkAPITrader`，`MsgCode=0001`）。

## SPARK futures official support
- ✅ 官方 SPARK 同時支援 Securities 與 Futures 帳號；權限依帳號個別開通。
- 先前「Futures = COM only」錯誤假設**已修正**。

## SPARK futures local permission status
- 期貨帳號 SPARK Login 回 `0112` = **「無此權限使用功能」**（不是 Wrong API family）。
- 狀態：`NEEDS_ACCOUNT_API_PERMISSION / NOT_ENTITLED`。

## Legacy Quote API scope
- 官方公開頁命名「**國內行情 API**」+ 本地 sample/Setup.ini 僅 TAIFEX 國內商品。
- → `legacy_com_scope = DOMESTIC_ONLY`（疑）；**不用它找 JNU（OSE 國外期貨）**。

## Legacy Trading API inventory
- 官方期貨 API 頁：交易 API **1.6.1.3**（C# / Python sample）。
- 需「API 交易服務風險預告暨申請使用聲明書」+ 核准。
- **FUTURE_RESEARCH_ONLY / NOT_IMPLEMENTED**，本棒未 register/登入/測 order。

## Certificate workflow
- `docs/YUANTA_CERTIFICATE_WINDOWS11.md`（申請/匯入/簽驗，同一 ID 一張憑證，期限 1 年）。
- `scripts/check_yuanta_certificate.ps1`（唯讀檢查，不 export private key、PII 遮罩）。

## Download sources
- `docs/YUANTA_DOWNLOADS.md`（SPARK x64/x86/C#/COM + Futures 行情/交易；標 `PUBLIC_PAGE_VERSION != LOCAL_OBSERVED_VERSION`）。
- `config/yuanta_official_sources.yaml`（官方來源 ground truth）。

## API application paths
- `docs/YUANTA_API_PERMISSIONS.md`（API 行情/交易服務申請聲明書路徑）。
- `docs/YUANTA_MARKET_DATA_PERMISSIONS.md`（各權限 VERIFIED/UNKNOWN/NEEDS_BROKER_CONFIRMATION）。

## JNU public product code
- ✅ 大阪微日經 public product code = **JNU**（JNI=大阪日經、JNM=大阪小日經）。
- OSE Micro contract multiplier = Nikkei 225 × JPY 10。

## 三種代碼目前是否 verified
| 代碼 | 狀態 |
|---|---|
| public_product_code（JNU） | **VERIFIED** |
| spark_quote_code | UNVERIFIED |
| legacy_com_quote_symbol | UNVERIFIED |
| trading_order_code | UNVERIFIED |

## Futures COM real auth status
- ✅ 登入流程全通：**T+1 盤登入成功**（`status=2`），**T 盤無登入權**（`status=-2`）。
- Big5 編碼已修；單次 login、不 retry。

## OSE quote path recommendation
- 若需 OSE Micro 即時行情：**SPARK Futures**（開通期貨 SPARK 權限後，經 FunctionList/StkCode 取得）。
- Legacy COM 不支援國外期貨（scope DOMESTIC_ONLY）→ 不用 JNU probe。

## GitHub documentation completeness
- 11 份 Yuanta docs + 2 config + scripts 全進 `PUBLICATION_FILE_MANIFEST.txt`。
- vendor/OCX/DLL/PFX/credential 進 `PUBLICATION_EXCLUDE_MANIFEST.txt` + `.gitignore`。

## Security
- OrderApiExposureGuard PASS；Trading API 未 import runtime；無 order MCP；帳號/密碼不落檔。

## Tests（16 新增）
spark_supports_futures / 0112_permission_not_wrong_family / three_way_split / public_jnu /
jnu_not_auto_quote / legacy_com_scope_not_assumed / downloads_doc / certificate_doc /
certificate_no_private_export / permission_doc / product_code_lookup_doc /
trading_api_future_documented / trading_api_not_runtime_imported / order_guard_still_passes /
publication_manifest_all_yuanta_docs / ai_reconstruction_prerequisites。

## 驗證
- `pytest tests/ -q` → 465 passed
- build_id 維持 `ccabe1e1552d9ae7`
- 全程未下單/查帳/持倉/餘額/損益；未 recorder；未 Live Trading；未 GitHub push。
