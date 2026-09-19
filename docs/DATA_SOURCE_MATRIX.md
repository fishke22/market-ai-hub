# DATA_SOURCE_MATRIX — 資料來源矩陣

## 台股

| Dataset | 來源 | Tier | 成本 |
|---------|------|------|------|
| TaiwanStockPrice | FinMind | FREE | 0 |
| TaiwanStockPriceAdj | FinMind | FREE | 0 |
| TaiwanStockPER | FinMind | FREE | 0 |
| TaiwanStockMonthRevenue | FinMind | FREE | 0 |
| TaiwanStockFinancialStatements | FinMind | FREE | 0 |
| TaiwanStockBalanceSheet | FinMind | FREE | 0 |
| TaiwanStockCashFlowsStatement | FinMind | FREE | 0 |
| TaiwanStockDividend | FinMind | FREE | 0 |
| TaiwanStockDividendResult | FinMind | FREE | 0 |
| TaiwanStockInstitutionalInvestorsBuySell (三大法人) | FinMind | FREE_WITH_DATA_ID | 0 |
| TaiwanStockMarginPurchaseShortSale (融資融券) | FinMind | FREE_WITH_DATA_ID | 0 |
| TaiwanStockSecuritiesLending (借券) | FinMind | FREE_WITH_DATA_ID | 0 |
| TaiwanStockDayTrading (當沖) | FinMind | FREE_WITH_DATA_ID | 0 |
| TaiwanFuturesDaily | FinMind | FREE | 0 |
| TaiwanOptionDaily | FinMind | FREE | 0 |
| 部分總經 (TaiwanStockGovernmentBondYield 等) | FinMind | UNKNOWN（依官方最新 tier 表） | 0~付費 |
| 日線全市場 (STOCK_DAY_ALL) | TWSE OpenAPI | FREE | 0 |

FinMind tier：Free / Backer / Sponsor / Sponsor Pro。第一階段只使用 Free 可存取資料。
若 dataset 需要 Backer/Sponsor → 回傳 `DATA_REQUIRES_PAID_TIER`，不付費。

## 全球市場代理（yfinance）

| Symbol | 說明 | Grade |
|--------|------|-------|
| ^N225 | Nikkei 225 INDEX（非 OSE micro futures） | RESEARCH_PROXY / DELAYED |
| USDJPY=X / JPY=X | USDJPY | RESEARCH_PROXY / DELAYED |
| NQ=F / ES=F | 美股期貨 proxy | RESEARCH_PROXY / DELAYED |
| ^VIX / ^SOX | VIX / 費半 | RESEARCH_PROXY / DELAYED |
| GC=F / CL=F | 黃金 / WTI | RESEARCH_PROXY / DELAYED |
| BTC-USD | 比特幣 | RESEARCH_PROXY / DELAYED |

yfinance 是 unofficial wrapper，Yahoo Finance 非 institutional data API。
標記：BEST_EFFORT / DELAYED_POSSIBLE / PERSONAL_RESEARCH。

## 總經（FRED）

| Series | 說明 | Grade |
|--------|------|-------|
| DGS2 / DGS10 / FEDFUNDS | 美債 2Y/10Y、聯邦基金利率 | OFFICIAL_DAILY（非高頻即時） |

需要 FRED_API_KEY（免費）。保留 observation_timestamp + retrieved_at 防 data leakage。

## 付費（僅 adapter，不購買）

| 來源 | 價格 | 用途 |
|------|------|------|
| JPX J-Quants | Free JPY0（12-week delay）/ Light 約 JPY1,650/月 / Standard 約 JPY3,300/月 / Premium 約 JPY16,500/月 | Futures OHLC 需 Premium |
| JPX J-Quants DataCube | 約 JPY143/一個月 dataset（歷史 1-min Nikkei 225 micro） | 付費歷史資料，未來升級選項 |

詳見 `docs/PAID_DATA_OPTIONS.md`。
