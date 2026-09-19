# 系統架構（ARCHITECTURE）

## 資料流

```
資料來源 (TWSE / FinMind / FRED / yfinance)
        ↓
Data layer（清理、時區對齊、trading calendar、feature 計算）
        ↓
Base Models（chronos-2、timesfm-3.0、xgboost、lightgbm）
        ↓
Ensemble（price_ensemble + direction_ensemble）
        ↓
Analysis Wrapper（analyze_osaka_nikkei / analyze_taiwan_stock）
        ↓
MCP Server（stdio，13 tools）
        ↓
Cherry Studio（LLM 產生自然語言分析）
```

## 三層角色（不可混淆）

| 層 | 角色 | 說明 |
|----|------|------|
| Level A | **BASE_MODEL** | 獨立模型：chronos-2、timesfm-3.0、xgboost、lightgbm（+ 可選 fincast） |
| Level B | **ENSEMBLE** | 整合層，**不是**第 5 個獨立模型 |
| Level C | **ANALYSIS_WRAPPER** | 分析封裝，**不是**第 6 個獨立模型 |

- `predict_ensemble` = 4 個 base model + 1 個 ensemble。
- `analyze_*` = wrapper，內部呼叫 base models 與 ensemble。
- 獨立證據計票只算 base models：`independent_base_model_count` / `eligible_direction_vote_count` /
  `eligible_price_reference_count`。

## PRICE_FORECAST vs DIRECTION_CLASSIFICATION

| 任務 | 模型 | 輸出 |
|------|------|------|
| **PRICE_FORECAST** | chronos-2、timesfm-3.0（fincast） | `forecast_path`、`point_forecast`、真 quantile（p10/p50/p90）、MAE/RMSE/MASE（驗證後） |
| **DIRECTION_CLASSIFICATION** | xgboost、lightgbm | Up/Flat/Down、class probabilities（未校準）、accuracy/balanced_accuracy/macro_f1/mcc/baselines |

分類器**不得**偽裝成價格分佈模型：其 `quantile_type = NOT_AVAILABLE`，
heuristic spread 以 `lower_reference` / `upper_reference` 表示，不叫 p10/p90。

## Ensemble 語義

- `price_ensemble`：只聚合 PRICE_FORECAST 的真 quantile / path。
- `direction_ensemble`：只聚合 DIRECTION_CLASSIFICATION 的方向與 class probabilities。
- 權重方法：`EQUAL_WEIGHT_RESEARCH`（`experimental=true`）。
- `validation_level=RESEARCH`（尚無 VALIDATED 模型）。
- `component_table`：每個 component 的 role / status / eligible / raw_weight / effective_weight /
  excluded_reason。
- 舊欄位（頂層 `direction` 等）標 `legacy_research_only=true`。

## V1 關鍵 correctness rules

1. **Horizon**：`data_frequency="1d"` 時 `Nd` = N 根 trading bars。
   日線資料 + 日內 horizon（5m/15m/30m/60m）→ `UNSUPPORTED_WITH_CURRENT_DATA`。
2. **Calendar**：TWSE=XTAI、TSE=XTKS（exchange_calendars）。forecast target 全為**未來 sessions**。
3. **Timezone**：`trading_date` 由交易所時區推導（Asia/Taipei、Asia/Tokyo），禁用 UTC date。
4. **Quantile Contract**：`p10 <= p50 <= p90`，否則標 NOT_AVAILABLE 且不進 ensemble。
5. **Calibration**：分類器 probability 未校準（`probability_calibrated=false`），
   不得把 0.84 解讀為「84% 上漲機率」。
6. **Session / Freshness 分離**：
   - `market_open` / `tradable_now` / `session_status`（OPEN/CLOSED/…）只由交易制度決定。
   - `freshness_status`（LIVE/RECENT/STALE/HISTORICAL/UNKNOWN）、`quote_live`、
     `usable_for_live_decision` 只由資料新鮮度決定。
   - stale **不會**把 market_open 改成 false。
7. **Reproducibility**：`input_data_hash` + `forecast_config_hash` + `inference_seed` +
   `model_revision` + `model_build_id`。Chronos/TimesFM 為 `deterministic_mode=true`（10x 一致）。

## 儲存

- DuckDB（`data/`）+ Parquet（`data/raw/`，append-only，含 provenance + checksum）。
- raw 不覆寫；processed 可重建。**這些資料不進 repository。**

## 目錄結構

```
src/market_ai_hub/
  config/      設定載入
  data/        時間工具
  providers/   TWSE / FinMind / FRED / yfinance / (disabled adapters)
  features/    feature 計算（含 sanitation）
  models/      chronos / timesfm / baseline_ml / fincast
  ensemble/    ensemble 邏輯
  backtest/    walk-forward
  storage/     duckdb / performance
  services/    horizon / calendar / market_session / reproducibility / validation / model_catalog / build_info / analysis
  schemas/     pydantic schema
  mcp/         MCP server
```
