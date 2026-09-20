# Phase 2F — Historical Strategy Research Engine

- Gate: **PHASE2F_PASS**
- build_id: `bbf3cb2f9a80d20e`（未變，V1 相容）
- 測試：**258 passed**（154 V1 + 12 2A + 12 2B + 17 2C + 16 2D + 15 2D.1 + 14 2E + 18 2F）

## 交付內容（對照 A–S）

| 項 | 交付 | 檔案 |
|---|---|---|
| A | StrategyCandidate contract + 狀態機 | `strategy/contract.py` |
| B | point-in-time 信號資料集 | `strategy/signal_dataset.py` |
| C | 可解釋規則搜尋 | `strategy/search.py` |
| D | HistoricalEdgeStore | `strategy/edge_store.py` |
| E | 成本模型（ZERO/BASE/STRESS） | `strategy/cost.py` |
| F | Walk-forward split（TRAIN→VALIDATION→FROZEN TEST） | `strategy/walk_forward.py` |
| G | 完整 metrics | `strategy/metrics.py` |
| H | 防 overfitting guard | `strategy/overfitting.py` |
| I | Model-assisted（政策，prediction≠strategy） | `docs/HISTORICAL_STRATEGY_RESEARCH.md` |
| J | TRADE_CANDIDATE/WAIT/NO_EDGE | `strategy/output.py` |
| K | Analysis Archive link（附加 relationship） | `automation/archive.py::link_strategy` |
| L | FineTuneAdapter interface | `strategy/fine_tune.py` |
| M/N | TradingView optional bridge（design only） | `strategy/tradingview_bridge.py` |
| O | Yuanta future placeholder | `strategy/yuanta.py` |
| P | 測試（18 項） | `tests/test_phase2f.py` |
| Q | 文件（4 份繁中） | `docs/*.md` |
| R | 本報告 | `PHASE2F_STRATEGY_RESEARCH_REPORT.md` |
| S | 交接 | `CURRENT_HANDOFF.md` |

## Historical Edge Engine
- `compute_edge()` 對 forward-return series 計算：sample_size / mean / median / positive_rate /
  5% downside quantile / 95% upside quantile / MAE / MFE / EV / 95% CI / status。
- 狀態判定：CI 下限 > 0 → `EDGE_FOUND`；CI 上限 < 0 → `NO_EDGE`；其餘或樣本 < 30 → `INSUFFICIENT_EVIDENCE`。
- `search_edges()`（depth-1 單條件）、`search_condition_combos()`（depth-1~3 AND 組合）、
  `stable_across_horizons()`（多窗口仍成立的 rule）。

## Strategy candidates
- 狀態機 `EXPERIMENTAL → RESEARCH_CANDIDATE → SHADOW → REJECTED`；`PRODUCTION_TRADING` 禁止
  （`test_forbidden_status_rejected` 鎖定）。

## Walk-forward result
- `walk_forward_split(dates, n_splits, train_ratio=0.6, validation_ratio=0.2)` 產生 rolling
  (train, validation, frozen test) 三段；`assert_frozen_test` 確保 test 完全在 validation 之後。

## Cost sensitivity
- 三種成本：ZERO_COST / BASE_COST / STRESS_COST；`compute_strategy_metrics` 一律回報
  `cost_sensitivity`（net − gross mean）。`test_cost_sensitivity` 驗證有成本時 expectancy 下降。

## WAIT / NO_EDGE behavior
- `classify_output()`：無 edge / 樣本不足 → `NO_EDGE`；edge 但未過 overfitting guard → `WAIT`；
  通過 → `TRADE_CANDIDATE`。三態皆合法，不強迫每天 LONG/SHORT。

## FineTune interface
- `FineTuneAdapter`（prepare_dataset/train/evaluate/save_artifact/rollback）。
- xgboost / lightgbm / nhits / nbeatsx `supported=True`；foundation（moirai-2 / ttm / timesfm /
  chronos / kronos-tw / sundial）`supported=False`。
- 四個 enabled adapter 的 train/evaluate 為 extension point（`NotImplementedError`），
  不自動重度微調。

## TradingView bridge design
- `TradingViewResearchBridge` 介面（health / get_chart_state / get_indicator_snapshot /
  capture_chart / run_pine_research / get_strategy_tester_summary）。
- 標記 `OPTIONAL_EXTERNAL_UI_SOURCE`；無 place_order / broker_order / credentials。
- 本棒未安裝、未接線、未取任何 cookie/password/session secret。

## Yuanta realtime status
- `YuantaQuoteOnlyGateway.realtime_recorder_enabled = False`；`YuantaRecorderContract.enabled = False`。
- 本棒不要求長時間開機；文件說明未來啟用 Tick/L2 Recorder 才需交易期間開機。

## Tests
`tests/test_phase2f.py`（18 項）：point-in-time / no-lookahead / edge min-sample / edge-found /
walk-forward split / cost sensitivity / small-sample-not-edge / wait / no-edge / forbidden status /
archive link / finetune-disabled-default / tradingview optional-only / no-core-dependency /
no-credentials / yuanta-realtime-disabled / search smoke / edge-store roundtrip。

## Blockers
- 無 blocking。
- 誠實揭露：本 phase 為「研究引擎 + contract」，**未宣稱任何可獲利策略已建立**。
  要宣稱可獲利策略，需足夠 OOS + walk-forward + forward paper evidence（尚未進行）。
- TradingView 橋接未安裝（僅 design）；Yuanta 未啟用；FineTune 為 extension point。

## 驗證
- `pytest tests/test_phase2f.py -q` → 18 passed
- `pytest tests/ -q` → 258 passed
- `build_id` 維持 `bbf3cb2f9a80d20e`
