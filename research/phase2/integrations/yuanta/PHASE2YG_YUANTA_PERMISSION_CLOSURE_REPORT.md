# Phase 2Y-G — Yuanta Permission Contradiction Closure + Legacy Login ID Verification + OSE Path Finalization

- Gate: **PHASE2YG_PASS_EXTERNAL_BROKER_CONFIRMATION_REQUIRED**
  （contradiction diagnosis + docs 完成；SPARK Futures 仍 0112、OSE StkCode 仍 UNVERIFIED → 需外部確認）
- build_id：`ccabe1e1552d9ae7`（未變）
- 測試：**484 passed**（465 + 19 2Y-G；5 live deselected）

## User permission assertion
- 「元大期貨 API 權限已全部開通」→ 各權限初始 `USER_CONFIRMED_ENABLED`。
- server 回無權限時標 **CONTRADICTION**，不覆寫成「使用者沒申請」。

## SPARK Futures result
- `0112` → 狀態 **CONTRADICTION**（user enabled vs server 0112）。
- 可能來源（待查，不猜）：account format / branch / prefix / PROD / profile / entitlement 範圍。

## Legacy login ID correctness（本棒修正 BUG）
- 官方 sample label 為「**登入ID**」（身份證ID/登入ID），**不是期貨帳號**。
- 先前把 FF 帳號傳入 `SetMktLogon` 是 BUG → 已修：
  - `legacy_login_id` 與 `futures_account` 永久分離。
  - 新 WinCred target `MARKET_AI_HUB/YUANTA/LEGACY_LOGIN_ID`。
  - `scripts/setup_yuanta_legacy_login_id.ps1`（本機一次性輸入）。
  - `futures_auth_probe` 改用 login_id 登入。

## T result / T+1 result
- T+1：`登入成功`（status=2）→ SERVER_CONFIRMED。
- T：`無登入權`（status=-2）→ CONTRADICTION（可能為 login ID 問題；待用正確登入ID 重測）。

## Quote vs Trading independence
- `docs/YUANTA_QUOTE_VS_TRADING_DEPENDENCY.md`：**NO_RUNTIME_DEPENDENCY_FOUND**
  （獨立 ProgID/Interop/登入；quote 不需 trading 同時登入）。

## Legacy overseas scope
- 官方頁名「國內行情」+ sample 僅 TAIFEX → 疑 DOMESTIC，但**未證實排除海外** →
  標 `RUNTIME_OVERSEAS_SUPPORT_UNVERIFIED`（evidence-based，不硬下結論）。

## JNU evidence
- JNU = **VERIFIED_PUBLIC_PRODUCT_CODE**（大阪微日經）。
- SPARK StkCode / Legacy quote symbol / Trading order code：全 **UNVERIFIED**（不互等）。

## SPARK StkCode / Legacy quote symbol / Trading order code status
- 三者均 **UNVERIFIED**（需開通權限後 runtime 取得，或官方對照表）。

## Certificate / Download / Quick Start / Support packet
- Certificate docs：申請/匯出/匯入/簽驗/期限 + `check_yuanta_certificate.ps1`。
- Download docs：SPARK x64/x86/C#/COM + Futures 行情/交易（含 version 差異標記）。
- `docs/YUANTA_QUICK_START_WINDOWS11.md`：14 步（command/expected/failure）+ Troubleshooting Table。
- `YUANTA_SUPPORT_EVIDENCE_PACKET.md`：無 PII，可直接給客服。

## Security
- OrderApiExposureGuard PASS；Trading API 未 import runtime；login ID 只存 WinCred；無 PII。

## Tests（19 新增）
user_permission_claim_preserved / permission_contradiction_state / legacy_login_id_not_futures_account /
legacy_login_id_wincred_only / status1_connected_only / status2_authenticated /
quote_and_trading_independent / 0112_not_auto_permission_denied / account_format_validation /
no_branch_bruteforce / jnu_public_code_only / overseas_scope_evidence_based / support_packet_no_pii /
quick_start_complete / certificate_steps_complete / downloads_steps_complete /
market_data_permission_docs_complete / trading_api_static_only / order_guard_passes。

## Remaining external questions（需營業員/客服）
1. SPARK Futures 0112：此期貨帳號的 SPARK API Futures 權限是否啟用？
2. Legacy Quote 登入ID格式（身份證ID？）；T 盤權限。
3. OSE/JNU 行情權限 + SPARK StkCode。

## 驗證
- `pytest tests/ -q` → 484 passed
- build_id 維持 `ccabe1e1552d9ae7`
- 全程未下單/查帳/持倉/餘額/損益；未 recorder；未 Live Trading；未 GitHub push。
