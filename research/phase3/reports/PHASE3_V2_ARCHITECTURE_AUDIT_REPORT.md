# PHASE 3-V2 ARCHITECTURE AUDIT — MASTER REPORT

- **Date**: 2026-09-22
- **Branch**: audit-only (read-only)
- **Baseline verified**: main = `2921bd3846731d217555951e6356353c07c4c9f3` (= origin/main, clean);
  runtime build_id `c7417f7c4cbfb388`; schema `3A.2.3`; MCP tools = **21**; data root `D:\MARKET_AI_HUB\data`.

## Plain-language answers

### 1. 目前真正有哪些 raw data？
Daily-frequency only:
- OSE Nikkei 225 Micro daily bars (`data/normalized/ose_micro/ose_micro_daily_bar_v1.parquet`, 960 rows) + preclose snapshots (330 rows).
- JPX OSE settlement (`data/raw/jpx/settlement/…rb20260918.parquet`, 39 rows).
- TWSE daily OHLCV (`data/cache/twse/`, 916 daily snapshots).
- TAIFEX daily cache (1 file), US Treasury daily (1 file).
- Feature store DuckDB (only `close` for `^N225`, 547 rows).
- `data/validation_samples/2026-09-21/fresh_validation_sample.json`.

### 2. 各自 frequency？
All **daily**. No intraday anywhere.

### 3. 哪裡有 1-minute？
**Nowhere.** No 1m data for any target.

### 4. 哪裡有 tick？
**Nowhere.**

### 5. 有沒有 L1？
**No.** (NO_L1_FOUND)

### 6. 有沒有 L2？
**No.** (NO_L2_FOUND)

### 7. Nasdaq / USDJPY / SOX / VIX / US yields / Brent / WTI 各自現在有沒有？
- US yields: `US Treasury daily` provider + 1 cache file — **YES (daily)**.
- FRED macro: provider configured (WinCred key) — **YES (daily/periodic)**.
- Nasdaq futures / USDJPY / SOX / VIX / Brent / WTI: **NO dedicated provider**; only reachable
  indirectly via `yfinance` generic symbols; `forecast/leakage.py` names `NQ_tomorrow/USDJPY_tomorrow/
  VIX_tomorrow/SOX_tomorrow` as *unknown-future* fields but no first-class data source. **NOT_AVAILABLE as a managed dataset.**

### 8. timestamps 是否真的統一？
**Partially.** `data/timezones.py` enforces UTC storage + rejects naive datetimes. The feature store
has `event_time` + `available_at`. But there is **no** canonical
`event/observed/source/ingested/feature_cutoff/forecast_origin` taxonomy, and no revision-aware
point-in-time loader.

### 9. 最大的 look-ahead risks？
1. Future intraday VWAP / session-high-low / volume-profile built without an as-of bound (HIGH).
2. Prior-day US close used as a live intraday signal.
3. Contract-roll splice into a label.
4. (Currently low) `future_return_*` labels are correctly excluded from features — verified.

### 10. 目前 feature 已有哪些？
`returns, log_returns, rolling_volatility, atr, rsi, ema_10/20, sma_20, distance_from_ma20,
rolling_high_20, rolling_low_20, realized_volatility_20, volume_change, time_of_day, day_of_week`
(+ `future_return_1/3` labels). No VWAP/volume-profile/session-high-low/extension/exhaustion features.

### 11. 目前 label 怎麼做？
Regression: `future_return_k = close.shift(-k)/close - 1`.
Classification: 3-class `> +0.5% / flat / < -0.5%` (threshold 0.005). Single chronological split,
not rolling walk-forward.

### 12. 目前模型真正預測什麼？(full matrix)

| Model | task | target | role/scope | input freq | output freq | horizon | prediction semantics | direction | probability | calibration | hist evidence | fwd evidence |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| VAR(1) | direct micro forecast | OSE micro | DIRECT | daily | daily | 1d | return/level forecast | dir_acc 0.622, MCC 0.241 | none (point) | none | `STATISTICAL_FORECAST_EVIDENCE` | NONE_YET |
| chronos-2 | PRICE_FORECAST | ^N225 (proxy) | PROXY | daily | daily | 1/2/5/10d | per-step quantile path p10/p50/p90 | none | quantile path (research) | none | NO_EVIDENCE | NONE_YET |
| timesfm-3.0 | PRICE_FORECAST | ^N225 (proxy) | PROXY | daily | daily | 1/2/5/10d | per-step quantile path | none | quantile path (research) | none | NO_EVIDENCE | NONE_YET |
| xgboost | DIRECTION_CLASSIFICATION | any (daily) | — | daily | daily | 1/2/5/10d | 3-class | yes (3-class) | none | none | NOT_YET_VALIDATED | NONE_YET |
| lightgbm | DIRECTION_CLASSIFICATION | any (daily) | — | daily | daily | 1/2/5/10d | 3-class | yes | none | none | NOT_YET_VALIDATED | NONE_YET |
| nhits / nbeatsx | PRICE_FORECAST | — | — | daily | daily | 1/2/5/10d | point path | none | none | none | CHALLENGER (not available) | — |
| fincast | PRICE_FORECAST | — | — | daily | daily | 1/2/5/10d | point | none | none | none | PARTIAL (CPU bridge) | — |
| moirai-2 / sundial / kronos-tw / tinytimemixer | PRICE_FORECAST | — | — | daily | daily | 1/5/10d | point/quantile | none | varies | none | CHALLENGER | — |
| ensemble | dynamic ensemble | ^N225 | — | daily | daily | 1d | combined forecast | — | research quantile summary | none | NOT_YET_VALIDATED | NONE_YET |

**No model predicts a predictive distribution, touch/break/acceptance, or intraday state.**

### 13. 目前 probability 到底哪些 calibrated？
**None.** All public probabilities are `NOT_AVAILABLE`. The 3A.2.x contract is a **typed schema /
fail-closed gate**, not calibrated probability.

### 14. 目前 backtest 哪些可信到什麼程度？
- `TRUSTED_FOR_ENGINEERING`: walk-forward harness, splits, build fingerprint.
- `STATISTICAL_EVIDENCE`: only VAR(1) direct-micro (MASE 0.958, dir_acc 0.622) — and it is
  `NON_EXECUTABLE_FORECAST_EDGE`.
- `CONTAMINATED_FOR_SELECTION`: any model chosen on the same OOS used for reporting (guard in
  tournament `data_quality.py` / `leakage-auditor`).
- `NOT_YET_VALIDATED`: Taiwan stock/index, all challengers, forward.

### 15. 哪些新功能可以直接施工？
As-of/timestamp contract + schema, gap/overnight decomposition (daily), state-machine scaffold
(daily), daily barrier labels (touch/break/acceptance), Prediction Audit DB schema, catalyst
response (daily cross-market).

### 16. 哪些需要新資料？
Intraday bars (1m/5m/…), VWAP/volume-profile/session-high-low, L1, L2, order events, true
futures-cash basis on holiday days.

### 17. 2026-09-22 案例真正揭露什麼系統缺口？
The system cannot express the `Bullish → Extended → Acceptance Failed → Exhaustion Warning →
CHASE_RISK STOP → Downgrade` sequence: no intraday data, no state machine, no acceptance/
exhaustion labels, no chase-risk state, and (TSE cash closed) no degraded-basis handling.

### 18. 哪些需求可能只是單日 overfit？
Any rule derived from the specific levels 66990/67045/66515/66445/66282; any "must fade high
opens" rule. All such are `HYPOTHESIS_ONLY` pending proper validation.

### 19. V2 Core 建議包含什麼？
As-Of Data Layer, Intraday Session Semantics, Gap/Overnight Decomposition, State Machine,
Touch/Break/Acceptance labels, Extension/Exhaustion features, Catalyst Response, Sequential
Updating, Prediction Audit DB.

### 20. 哪些先 deferred？
True order-flow, L2 depth, non-core LLM layers, intraday-dependent research until data exists.

### 21. 下一個最小施工 Phase 應該是什麼？
**V2-A — As-Of / Timestamp / Data Truth** (canonical timestamp taxonomy + point-in-time loader +
stale/reference status). It is `BUILDABLE_NOW`, unlocks every later phase, and is pure schema/
plumbing (no fitting, no new prediction behavior).

## GO / CONDITIONAL_GO / BLOCKED matrix

| Module | Decision | Reason |
|---|---|---|
| V2 Core (as-of/session/state/labels/audit-db schema) | **GO** | daily data + existing typed-contract foundations |
| Intraday State Engine | **CONDITIONAL_GO** | daily scaffold buildable now; intraday needs data |
| Multi-Target Labels | **CONDITIONAL_GO** | daily barrier labels buildable; intraday variants data-dependent |
| Catalyst Response | **CONDITIONAL_GO** | daily cross-market buildable; live intraday needs data |
| Order Flow | **BLOCKED** | no L1/L2/order events |
| 1m Taiwan | **BLOCKED** | no 1m data |
| 1m Osaka | **BLOCKED** | no 1m data |
| L1 | **BLOCKED** | no L1 source |
| L2 | **BLOCKED** | no L2 source |
| Prediction Audit DB | **GO (schema)** | no data dependency |

## Deliverables (this audit)

`research/phase3/v2_audit/`: CURRENT_ARCHITECTURE_AUDIT, DATA_SOURCE_AUDIT, FEATURE_GAP_ANALYSIS,
MARKET_STATE_MACHINE_DESIGN, MULTI_TARGET_LABEL_DESIGN, ORDER_FLOW_FEASIBILITY,
IMPLEMENTATION_ROADMAP_V2, LABEL_LEAKAGE_AUDIT, TEMPORAL_ASOF_AUDIT, INTRADAY_DATA_FEASIBILITY,
CASE_STUDY_2026_09_22, MARKET_AI_HUB_ARCHITECTURE_V2_FREEZE_DRAFT.
