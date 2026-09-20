# Phase 2Y-B — Yuanta Futures Real Login + OSE Symbol Resolution + Quote Probe

- Gate: **PHASE2YB_BLOCKED**（非核心系統失敗；blocker 為「真實登入需使用者本機互動」）
- build_id：`ccabe1e1552d9ae7`（未變）
- 測試：**396 passed**（380 + 16 2Y-B；5 live deselected）

## Login: NOT PERFORMED（誠實 blocker）
**本棒未能執行真實登入**，原因：
1. 真實密碼只允許透過本機 `getpass()` 輸入；**不得**經 command-line arg / env / prompt file /
   OpenCode prompt / MCP / JSON / log 傳遞。
2. §2.3 明確：不得向聊天視窗要求使用者重貼帳號；只能本機 CLI 讓使用者輸入。
3. 我（agent）無法取得密碼，也不得用假密碼嘗試 Login（有 0102 密碼凍結風險）。
4. 因此真實 login 需使用者自行執行：
   `python -m market_ai_hub.integrations.yuanta.auth_probe --profile futures`

## Account: MASKED
- credential preset 走 Windows Credential Manager（`MARKET_AI_HUB/YUANTA/FUTURES`）。
- 畫面只顯示 masked（`F************1234` 形式），完整帳號不落 source/config/env/json/log/docs/tests/report。

## OSE Market: 207 verified
- 由 FunctionList.xlsx 市場類 sheet 確認（2Y-A）；本棒未改。

## OSE Micro Spark Code: UNRESOLVED
- FunctionList 股票代碼總表**未含 OSE (207) 期貨 code**（2Y-A）。
- 本棒嘗試 pythonnet 反射 YuantaSparkAPI.dll：Assembly 可載入（`YuantaSparkAPI, Version=2.0.0.1`,
  namespace `NX_ShareInterface`），但**完整 enum 反射失敗**（型別相依 gRPC/ASP.NET Core，
  pythonnet 無法解析相依 → ReflectionTypeLoadException）。
- 因此 `enumEnvironment` numeric value 與 OSE Micro StkCode **不得猜**，需在完整 runtime
  （auth_probe 執行時）反射 + 登入後 read-only market info 取得。

## Capabilities（未 login，故不標 SUPPORTED_BY_ACCOUNT）
| capability | status |
|---|---|
| LOGIN / GET_WATCHLIST / GET_TICK_DETAIL / CLASSIFY_PRICE / QUOTE_LIST / WATCHLIST / FIVE_TICK / STOCK_TICK | SUPPORTED_BY_API_ONLY（entitlement 未知） |
| GET_KLINE（OSE） | NOT_SUPPORTED_BY_API_DOC（官方僅台股上市櫃） |

## Timestamp quality
- 未 login，無 quote sample；政策已備（source_timestamp = API timestamp 或 null；
  received_at = local UTC；timestamp_quality = LOCAL_RECEIVE_TIME，不製造 exchange timestamp）。

## Entitlement
- UNKNOWN（未 login，未收到有效 callback）。

## Security: PASS
- OrderApiExposureGuard：PASS（quote-only gateway 無 order method）。
- sanitizer：不回 Name/InvestorID/SellerNo/full Account。
- secret scan：只輸出 path + rule + masked match。
- auth_probe/quote_probe：單次 login、0102/0112 abort、finally LogOut+Dispose、無自動登入。

## 已交付（可完成部分）
- `integrations/yuanta/spark_auth.py`（login policy + abort codes + sanitized outcome）
- `integrations/yuanta/auth_probe.py`（CLI：masked preset + getpass + 單次 login + abort + LogOut/Dispose）
- `integrations/yuanta/quote_probe.py`（CLI：GetWatchListAll → TickDetail(20) → ClassifyPrice(1) → 短 5s streaming）
- `integrations/yuanta/reflect.py`（反射 finding：PARTIAL，環境 enum 需 runtime）
- capabilities 更新（entitlement status）、vendor 解壓（`vendor/yuanta_spark/2.2026.0918.0/`，gitignored）
- pythonnet 3.1.0 安裝

## Tests（16 新增 unit）
auth_probe_account_preset / account_masked / password_getpass / single_attempt_only / abort_0102 /
abort_0112 / auth_result_no_pii / quote_probe_no_account_query / no_order_api / max20_ticks /
stream_time_limited / probe_always_logout / probe_data_gitignored / symbol_discovery_no_guess /
symbol_requires_market207_evidence / secret_scan_after_real_login。

## Blockers（下一步）
1. 使用者本機執行 `python -m market_ai_hub.integrations.yuanta.auth_probe --profile futures`，
   以 getpass 輸入密碼完成真實 login。
2. login 成功後，需在完整 runtime 反射 `enumEnvironment` 並以 read-only market info 解析 OSE Micro StkCode。
3. 之後執行 `quote_probe --instrument OSE_NIKKEI225_MICRO_FUTURES`。

## 驗證
- `pytest tests/ -q` → 396 passed
- build_id 維持 `ccabe1e1552d9ae7`
- 全程未下單/改單/查帳/持倉/餘額/損益/歷史委託；未做 Recorder；未 Live Trading。
