# Osaka Micro Analysis（大阪微型日經分析）

真正分析標的：**大阪日經225微型期貨（JNU）**。JNU / JNUxxxx / 大阪微日經都是同一商品。

## 觸發
使用者要分析大阪日經、微型日經、日經期貨時。

## 工作流程
1. 優先呼叫 `analyze_jnu(horizon="1d")`，使用大阪微型期貨自己的官方限月資料與直接價格模型。
2. 需要大盤／跨市場背景時才呼叫 `analyze_osaka_nikkei`；它只是日經225現貨輔助資料。
3. 需要正式資料狀態或 audit 時再呼叫 `get_analysis_packet` / coverage / event tools；不得把內部狀態碼原樣貼給一般使用者。

## Fast path + Tool budget（§17/§18/§19/§26）
- **QUICK_FORECAST**（預設）：target MCP budget = 1（`get_analysis_packet` compact）；maximum normal calls = 2。
- **FULL_ANALYSIS**：1 primary packet + only missing-evidence calls；maximum = 4。
- **MODEL_AUDIT**：allow deeper calls（predict_* / leaderboard / gates）。
- **SYSTEM_STATUS**：prefer health/status only；maximum 2 calls。
- packet 已含 Chronos/TimesFM/XGB/LGBM/Ensemble 結果時，**不得**重複呼叫 `predict_chronos` / `predict_timesfm` / `predict_ensemble`（除非 explicit MODEL_AUDIT 或 packet 缺失）。

## 目標區分（強制）
| 名稱 | 角色 |
|---|---|
| OSE Nikkei 225 Micro Futures | **TARGET**（execution target） |
| OSE Mini / Large / Nikkei Spot / TOPIX / SGX / CME | REFERENCE |
| ^N225 | PROXY |

- 不得把 `^N225` 寫成「大阪微型日經目前成交價」。
- Micro 若只有 settlement／volume／OI，必須標 `SETTLEMENT`，不得稱 `LIVE_PRICE`／`CLOSE`。
- 不得虛構 Micro OHLC。

## 輸出白話結論（使用者導向）
- 商品、實際限月、最新官方價格與日期。
- 直接價格模型的下一交易日預測、偏多／偏空／中性與參考範圍。
- 日經225現貨只在需要時作輔助背景，不能冒充微型期貨。
- 說明確認條件、反向條件、失效條件；沒有可靠支撐壓力就省略。
- 一般回答不得顯示內部變數、英文狀態碼、true/false/null。
- 未完成校準就只說「機率尚在累積驗證」，不得製造假機率。
