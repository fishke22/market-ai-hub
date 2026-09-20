# Yuanta Security（元大安全邊界）

## 硬性禁止（本棒及未來）
- NO LOGIN（本棒）
- NO QUOTE SUBSCRIPTION
- NO ACCOUNT / POSITION QUERY
- NO ORDER / CANCEL / MODIFY
- NO LIVE TRADING

## Credential 原則
- 只用 Windows Credential Manager（win32cred）；非 WinCred → **FAIL CLOSED**。
- 真實完整 account 只存在：1) WinCred，2) 登入當下 process memory。
- 不得存在 .env / json / yaml / DuckDB / Parquet / logs / tests / docs / MLflow / MCP response。
- 專案最多保存：profile / credential_target / masked_account / verified_branch_code / verified_at。

## Sanitizer
- `sanitize_login_result()`：只回 connected / profile / masked_account / status_code /
  permission_state / timestamp。**不回 Name / InvestorID / SellerNo**。

## Order API Guard
- `OrderApiExposureGuard` 掃描 integrations/yuanta、mcp/server.py、skills、examples。
- 發現 order/trade method → `YUANTA_SECURITY_GATE = FAIL`。
- `YuantaQuoteOnlyGateway` 架構上無 order method（不是 prompt 限制）。

## GitHub
- vendor/、*.dll、*.pfx、*.p12、FunctionList 原檔 → gitignore。
- 只提交 `vendor_manifest.json`（file names/version/SHA256，無帳號）。

## Secret scan
- 偵測：元大帳號格式 pattern、password keywords、InvestorID、PFX、certificate、credential export。
- 只顯示 path + rule + masked match，不打印秘密內容。
