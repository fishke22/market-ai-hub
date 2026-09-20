# Yuanta Leveraged Trading API（槓桿全球贏家 Web API）

> 只使用公開 Yuanta webpages + 允許公開的高層描述。原始 spec 為 proprietary/confidential，
> 不得複製進 GitHub。

## 定位
- **槓桿全球贏家 = CFD / 槓桿保證金平台**（不是一般 Futures account）。
- 不是 Legacy Futures Quote、不是 SPARK Futures、不是 OSE Micro Futures API。

## 官方公開入口
- API 申請頁：`https://ltm.yuantafutures.com.tw/member/api-apply`
- 屬於 `ltm.yuantafutures.com.tw` = **Yuanta Leveraged Trading（槓桿全球贏家）**。
- **不要把它寫成「一般元大 Futures API 權限申請頁」。**

## 帳戶 requirement
- 公開網頁顯示：加開「槓桿全球贏家」需要**有效槓桿保證金帳號/交易密碼**。
- `LEVERAGED_API_ACCOUNT = SEPARATE_ACCOUNT_REQUIRED`。
- 這**不代表**一般期貨 T/T+1 需要槓桿帳號。

## T / T+1 定義（永久）
- T / T+1 = **futures market session labels**（日盤 / 盤後時段）。
- 不是「一般期貨帳號 vs 槓桿帳號」。
- JPX / Nikkei Futures 等 Yuanta 官方資料都有 T / T+1 時段。

## MARKET_AI_HUB target
- Primary target = `OSE_NIKKEI225_MICRO_FUTURES`，public code **JNU**。
- JNU 屬於 **JPX Futures**，不是 Nikkei CFD。
- **不需要為了 JNU 去開槓桿全球贏家帳戶。**

## 狀態
- `YUANTA_LEVERAGED_WEB_API = DOCUMENTED_ONLY / OUT_OF_SCOPE_CURRENT_PHASE`。
- 未來若要分析 FX / Gold/Silver / Oil / Index CFD / Stock CFD，可另做 integration research。
- 目前：不實作、不登入、不申請帳號、不納入 core。

## Proprietary document rule
- 「槓桿全球贏家 Web API Specification」文件標示 proprietary/confidential。
- **不得**加入 GitHub：copy PDF / screenshots / long tables / private endpoint details /
  sample credential / API key。
- GitHub docs 只能根據公開 website + 高層 interoperability facts 原創摘要。

## WebView2
- `Microsoft.WebView2.FixedVersionRuntime*.cab` = **UI_RUNTIME_DEPENDENCY**（桌面 UI 元件）。
- 不是 Yuanta API binary、不是 broker credential component、不是 certificate / account component。
- 不加入 GitHub binary；可提供 Microsoft 官方下載/說明連結。
