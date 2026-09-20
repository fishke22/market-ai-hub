# Yuanta Setup & Login（總導航 — 第一個讀這個）

**元大 API 有四條 family（SPARK / Futures Legacy Quote / Futures Legacy Trading /
Leveraged Trading 槓桿全球贏家 Web API）。不要混用。**

## ⚠️ 不要到「槓桿全球贏家」API 申請頁申請一般 Futures API

- `https://ltm.yuantafutures.com.tw/member/api-apply` 是**槓桿全球贏家（CFD/槓桿保證金）**的申請頁。
- 若你的目標是 **OSE Micro / JNU（JPX Futures）**，應走**一般 Futures / SPARK / 正式 Futures API** 的權限與行情路徑。
- 槓桿全球贏家需要**獨立槓桿保證金帳號**，與一般期貨帳號分開。

## 決策樹

```
IF SECURITIES → SPARK（docs/YUANTA_SECURITIES_SPARK.md）
IF FUTURES    → 兩條路：
                 行情：Legacy Quote COM（docs/YUANTA_FUTURES_COM.md）
                 或 SPARK（需期貨帳號另開 SPARK 權限）
IF 槓桿/CFD  → Leveraged Trading Web API（docs/YUANTA_LEVERAGED_TRADING_API.md，OUT_OF_SCOPE）

Futures account + SPARK → 0112
  => 官方定義：無此權限使用功能
  => 檢查該 Futures account 是否已申請 SPARK API permission
  => 聯繫營業員/客服確認
```

## 快速判斷

| 我要… | 用哪套 | 文件 |
|---|---|---|
| 登入證券 | SPARK | YUANTA_SECURITIES_SPARK.md |
| 登入期貨（行情） | Futures Quote COM（或 SPARK 開權限後） | YUANTA_FUTURES_COM.md |
| 期貨帳號回 0112 | **SPARK 權限未開**，申請 SPARK permission | YUANTA_API_PERMISSIONS.md |
| 查商品代碼 | 四種代碼分離，不混用 | YUANTA_PRODUCT_CODE_LOOKUP.md |

## CLI

```powershell
# 證券（Spark x64）
.venv\Scripts\python.exe -m market_ai_hub.integrations.yuanta.auth_probe --profile securities

# 期貨行情（COM x86 sidecar）
powershell -ExecutionPolicy Bypass -File scripts\yuanta_futures_auth.ps1
```

## 帳號/密碼
- 帳號只存 Windows Credential Manager，畫面只顯示 masked。
- 密碼只透過 `getpass()` 本機輸入，不落檔、不經 MCP。

## 下載 / 憑證 / 權限 / 商品代碼
- `docs/YUANTA_DOWNLOADS.md`、`docs/YUANTA_CERTIFICATE_WINDOWS11.md`
- `docs/YUANTA_API_PERMISSIONS.md`、`docs/YUANTA_MARKET_DATA_PERMISSIONS.md`
- `docs/YUANTA_PRODUCT_CODE_LOOKUP.md`、`config/yuanta_product_codes.yaml`
- `docs/YUANTA_LEVERAGED_TRADING_API.md`（槓桿全球贏家，另開帳戶）

## 相關文件
- `docs/YUANTA_API_ARCHITECTURE.md`（四條 family 總表）
- `docs/YUANTA_SECURITIES_SPARK.md`、`docs/YUANTA_FUTURES_COM.md`
- `docs/YUANTA_FUTURES_ERROR_CODES.md`、`docs/YUANTA_FUTURES_TRADING_API_FUTURE.md`
- `docs/YUANTA_SUPPORT_CHECKLIST.md`
