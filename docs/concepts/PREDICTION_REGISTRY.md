# Prediction Registry（預測註冊表）

Phase 2A 的**不可變預測註冊表**：每次預測建立後永久保存，事後不得修改，只能 append outcome。

## 核心原則

1. **Forecast 不可變**：`register()` 之後，同一個 `forecast_id` 再註冊會被拒絕（不會 overwrite）。
2. **Outcome append-only**：結算只新增 `outcomes`，不回頭改 forecast；同一 forecast 重複 settle 會被拒絕。
3. **No look-ahead**：每個 forecast 帶 `information_cutoff`；任何資料 `available_at > information_cutoff`
   不得進模型（`assert_no_lookahead` 會在洩漏時拋 `LookAheadError`）。

## Forecast 欄位（PredictionRecord）

| 分類 | 欄位 |
|------|------|
| identity | `forecast_id`、`created_at`、`information_cutoff` |
| target | `market`、`target`、`instrument`、`contract` |
| horizon | `horizon`、`forecast_origin`、`forecast_target_dates`、`exchange_calendar` |
| model | `model_name`、`model_task`、`model_revision`、`model_build_id`、`training_cutoff` |
| reproducibility | `input_data_hash`、`dataset_version`、`feature_version`、`forecast_config_hash`、`inference_seed`、`sampling_config`、`deterministic_mode` |
| forecast value | `point_forecast`、`p10`、`p50`、`p90`、`origin_price` |
| direction | `direction`、`raw_class_scores`、`probability_calibrated` |
| status | `engineering_status`、`predictive_validation_status` |
| context | `regime_as_known_at_prediction_time`、`data_quality_state`、`raw_output_reference` |

## Outcome 欄位（OutcomeRecord，append-only）

`actual`、`actual_timestamp`、`absolute_error`、`squared_error`、`scaled_error`、
`direction_result`、`interval_hit`、`pinball_loss`、`settled_at`。

## 儲存（DuckDB + Parquet）

- **DuckDB**（`data/registry/registry.duckdb`）：metadata / registry
  - `schema_meta`（記錄 `schema_version`，目前 = 1）
  - `predictions`（不可變）
  - `outcomes`（append-only）
- **Parquet**（`data/registry/*.parquet`）：bulk forecast / outcome 快照，檔名含 schema version。
- 遷移為 **non-destructive**（只 `CREATE IF NOT EXISTS`，不 DROP 既有資料）。

## 使用

```python
from market_ai_hub.research.registry import PredictionRegistry
from market_ai_hub.research.schemas import PredictionRecord, OutcomeRecord

reg = PredictionRegistry()
reg.register(PredictionRecord(forecast_id="...", ...))   # 不可變
reg.settle(OutcomeRecord(forecast_id="...", actual=..., ...))  # append-only
reg.list_predictions(settled=False)   # 查 open forecasts
reg.leaderboard()                     # 已結算預測的聚合指標
reg.export_parquet()                  # 落 Parquet
```

## CLI（Forward Test）

見 `docs/concepts/FORWARD_TEST.md`。對應 `python -m market_ai_hub.research.forward {run,settle,status,leaderboard}`。

## 注意

- 本模組為 Phase 2A 新增，**不改動 V1 核心**（build_id 維持 `bbf3cb2f9a80d20e`）。
- `data/registry/` 與 `mlflow.db` 皆在 `.gitignore` 排除（研究產物，不入 repository）。
