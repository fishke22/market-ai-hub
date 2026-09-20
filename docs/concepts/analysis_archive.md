# Analysis Archive

不可變分析 + append-only 結算（DuckDB，`data/analysis_archive/archive.duckdb`）。

## AnalysisRecord（`automation/archive.py`）
- analysis_id / created_at / information_cutoff
- market / target / instrument / horizon / forecast_target_dates
- reference_price / model_center / research_center / model_range / research_core_range
- direction / research_confidence
- support / resistance / confirmation / invalidation levels
- regime / event_state
- top_positive_drivers / top_negative_drivers
- forecast_ids / model_versions / dataset_version / feature_version
- analysis_packet_hash / human_readable_report_ref

## AnalysisOutcome（append-only）
- actual_close / actual_high / actual_low
- center_absolute_error / direction_hit / core_range_hit / core_range_coverage
- support_broken / resistance_broken / invalidation_triggered
- max_favorable_move / max_adverse_move / settled_at

## 規則
- 重複 `analysis_id` → 拒絕（不可變）
- 每筆分析只能結算一次（append-only）
- `unsettled_ids()` 回傳尚未結算的分析

## Save hook（不改 V1 response）
`automation/analysis_hook.py::archive_analysis(result_dict)` → 回 analysis_id。
LLM 文字不得拿來訓練價格模型。
