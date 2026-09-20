# PAID_DATA_OPTIONS — 付費資料升級選項（本階段不購買）

## A. JPX J-Quants API

- 官網: https://jpx-jquants.com
- 方案（已知官方架構，實際以官方最新價格為準）：
  - Free: JPY 0（資料有約 12 週 delay）
  - Light: 約 JPY 1,650 / 月
  - Standard: 約 JPY 3,300 / 月
  - Premium: 約 JPY 16,500 / 月
- Futures OHLC 需 Premium
- 本專案 adapter: `src/market_ai_hub/providers/jquants.py`（enabled=false）
- 若未來使用者自備 key 並自行訂閱，才啟用 adapter

## B. JPX J-Quants DataCube

- 可購買 Nikkei 225 micro futures 的 one-minute historical data
- 官方歷史價格範例：個人/學術用途約 JPY 143 / 一個月 dataset
- 價格依月份、用途與官方最新定價調整
- 用途：把大阪日經從 PROXY 升級為「真 OSE micro 歷史資料訓練」
- 本階段：DO NOT PURCHASE

## C. 其他潛在合法來源（未來評估，不承諾）

- 使用者自備合法 broker feed / 官方 API / 合法 MCP
- 使用者提供 TradingView 合法 integration 授權
- 台灣期交所 (TAIFEX) 官方歷史資料產品

## 原則

- 系統永不自動購買
- 付費來源只會以 disabled adapter 存在
- 免費 fallback 永遠可用
