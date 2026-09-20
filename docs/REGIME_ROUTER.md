# Regime Router（Regime-aware 模型路由）

`forecast/regime_router.py`。

## 輸入
target / horizon / current regime / model performance store。

## 輸出
- eligible_models
- model_weights
- fallback_model
- evidence_state

不能只選歷史最高分模型；需考量 sample_size / confidence / global shrinkage。

## Regime 樣本安全（沿用 Phase 2C）
- `minimum_sample_size`（預設 30）
- `confidence_interval`
- `shrinkage_to_global`

例如：某模型在 `VOL_HIGH` 只有 4 observations，即使 4 次全對，不得給 100% 權重，
標 `REGIME_EVIDENCE_INSUFFICIENT`，並回退 global performance。

## 權重公式
沿用 `forecast/weights.py::compute_weights`（inverse normalized loss +
calibration penalty + reliability penalty + sample shrinkage）。
