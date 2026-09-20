# Yuanta Quote API Inventory（只盤點，不呼叫）

來源：`FunctionList.xlsx`（功能對照表 + IO_Doc/*.doc）。本棒**不呼叫任何 method**。

| method | purpose | historical/current | market support | account required | tested | risk | planned use |
|---|---|---|---|---|---|---|---|
| SubscribeWatchlistAll | 訂閱全部 watchlist | current | TW/海外 | 需 login | NO | streaming | 未來 OSE 商品發現 |
| SubscribeWatchlist | 訂閱指定 watchlist | current | TW/海外 | 需 login | NO | streaming | 未來 OSE quote |
| SubscribeFiveTickA | 訂閱五檔 | current | TW/海外 | 需 login | NO | streaming | 未來 order book |
| SubscribeStocktick | 訂閱逐筆 tick | current | TW/海外 | 需 login | NO | streaming | 未來 recorder |
| GetStkTickDetail | 當日 tick 明細 | current day | TW/海外 | 需 login | NO | current-only | capability probe |
| GetStkClassifyPrice | 當日分價量 | current day | TW/海外 | 需 login | NO | current-only | capability probe |
| GetQuoteList | 取得自選即時報價（ID 100001） | current | TW/海外 | 需 login | NO | current | 未來 snapshot |
| SubscribeMarketInformation | 訂閱市場資訊 | current | TW/海外 | 需 login | NO | streaming | 未來 market status |
| GetKLine | 歷史 K 線 | historical | 僅 TWSE/TWOTC | 需 login | NO | historical | 台股 Data Lake |

## 注意
- `GetKLine` 僅 TWSE/TWOTC 歷史 K 線，**不含 OSE 期貨歷史**。
- 海外（SGX/CME/OSE）quote 需 login + entitlement，本棒未驗證。
- 不因 method 存在就標 SUPPORTED_BY_ACCOUNT。
