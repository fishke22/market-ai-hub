# CURRENT ARCHITECTURE AUDIT (V2)

- **Audit date**: 2026-09-22
- **Branch**: audit-only, read-only inspection
- **Baseline**: main = `2921bd3846731d217555951e6356353c07c4c9f3`, build_id `c7417f7c4cbfb388`, schema `3A.2.3`

Status legend: `IMPLEMENTED` / `PARTIAL` / `INTERFACE_ONLY` / `NOT_IMPLEMENTED` / `DEFERRED`.
Every status below is derived from actual code paths + on-disk data, **not** from README.

## Layer status table

| Layer | Status | Evidence |
|---|---|---|
| Data Sources (providers) | `IMPLEMENTED` (daily HTTP only) | `src/market_ai_hub/providers/*.py` (twse, finmind, taifex, fred, ustreasury, yfinance, jquants, cftc_cot, boj, tradingview_broker) |
| Data Quality | `PARTIAL` | `services/data_consistency.py`, `services/validation.py`, `research/tournament/data_quality.py`; no continuous drift monitor beyond forward-shadow |
| Data Lake | `PARTIAL` | `automation/data_lake.py` + `storage/duckdb_store.py`; on-disk only parquet/duckdb, no full lake pipeline |
| Feature Store | `PARTIAL` | `feature_store/store.py`, `feature_store/panel.py`, `data/feature_store/features.duckdb` (only `close` for `^N225`, 547 rows) |
| Calendar | `IMPLEMENTED` (daily/session) | `services/calendar.py`, `config/ose_derivatives_calendar.yaml` (holiday-trading verified) |
| Target Semantics | `IMPLEMENTED` | `config/primary_targets.yaml`, `targets/semantics.py`, `services/primary_targets.py`, `services/research_truth.py` |
| Forecast Models | `PARTIAL` | chronos-2 / timesfm-3.0 / xgboost / lightgbm = `AVAILABLE`; fincast `PARTIAL`; nhits/nbeatsx/moirai-2/sundial/kronos = `CHALLENGER` (`config/model_registry.yaml`) |
| Classification Models | `IMPLEMENTED` | `models/baseline_ml.py` (LR/RF/XGB/LGBM 3-class direction) |
| Regime Engine | `PARTIAL` | `regime/engine.py`, `regime/events.py`, `regime/protection.py` |
| Scenario Engine | `PARTIAL` | `forecast/scenario.py` |
| Historical OOS | `IMPLEMENTED` | `backtest/walk_forward.py`, `forecast/backtest.py`, `research/historical_learning.py` |
| Forward Shadow | `PARTIAL` | `research/forward_shadow.py`, `research/forward.py`; forward evidence = `NONE_YET` |
| Research Gates | `IMPLEMENTED` | `research/registry.py`, `research/schemas.py`, `services/research_truth.py` |
| Price Map | `IMPLEMENTED` (research-only) | `research/price_probability_map.py` `PriceMap` |
| Probability Map | `INTERFACE_ONLY` (research) | `research/price_probability_map.py` `ProbabilityMap` — all public probabilities `NOT_AVAILABLE` |
| Calibration Evidence | `INTERFACE_ONLY` | `CalibrationEvidence` dataclass exists; no fitting performed |
| Analysis Packet | `IMPLEMENTED` | `packet/schema.py`, `packet/builder.py` |
| MCP Public View | `IMPLEMENTED` | `mcp/server.py` (21 tools), `services/public_view.py` |
| Cherry / LLM layer | `INTERFACE_ONLY` | no Cherry prompt modification in this repo's public path |
| Yuanta integration | `INTERFACE_ONLY` (read-only quote gate) | `integrations/yuanta/*.py`, `services/secret_store.py` |
| TradingView integration | `INTERFACE_ONLY` (research display) | `integrations/tradingview_bridge.py` |

## Detailed layer notes

### Data Sources
- All `providers/*` implement **daily-frequency HTTP fetch** (`fetch_daily`, `fetch_stock_day_all`, `fetch_series`, `fetch_price`). No streaming, no websocket, no tick subscription.
- `TaifexProvider.fetch_time_and_sales` exists but is a **daily CSV download** (TAIFEX historical time-and-sales file), not realtime L1.
- Evidence: `providers/twse.py:69 fetch_stock_day_all`, `providers/taifex.py:53 fetch_time_and_sales`, `providers/yfinance_provider.py:55 fetch`.

### Feature Store
- On-disk DuckDB: `data/feature_store/features.duckdb`.
- `features` table columns: `feature_name, symbol, event_time, available_at, feature_version, source, data_grade, value` (547 rows).
- **Only feature present**: `close` for symbol `^N225`, daily, `2025-09-17..2026-06-30`, `data_grade=RESEARCH_PROXY`.
- This means the "as-of" schema scaffold (`event_time` + `available_at`) **exists**, but it is populated with a single proxy close series — the point-in-time join and revision-aware loader are **not implemented**.

### Calendar
- `services/calendar.py` provides `exchange_for_symbol` (TWSE→XTAI, TSE→XTKS), `calendar_name`, `next_ose_derivatives_sessions` (XTKS cash + JPX holiday trading), `sanitize_daily_exchange_sessions`.
- `config/ose_derivatives_calendar.yaml` marks 2026-09-21/22/23 as TSE-cash-closed / OSE-derivatives-open holiday trading. Verified against JPX official schedule + IC Markets schedule + OfficeHolidays.

### Models (see PHASE3_V2_ARCHITECTURE_AUDIT_REPORT.md §12 for full matrix)
- Only daily-frequency, horizon `1d/2d/5d/10d`. No intraday model, no distribution model, no event/barrier model, no state machine.
- VAR(1) direct-micro is the only `STATISTICAL_FORECAST_EVIDENCE` (`PHASE2_RESEARCH_FREEZE.yaml`), and it is `NON_EXECUTABLE_FORECAST_EDGE`.

### Probability / Calibration
- The 3A.2.x contract chain (price map → probability map → distribution evidence → calibration evidence) is fully implemented as a **fail-closed typed schema**, but no distribution/calibration has been fit. Result: **all public probabilities `NOT_AVAILABLE`** (by design). This is a contract, not calibrated probability.

## Gaps that V2 must address
1. No intraday (1m/5m/…) data for any target — see `INTRADAY_DATA_FEASIBILITY.md`.
2. No canonical event/observed/source/ingested timestamp taxonomy — single `timestamp_utc` + feature-store `event_time`/`available_at` only.
3. No point-in-time / as-of join beyond the single-series feature store.
4. No structured market state machine (only `regime` dict + `event_state` string).
5. No touch/break/acceptance label engine.
6. No prediction audit DB (forecast_origin / feature_cutoff / source_snapshot_ids / roll state / model_version / label_version are not persisted together).
