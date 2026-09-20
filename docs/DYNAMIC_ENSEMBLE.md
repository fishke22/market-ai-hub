# Dynamic Ensemble（動態集成）

`forecast/dynamic_ensemble.py`、`forecast/weights.py`。

## 權重（只能程式計算，不得由 LLM 決定）
`weight_method_version = v1`：
```
w_raw(model) = inv_loss * calibration_factor * reliability_factor * sample_shrinkage
inv_loss           = 1 / (loss + eps)
calibration_factor = 1 - min(calibration_error, 1)
reliability_factor = 1 - failure_rate
sample_shrinkage   = n / (n + shrinkage_k)
最後 normalize 使和 = 1。
```
全部 documented / deterministic / versioned。

## Best Baseline 安全（沿用 Phase 2D）
- Dynamic Ensemble 必須包含 `BEST_BASELINE` 為合法候選。
- AI 打不贏 Best Baseline → 允許 ensemble 主要用 baseline，甚至 `BASELINE_DOMINANT`。
- 不得為了叫「AI Ensemble」就排除簡單模型。

## Model 失敗處理
timeout / OOM / missing dependency / invalid quantile / data mismatch → 從本次 eligible set 移除，
記錄 `MODEL_SKIPPED_RUNTIME` + 原因，**不得整次分析失敗**。

## Ensemble quantile 語義（非常重要）
- 不得直接平均各模型 P10/P50/P90 當 predictive quantile。
- 只做 component quantile 算術平均 → 標 `ENSEMBLE_RESEARCH_QUANTILE_SUMMARY` + `UNVALIDATED`。
- 只有 `sample-level mixture`（`mixture_quantiles`）或 validated ensemble distribution
  才回 ensemble predictive quantiles。
- 新增欄位：`ensemble_distribution_validated` / `ensemble_quantile_method` /
  `interval_calibration_status`。

## Auto routing 限制
- `AUTO_SELECT_FOR_RESEARCH = true`
- `AUTO_TRADE = false`
- `AUTO_PROMOTE_CHAMPION = false`
- Dynamic Router 只影響研究分析用的模型組合，不得影響任何 broker action。
