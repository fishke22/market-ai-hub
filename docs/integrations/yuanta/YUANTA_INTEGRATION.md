# Yuanta Integration（元大整合）

## 目前完成（Phase 2Y-A）
1. **元件盤點**：`YUANTA_COMPONENT_INVENTORY.md`（Spark API 2.2026.0918.0 + legacy COM 2.1.2.7）。
2. **安全憑證基礎**：`integrations/yuanta/credential_store.py`（Windows Credential Manager，fail-closed）。
3. **Quote-only 邊界**：`integrations/yuanta/gateway.py`（架構上無 order method）。
4. **商品 resolver 基礎**：`integrations/yuanta/resolver.py`（只解析 FunctionList，不猜 ticker）。

## 目前未完成（NO LOGIN）
- 真實 login（未登入）
- account entitlement（未查帳）
- OSE Micro quote 實測（未訂閱）
- realtime recording（DISABLED_BY_POLICY）

## 憑證
- backend：Windows Credential Manager（win32cred）。
- targets：`MARKET_AI_HUB/YUANTA/FUTURES`、`MARKET_AI_HUB/YUANTA/SECURITIES`。
- CLI：`python -m market_ai_hub.integrations.yuanta.credentials status|setup|remove`（local interactive，getpass 不 echo）。
- repository 永不保存 full account / password / PFX / certificate secret。

## 商品 resolver 結論
- OSE 市場 enum = 207（FunctionList 市場類 sheet 確認）。
- SGX 日經 NKN / 微型日經 SNS；CME 微型日經 MNIK/MNK、日經 NIY/NK（股票代碼總表確認）。
- **OSE Nikkei Micro/Mini/Large SPARK StkCode 不在 FunctionList** → 不得猜，需未來 login + market info。

## 安全邊界
- `YuantaQuoteOnlyGateway`：無 login/subscribe/order 方法（skeleton only）。
- `OrderApiExposureGuard`：掃描 order/trade method，發現 → `YUANTA_SECURITY_GATE = FAIL`。
- `SafeYuantaLogger`：不 log password/account/InvestorID/Name。
- `sanitize_login_result()`：只回 masked account + status，不回 Name/InvestorID/SellerNo。

## MCP 邊界
- 本棒不新增 login/credential/broker MCP。
- 未來 MCP 最多：`yuanta_status` / `yuanta_capabilities` / `yuanta_quote_snapshot`。
- Credential 操作永遠 local CLI。
