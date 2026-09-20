# Yuanta Market Data Permissions（行情權限/訂閱）

狀態標記：`VERIFIED` / `UNKNOWN` / `NEEDS_BROKER_CONFIRMATION`。

| 問題 | 答案 | 狀態 |
|---|---|---|
| API 行情權限在哪申請 | 期貨線上服務 → 線上服務 → API 行情服務風險預告暨申請使用聲明書 | VERIFIED（路徑） |
| API 交易權限在哪申請 | 期貨線上服務 → API 交易服務風險預告暨申請使用聲明書 | VERIFIED（路徑） |
| SPARK futures permission 如何確認 | 期貨帳號 SPARK Login 回 0112 = 無此權限 → 需另申請；聯繫營業員 | VERIFIED（0112 語義） |
| legacy quote API 是否需申請 | 已可登入（T+1 盤成功）；T 盤「無登入權」需確認 | NEEDS_BROKER_CONFIRMATION |
| 海外行情是否另收費/另開權限 | 國外期貨行情可能另有訂閱/權限/費用 | NEEDS_BROKER_CONFIRMATION |
| MultiCharts 外期行情服務 | 獨立產品 | VERIFIED（獨立） |
| TradingView entitlement 與 Yuanta entitlement | 無關（不同平台） | VERIFIED |

## Legacy COM scope（重要）
官方公開頁把 legacy Quote 命名為「**國內行情 API**」，且本地 sample/Setup.ini 僅 TAIFEX 國內商品。
→ `legacy_com_scope` 疑為 **DOMESTIC_ONLY**；若確認，則**不用它找 JNU（OSE 國外期貨）**。
OSE Micro realtime 改走 **SPARK Futures**（開通權限後）。
