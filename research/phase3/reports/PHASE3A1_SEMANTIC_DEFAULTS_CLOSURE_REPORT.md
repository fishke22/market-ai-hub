# PHASE 3A.1 — Target Profile Isolation + Unknown/Unevaluated Semantics + Fail-Closed Price Map Defaults

- gate：**PHASE3A1_SEMANTIC_DEFAULTS_PASS**（0 Critical / 0 High）
- build_id：`8488def718b8672c`
- 版本：`v2.0.0-rc1`（不 tag / release / retag）

## 8 問答（§24）

1. **TAIWAN_INDEX 原先是否錯拿 OSAKA_MICRO_PROFILE？** **是**。`profile_for` 邏輯為 `if TAIWAN_STOCK else OSAKA_MICRO`，故 TAIWAN_INDEX / UNKNOWN / future family 全部 fallback 到 Osaka。
2. **原因是什麼？** 二分法 fallback（`if TAIWAN_STOCK ... else OSAKA`），無 explicit family 映射。
3. **unknown family 現在如何處理？** `profile_for` 明確映射三 family；未知 → `raise ValueError`（fail closed，不 fallback）。
4. **沒有 state detector evidence 現在輸出什麼？** `market_state = null`、`market_state_status = NOT_EVALUATED`（不再 NEUTRAL_ZONE）。
5. **沒有 regime evidence 現在輸出什麼？** `regime = null`、`regime_status = NOT_EVALUATED`（不再 RANGE_LOW_VOL）；`strategy_candidate = NONE`。
6. **沒有 model-failure evaluation 現在輸出什麼？** `model_failure_state = null`、`model_failure_evaluation_status = NOT_EVALUATED`（不再 NORMAL）。
7. **sample_size=0 是否還會叫 EMPIRICAL distribution？** **NO**（`method = NOT_ESTABLISHED`）。
8. **是否仍存在跨 target-family fallback？** **NO**。

## 修正

| 項 | 修正 |
|----|------|
| profiles | 新增 `TAIWAN_INDEX_PROFILE`（forecast=TAIEX、execution=TX/MTX/TMF、cash_index_executable=false、execution_validation=NOT_ESTABLISHED）；`profile_for` explicit 映射 + unknown raise |
| market_state | `str \| None = None` + `market_state_status=NOT_EVALUATED` |
| regime | `str \| None = None` + `regime_status=NOT_EVALUATED` |
| model_failure | `model_failure_state=None` + `model_failure_evaluation_status=NOT_EVALUATED` |
| distribution method | `NOT_ESTABLISHED`（sample_size=0 不叫 EMPIRICAL） |
| calibration | 無 distribution → `INSUFFICIENT_EVIDENCE`（區分 UNCALIBRATED） |
| strategy candidate | regime 未評估 → `NONE` |
| `empty_price_map()` | 新增 canonical fail-closed helper |
| `six_state_research_view` | omitted → NOT_EVALUATED；explicit → enum 驗證 + EVALUATED |

## 新增測試

`tests/test_phase3a1.py`（15 tests）：profile isolation / unknown fail-closed / no fake NEUTRAL·RANGE·NORMAL·EMPIRICAL / calibration semantics / empty_price_map / strategy candidate absent / invariants preserved。

## Gate 對照（§25）

TAIWAN_INDEX profile independent ✓；UNKNOWN family fail closed ✓；no fake NEUTRAL ✓；no fake RANGE ✓；no fake NORMAL ✓；no fake EMPIRICAL ✓；strategy candidate absent when regime unevaluated ✓；Phase3A invariants preserved ✓；full pytest PASS ✓；0 Critical / 0 High ✓。

## Validation

- **full default pytest：870 passed, 20 deselected**（855 + 15 new）。
- working tree clean after tests；runtime data no pollution。
- Fresh sample truth 保持（TAIEX 47718.84 / 3706 79.80 / 2330 2480.00），未改成 model evidence。

## 禁區未動

不 probability estimation / calibration fitting / strategy optimization / model training / hyperparameter search / live trading / broker execution。
