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
1. 先呼叫 `get_analysis_packet(market="osaka", target="OSE_NIKKEI225_MICRO_FUTURES", horizon="1d", detail_level="normal")`。
2. 只有 packet 顯示資料不足或需 audit，才呼叫個別 MCP。
3. 不得自行抓數十個 raw MCP result。

## Required checks
- OSE Micro = TARGET；OSE Mini/Large/Spot/TOPIX/SGX/CME = REFERENCE；^N225 = PROXY。
- Micro 只有 settlement → 標 `SETTLEMENT`，不得稱 LIVE_PRICE/CLOSE。
- ensemble 未 forward-validated → 標 `RESEARCH_ENSEMBLE / UNVALIDATED_FORWARD`。

## Output structure
- 偏多/偏空/盤整
- 主要區間（model_range）
- 支撐/壓力（support_levels / resistance_levels）
- 失效條件（invalidation_levels）
- 何種情況可研究型進場、何種情況 WAIT
- 何時重新分析（reanalysis_conditions）

## Failure handling
- 資料不足 → 明說缺口，不編數字。
- provider 失敗 → 依 packet 標記 degraded/missing，不 silent。

## Do not rules
- 不得把 ^N225 寫成「大阪微型日經成交價」。
- 不得製造假 probability。
- 不得虛構 Micro OHLC。
