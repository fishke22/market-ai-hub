# Yuanta OneAPI Version Capabilities（原創摘要，非複製原 PDF）

> 只做 capability/version research 原創摘要。原 `YuantaOneHis.pdf` 為 proprietary，不入 GitHub。
> 只記錄公開/高層 version→capability 對應。

## 版本 → 能力（時間線摘要）

| 時間 | 變更 |
|---|---|
| 2021/06 | 期貨報價代碼 7xxx 變更規則；FunctionList 商品檔更新 |
| 2023/07 | 新增期貨 / 海期下單能力；FunctionList 商品檔更新 |
| 2024/08 | 新增期貨、國際期貨庫存查詢 |
| 2024/09 | 多商品 SubscribeFiveTicks / SubscribeStockTicks / SubscribeWatchlists |
| 2025/02 | futures-account detection；login failure disclosure；futures margin optimization；futures combined order；international futures inventory handling |
| 2025/12 | threading changes；login / disconnect / reconnect example updates |

## 對 MARKET_AI_HUB 的意義
- **期貨報價代碼 7xxx 規則**（2021/06）：這是有關「legacy OneAPI 期貨報價代碼」的歷史變更，
  屬**另一套 legacy 命名空間**，與 SPARK StkCode / OSE Micro（JNU）無關。
- **國際期貨庫存查詢**（2024/08）＋ **international futures inventory handling**（2025/02）：
  顯示 SPARK 支援國際期貨（含 OSE）庫存/商品處理 —— 支持「OSE Micro 行情走 SPARK Futures」
  的路徑（開通權限後）。
- 本棒**不登入、不下單、不查庫存**；此文件只記錄 version capability。

## 注意
- 原 PDF 標 proprietary/confidential → 不入 GitHub（見 `PUBLICATION_EXCLUDE_MANIFEST.txt`）。
