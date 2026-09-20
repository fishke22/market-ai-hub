# Osaka Micro Analysis（大阪微型日經分析）

真正交易標的：**OSE Nikkei 225 Micro Futures**（`OSE_NIKKEI225_MICRO_FUTURES`）。

## 觸發
使用者要分析大阪日經、微型日經、日經期貨時。

## 工作流程
1. 優先呼叫 `get_analysis_packet(market="osaka", target="OSE_NIKKEI225_MICRO_FUTURES", horizon="1d", detail_level="compact")`。
2. 只有當 packet 顯示「資料不足」或需要 audit，才呼叫個別 MCP tool
   （`get_data_coverage` / `get_event_calendar` / `get_target_instrument_state`）。
3. 不得自行抓取數十個 raw MCP result；數值資料一律由 backend 提供。

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
- 目前偏多／偏空／盤整
- 主要區間（model_range）
- 重要支撐／壓力（support_levels／resistance_levels）
- 失效條件（invalidation_levels）
- 何種情況可考慮「研究型進場」、何種情況應 WAIT
- 何時需要重新分析（reanalysis_conditions）
- **不得製造假 probability**；ensemble 未 forward-validated 要標 `RESEARCH_ENSEMBLE / UNVALIDATED_FORWARD`。
