# PHASE 2Q-F.7 — Target-Scoped Research Truth Closure + Fresh Official Market Sample Validation

- gate：**PHASE2QF7_TARGET_TRUTH_PASS**（0 Critical / 0 High）
- build_id：`24f3c010c7f66798`
- 版本：`v2.0.0-rc1`（不 tag / release / retag）

## 0. Preflight

`git status` clean；HEAD == origin/main == `c2d2848`。無 dirty / 未提交。

## A1/A2 — Target-scoped research truth（HIGH defect 修復）

**根因**：`packet/builder.py::_fill_research_truth` 用 flat `validation_truth()`（Osaka-scoped）套用到**所有市場** → TAIEX packet 繼承 Osaka 的 VAR(1) / STATISTICAL_FORECAST_EVIDENCE / NON_EXECUTABLE_FORECAST_EDGE。

**修**：
- `_fill_research_truth(packet, family, target)` 改用 target-scoped `evidence_for(family, target)`。
- `evidence_for` 修正：TAIWAN_STOCK 動態代碼 fallback 到 family 預設 entry（不再 UNKNOWN_TARGET）。
- TAIWAN_STOCK / TAIWAN_INDEX evidence 改 canonical enum：`historical_oos=NOT_YET_VALIDATED`、`causal=NOT_ESTABLISHED`、`economic=NOT_ESTABLISHED`、`execution_validation=NOT_ESTABLISHED`（TAIWAN_INDEX）。

## A3 — Golden tests

`tests/test_phase2qf7.py`（9 tests）：Taiwan stock/index evidence 不得含 `VAR(1)`/`OSE`/`Micro`/`225LABO`/`NON_EXECUTABLE_FORECAST_EDGE`；Osaka 保留自身 evidence；packet validation_truth target-scoped。

## A4-A11 — Fresh official sample（engineering runtime validation only）

`scripts/capture_fresh_validation_sample.py`（輸出 local-only `data/validation_samples/YYYY-MM-DD/`；標 `sample_role=ENGINEERING_RUNTIME_VALIDATION_ONLY`、`not_predictive_evidence=true`）。

2026-09-21 比對結果：

| instrument | source | official | runtime | match |
|-----------|--------|----------|---------|-------|
| TAIEX | TWSE MI_INDEX | 47,718.84 | 47,718.84 | **true** |
| 3706.TW | TWSE STOCK_DAY | 79.80 | 79.80 | **true** |
| 2330.TW | TWSE STOCK_DAY | 2,480.00 | 2,480.00 | **true** |

`fresh_sample_match = PASS`。fresh sample **不升級** model evidence（MODEL_PREDICTIVE_GATE 仍 UNPROVEN、TRADING_EDGE_GATE 仍 NO_ECONOMIC_EDGE）。

## A8/A9 — OSE calendar

`config/ose_derivatives_calendar.yaml`（JPX official）：2026-09-21/22/23 OSE derivatives Holiday Trading OPEN；XTKS/TSE cash 同期 closed。JPX settlement file 不刊載 holiday-trading day data → 不得當 Direct Micro holiday-session quote（`direct_micro_forecast_status=NOT_AVAILABLE`）。

## A12 — Health family calendar

TAIWAN_STOCK/TAIWAN_INDEX → XTAI；OSAKA_MICRO_DIRECT → OSE_DERIVATIVES；OSAKA_PROXY → XTKS。

## 觀察（非本棒 defect）

FinMind `TaiwanStockPriceAdj` dataset 對個股回 HTTP 400（external provider issue）；runtime 正確 fallback 到 TWSE official（truth 保持正確）。記錄供後續 provider 修復。

## Validation

- **full default pytest：840 passed, 20 deselected**（831 + 9 new）。
- audit_runtime_evidence PASS；assert_uat_semantics PASS；secret scan 0 真實 secret。

## 禁區未動

不 live trading / broker order / auto order / auto retrain / auto promote / 把研究模型包裝成已驗證交易策略 / force push / retag。
