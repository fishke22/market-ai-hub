# Osaka Micro Analysis（大阪微型日經分析）

## Purpose
分析大阪日經，輸出研究結論。真正交易標的是 **OSE Nikkei 225 Micro Futures**。

## When to use
使用者要分析大阪日經、微型日經、日經期貨時。

## Required MCP
- `get_analysis_packet`（主入口，必備）
- `get_data_coverage`（資料缺口）
- `get_event_calendar`（BOJ/Fed/CPI/NFP）
- `get_target_instrument_state`（真正標的狀態）

## Workflow
1. 先呼叫 `get_analysis_packet(market="osaka", target="OSE_NIKKEI225_MICRO_FUTURES", horizon="1d", detail_level="compact")`。
2. 只有 packet 顯示資料不足或需 audit，才呼叫個別 MCP。
3. 不得自行抓數十個 raw MCP result。

## Fast path + Tool budget（§17/§18/§19/§26）
- **QUICK_FORECAST**（預設）：target MCP budget = 1（`get_analysis_packet` compact）；maximum normal calls = 2。
- **FULL_ANALYSIS**：1 primary packet + only missing-evidence calls；maximum = 4。
- **MODEL_AUDIT**：allow deeper calls（predict_* / leaderboard / gates）。
- **SYSTEM_STATUS**：prefer health/status only；maximum 2 calls。
- packet 已含 Chronos/TimesFM/XGB/LGBM/Ensemble 結果時，**不得**重複呼叫 `predict_chronos` / `predict_timesfm` / `predict_ensemble`（除非 explicit MODEL_AUDIT 或 packet 缺失）。

## Required checks
- OSE Micro = TARGET；OSE Mini/Large/Spot/TOPIX/SGX/CME = REFERENCE；^N225 = PROXY。
- Micro 只有 settlement → 標 `SETTLEMENT`，不得稱 LIVE_PRICE/CLOSE。
- ensemble 未 forward-validated → 標 `RESEARCH_ENSEMBLE / UNVALIDATED_FORWARD`。

## Direction（§23）
- **只有 `eligible_direction_vote_count > 0` 才可正式輸出方向。**
- `= 0` → `NO_VALIDATED_MODEL_CONSENSUS`，不得輸出 Up / Down / Flat。
- `model_agreement=HIGH`（raw）在 votes=0 時**不是** validated consensus，不得引用。

## Support / resistance（§23）
- `support_resistance_status == NOT_AVAILABLE` → 直接輸出 `NOT_AVAILABLE`。
- **不得由 P10/P90 quantile 生成支撐/壓力/停損/失效點。**
- P10/P90 只能叫「模型統計參考區間（model statistical reference range）」。

## Output structure
- 方向（僅 eligible votes > 0 時）
- 主要區間（model_range，標 statistical reference）
- 支撐/壓力：`NOT_AVAILABLE`（無正式 evidence 時）
- 失效條件：僅 explicit validated invalidation evidence 才提供
- 何時重新分析（reanalysis_conditions）
- **不得輸出：進場 / 買點 / 黃金買點 / 加碼 / 減碼 / 做多 / 做空 / 停損價 / 獲利了結**

## Calendar（§43）
- TSE cash（XTKS）休市日與 OSE derivatives Holiday Trading 不同，不得混。
- 2026-09-21/22/23：TSE cash closed，但 OSE derivatives OPEN（依 `next_ose_derivatives_sessions`）。

## Failure handling
- 資料不足 → 明說缺口，不編數字。
- provider 失敗 → 依 packet 標記 degraded/missing，不 silent。

## Do not rules
- 不得把 ^N225 寫成「大阪微型日經成交價」。
- 不得製造假 probability（uncalibrated 不得稱上漲/下跌機率）。
- 不得虛構 Micro OHLC。
- 不得把 ^N225 forecast 冒充 Direct Micro forecast（`direct_micro_forecast_status=NOT_AVAILABLE`）。
- 不得輸出任何交易建議（research reference only）。
