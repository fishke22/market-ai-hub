# Phase 2G.1 — True Target + Official Data Coverage Hardening

- Gate: **PHASE2G1_PASS**
- build_id: `bbf3cb2f9a80d20e`（未變，V1 相容）
- 測試：**290 passed**（279 既有 + 11 2G.1）

## 交付內容（對照 1–10）

| 項 | 交付 | 檔案 |
|---|---|---|
| 1 | TargetInstrumentContract + TARGET/REFERENCE/PROXY | `targets/contract.py` |
| 2 | JPXOSEDailyReportProvider + parser + incremental downloader | `targets/jpx_daily.py` |
| 3 | ContinuousFuturesBuilder（versioned + roll provenance） | `targets/continuous.py` |
| 4 | Micro forecast semantics（return/normalized/basis/anchor/label） | `targets/semantics.py` |
| 5 | Yuanta capability matrix | `docs/YUANTA_DATA_CAPABILITY_MATRIX.md` |
| 6 | Official event providers（11 家）+ information_cutoff | `targets/events.py` |
| 7 | DataCoverageAuditor（5 級 status） | `targets/coverage.py` |
| 8 | NautilusTraderAdapter interface + forecast≠backtest | `targets/backtest_contract.py` |
| 9 | MCP policy（預留 4 tools，TradingView 保持 OPTIONAL） | `targets/backtest_contract.py` |
| 10 | 測試（11 項）+ report + handoff | `tests/test_phase2g1.py` |

## True Execution Target
- `execution_target = OSE_NIKKEI225_MICRO_FUTURES`（`targets/contract.py`）。
- 不得再把 `^N225` 稱為最終交易標的（`role_of("^N225") == PROXY`）。
- 研究參考分開：OSE_MICRO（TARGET）/ OSE_MINI / OSE_LARGE / NIKKEI_SPOT / SGX_NIKKEI / CME_NIKKEI（REFERENCE）/ ^N225（PROXY）。
- 所有輸出一律標 TARGET / REFERENCE / PROXY，不得混稱。

## JPX OSE Daily Data
- `JPXOSEDailyReportProvider.download_incremental(fetcher, start, end, product)`：增量 archive downloader
  （fetcher 可注入/mock；寫 parquet + 由 DataLakeManager 管理）。
- `parse_daily_report()` 解析 Micro / Mini / Futures 的 OHLCV + settlement + source_hash。
- `MICRO_LISTING_DATE = 2023-05-29`；`assert_micro_not_before()` 拒絕上市前 Micro；
  parser 直接跳過上市前 Micro（不偽造）。

## Continuous Futures
- `ContinuousFuturesBuilder` 保留 RAW contract data，另產 continuous research series。
- 紀錄 `roll_dates` / `roll_method` / `adjustment_method`。
- adjusted continuous price 標 `is_executable_price=False`，不得冒充真實可成交價。

## Micro Forecast Semantics
- 優先預測 Micro return / normalized move / Micro-Mini basis，再 anchor 到 actual Micro price。
- `label(has_micro_actual)`：False → `PROXY_TRAINED_MICRO_ANCHORED`；True → `DIRECT_MICRO_MODEL`。
- Mini/Large/SGX/CME 是 covariate/reference，不是 Micro 真實價格。

## Yuanta Capability
- `GetKLine`：僅 TWSE/TWOTC 歷史 K 線 → 台股 Data Lake（ACTIVE）。
- `GetStkTickDetail` / `GetStkClassifyPrice`：保留 capability probe；realtime disabled。
- `Watchlist/FiveTick`：disabled。本棒不登入、不啟動 Recorder。

## Official Event Providers
- 11 家 backend providers（BLS/BEA/Fed/BOJ/e-Stat/Cabinet Office/MOF/EIA/SEC EDGAR/EDINET/Cboe）。
- 事件 schema：event_name / scheduled_at / released_at / source / importance_class / available_at。
- `event_visible(events, information_cutoff)` 遵守 information_cutoff（未 released 不得可見）。
- EDINET 標 CONFIG_ONLY（API key 未存在）。

## Data Coverage Auditor
- `DataCoverageAuditor`：AUTHORITATIVE / OFFICIAL_DELAYED / RESEARCH_PROXY / OPTIONAL / MISSING。
- 大阪模型 28 個 factor 全 audit；誠實預設大多 RESEARCH_PROXY / MISSING，**未宣稱全部 authoritative**。

## Backtest Contract
- 保留 FEV / OOS / Walk-forward / Forward Paper 作模型預測驗證。
- `NautilusTraderAdapter`（interface，`live_execution_enabled=False`）。
- `evaluation_kind()`：Forecast Evaluation ≠ Trading Strategy Backtest。
- TradingView Strategy Tester 只能 `SECONDARY_VALIDATION`。

## MCP Policy
- 不新增大量外部 MCP；官方 API 做 MARKET_AI_HUB provider。
- 預留 tools：`get_data_coverage` / `get_event_calendar` / `get_official_release_snapshot` /
  `get_target_instrument_state`。TradingView 保持 OPTIONAL。

## Tests
`tests/test_phase2g1.py`（11 項）：micro_target_identity / proxy_not_target / JPX_micro_parser /
no_fake_pre2023_micro / JPX incremental clamp / continuous_roll_provenance / proxy_trained_label /
event_information_cutoff / event providers registry / coverage_audit / forecast_vs_strategy_backtest_separation。

## Blockers
- 無 blocking。
- 誠實揭露：JPX 官方 CSV 實際欄位格式與下載 URL 未連線驗證（parser 依最小欄位集 + injectable fetcher）；
  本棒不登入 Yuanta、不啟動 Recorder；官方 provider 皆為 backend contract（未接實網）。

## 驗證
- `pytest tests/test_phase2g1.py -q` → 11 passed
- `pytest tests/ -q` → 290 passed
- `build_id` 維持 `bbf3cb2f9a80d20e`
