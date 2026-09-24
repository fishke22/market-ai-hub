# PHASE V2-I 2I.1 — Calibration Evaluation Foundation (report)

Schema: `V2_CALIBRATION_EVALUATION_SCHEMA_VERSION = "2I.1"`
Contract: `docs/architecture/v2-calibration-evaluation-contract.md`
Module: `src/market_ai_hub/research/v2/calibration_evaluation.py`
Tests: `tests/test_v2i_calibration_evaluation.py` (41)

## 0. Claim boundary

```text
ENGINE PASS != CALIBRATED
EVALUATED  != CALIBRATED
SYNTHETIC METRICS != MARKET EVIDENCE
```

本棒做 **evaluation engine**，**NOT calibration fitting**。無 pre-registered acceptance threshold，
且 audit DB 目前沒有真實 settled probabilistic samples → `CALIBRATED` 不可產生。

## 1. 交付物

```text
src/market_ai_hub/research/v2/calibration_evaluation.py     (新)
tests/test_v2i_calibration_evaluation.py                     (新，41 tests)
docs/architecture/v2-calibration-evaluation-contract.md      (新)
src/market_ai_hub/research/v2/prediction_audit.py            (v2_schema_versions 增 calibration_evaluation)
```

## 2. Input / manifest

只讀 V2-H 2H.2 `PredictionAuditDB`（append-only LOCAL_ONLY）；**禁止** CSV 或外部補值。
`build_evaluation_dataset()` 產生 content-addressed `EvaluationDatasetManifest`：

- `members[]`：`prediction_id` / `forecast_artifact_id` / `outcome_id` 全數保存（日後可證明 sample set）
- 綁定 `target_family / instrument / horizon / model / model_version / artifact_type /
  calibration_domain / probability_type / event_definition_id / window_start / window_end /
  partition_role / schema_version`
- `dataset_id = "v2i_ds_" + sha256(canonical(payload))`；member 排序固定 → 輸入順序不影響；
  member set 改變 → id 改變（皆有 test）。

`partition_role ∈ {CALIBRATION, VALIDATION, FINAL_OOS, FORWARD}`；2I.1 可評估任何合法 partition，
但**不做 fit**，故不得用 `FINAL_OOS` 調參。

## 3. Pairing（實測結果）

只接受 `forecast artifact ↔ 其 bound outcome`。15 個拒絕碼，分兩類：

| 類別 | 碼 | 效果 |
|---|---|---|
| BLOCKING | `CROSS_PREDICTION` `WRONG_PROBABILITY_TYPE` `WRONG_EVENT_DEFINITION` `WRONG_TARGET` `WRONG_HORIZON` `WRONG_MODEL` `WRONG_CALIBRATION_DOMAIN` `AMBIGUOUS_OUTCOME` `LEAKAGE_FUTURE` `OUTSIDE_WINDOW` `NOT_PROBABILITY` | 整個評估 `BLOCKED`（fail-closed） |
| NON-BLOCKING | `MISSING_OUTCOME` `NON_BINARY_OUTCOME` `NOT_BOUND` `EMPTY_VALUE` | 該樣本排除，其餘照算（資料稀疏，非 phase failure） |

- `MISSING_OUTCOME` 實測：2 個預測中 1 個無 outcome → 1 rejected、`sample_count=1` → `INSUFFICIENT_SAMPLE`。
- 洩漏兩層防線（皆有 test）：2H.2 寫入邊界 `OutcomeTemporalError` 先拒收；
  即使繞過寫入邊界把違規 outcome 塞進 DB，2I.1 仍以 `LEAKAGE_FUTURE` 拒收 → `BLOCKED`。

## 4. 機率評估（只限 EVENT_PROBABILITY）

實測指標（toy 精確值）：

```text
Brier score      [(0.1,0),(0.9,1)] -> 0.01
log loss         [(0.5,1),(0.5,0)] -> ln 2 = 0.6931471805599453
base rate        0.5
mean predicted   0.1
ECE / MCE        兩筆 p=0.1（bin [0.1,0.2)）-> 0.4 / 0.4
sample_count     2
log_loss_epsilon 1e-15（保存在 ProbabilityMetrics，無隱藏常數）
p=0/p=1          Brier 0.0、log loss 有限且 >= 0；epsilon=0 直接 raise
```

- **`CLASS_SCORE` 永不當機率**：機率資料集拒絕配對（`WRONG_PROBABILITY_TYPE`）；
  即使宣告為 `CLASS_SCORE` 資料集，評估結果為 typed `NOT_EVALUATABLE`（reason
  "CLASS_SCORE is never treated as a probability"），`probability is None`。
- `EVENT_PROBABILITY` value 1.5 → `NOT_PROBABILITY` → `BLOCKED`。
- `NOT_AVAILABLE` artifact 不帶值 → 永不成為機率（members 為空、`probability is None`）。
- 家族分離：`probability_type=TERMINAL` 配 `outcome_kind=TOUCH` → `BLOCKED`；
  未知 `probability_type` → fail-closed `BLOCKED`。
- `MIN_PROBABILITY_SAMPLES = 2`（單筆無法呈現 calibration）→ `INSUFFICIENT_SAMPLE`。

Reliability bins：10 個等寬 `[0,.1) ... [.9,1]`；下界含上界不含、最後一 bin 含 1；
空 bin **保留**（contract 固定此選擇）；ECE = Σ(n_b/N)·gap_b、MCE = max gap_b。

## 5. 其他 artifact 評估（非 calibration evidence）

| 類型 | 實測 toy | 結果 |
|---|---|---|
| `POINT` | value 100，actual 102 / 98 | MAE 2.0、RMSE 2.0 |
| `QUANTILE` | τ=0.5, value 100，actual 102 / 98 | pinball 1.0 / 1.0 → mean 1.0 |
| `INTERVAL` | [99,101] nominal 0.9，actual 100 / 105 | empirical 0.5、mean width 2.0、coverage error −0.4 |
| 混合 `quantile_level` | 0.5 + 0.9 | `BLOCKED` `MIXED_OR_MISSING_QUANTILE_LEVEL` |
| `STATE` / `NOT_AVAILABLE` / `CLASS_SCORE` | — | typed `NOT_EVALUATABLE` |

## 6. Evaluation status / adapter

```text
EVALUATED | INSUFFICIENT_SAMPLE | NOT_EVALUATABLE | BLOCKED
```

無任何「好/壞」threshold。`evaluation_result_to_calibration_evidence()` 只產生：

```text
INSUFFICIENT_EVIDENCE   (status != EVALUATED)
EVALUATED_UNCALIBRATED  (status == EVALUATED)
```

`EVIDENCE_STATUSES` 只有這兩個；adapter 內建 assert，任何第三種（含 `CALIBRATED`）輸出直接 raise。
`fitted_model=False`、`pre_registered_threshold=False` 明確寫入輸出。

## 7. Actual readiness（正式回報）

`evaluate_default_db()` 對 `data/audit/prediction_audit.duckdb` 做**唯讀**檢查（DB 不存在時不建立檔案）：

```text
db_present                      = False
prediction_count                = 0
settled_event_probability_samples = 0
ACTUAL_PROBABILITY_EVALUATION   = INSUFFICIENT_EVIDENCE
ACTUAL_CALIBRATION_EVIDENCE     = NONE_YET
```

**這是正常 PASS，不是 phase failure。** Synthetic tests 只證明 engine。

## 8. Tests

`tests/test_v2i_calibration_evaluation.py` — **41 passed**，涵蓋：

```text
Brier exact toy / log loss exact toy / p=0,p=1 數值穩定 + epsilon 保存
reliability bin 邊界（p=0 / p=1）/ ECE-MCE deterministic / 空 bin 保留
CLASS_SCORE 不得進機率指標 / EVENT_PROBABILITY >1、<0 blocked / NOT_AVAILABLE 不得成機率
TERMINAL vs TOUCH mismatch blocked / 未知 probability_type fail-closed
cross-target / cross-horizon / cross-model / cross-prediction blocked
member 永不跨預測 / missing outcome 非致命 / leakage 兩層防線
POINT MAE-RMSE / QUANTILE pinball / 混合 quantile blocked / INTERVAL coverage-width
manifest 輸入順序 deterministic / member set 改變 -> id 改變 / partition FINAL_OOS 可評估
adapter 永不 CALIBRATED / 非 EVALUATED 一律 INSUFFICIENT_EVIDENCE
readiness 不建立 DB / 空 DB -> NONE_YET / 2 筆真實樣本 -> EVALUATED + NONE_YET
```

## 9. Safety

NO calibration fitting · NO model training · NO threshold 調參 · NO probability 對外發布 ·
NO 資料下載 · NO order / trading · NO position / account query · NO recorder · NO auto retry。

## 10. Gate

```text
PHASEV2I_CALIBRATION_EVALUATION_FOUNDATION_PASS
```

STOPPED AFTER V2-I 2I.1 EVALUATION FOUNDATION. CALIBRATION FITTING NOT STARTED.
