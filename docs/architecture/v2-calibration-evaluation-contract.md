# V2 calibration / evaluation contract (2I.1)

Schema: `V2_CALIBRATION_EVALUATION_SCHEMA_VERSION = "2I.1"`
Module: `src/market_ai_hub/research/v2/calibration_evaluation.py`
Tests: `tests/test_v2i_calibration_evaluation.py`

## 0. 一句話

2I.1 是 **evaluation engine**，不是 calibration fitting。它證明「引擎能正確評估」，
**不**證明任何模型已校準。

```text
ENGINE PASS != CALIBRATED
EVALUATED  != CALIBRATED
SYNTHETIC METRICS != MARKET EVIDENCE
```

## 1. 唯一輸入來源

只讀 V2-H 2H.2 audit DB 的 `PredictionRecord` / `ForecastArtifactRecord` / `OutcomeRecord`
（`PredictionAuditDB`，append-only，LOCAL_ONLY）。**禁止**從 CSV、外部檔案或任何其他來源補值。
DB 不存在時 readiness 檢查**不得建立** DB（read-only、回 `db_present=False`）。

## 2. EvaluationDatasetManifest（content-addressed）

`build_evaluation_dataset(...)` 產生 manifest，至少綁定：

```text
members[]            prediction_id / forecast_artifact_id / outcome_id（全數保存，日後可證明 sample set）
target_family        instrument            horizon
model                model_version
artifact_type        calibration_domain    probability_type     event_definition_id
window_start/end     partition_role        schema_version
label_types[]        rejected[]（含理由）
dataset_id = "v2i_ds_" + sha256(canonical(members + 上述欄位))
```

- member 排序固定 → **輸入順序不影響 `dataset_id`**。
- member set 或任一欄位改變 → `dataset_id` 改變。
- `partition_role ∈ {CALIBRATION, VALIDATION, FINAL_OOS, FORWARD}`。2I.1 可評估任何合法
  partition，但**不做 fit**，因此不得用 `FINAL_OOS` 調參。

## 3. Pairing（只接受 forecast artifact ↔ 其綁定 outcome）

拒絕碼（15）：

```text
BLOCKING（資料集本身不合法 -> 整個評估 BLOCKED）
  CROSS_PREDICTION  WRONG_PROBABILITY_TYPE  WRONG_EVENT_DEFINITION
  WRONG_TARGET  WRONG_HORIZON  WRONG_MODEL  WRONG_CALIBRATION_DOMAIN
  AMBIGUOUS_OUTCOME  LEAKAGE_FUTURE  OUTSIDE_WINDOW  NOT_PROBABILITY

NON-BLOCKING（資料稀疏 -> 該樣本排除，其餘照算）
  MISSING_OUTCOME  NON_BINARY_OUTCOME  NOT_BOUND  EMPTY_VALUE
```

- `MISSING_OUTCOME` = 沒有 outcome 或 outcome 未結算 → 樣本被排除（**不是** phase failure）。
- `LEAKAGE_FUTURE`（`outcome.available_at < prediction.forecast_origin`）有兩層防線：
  2H.2 寫入邊界 `OutcomeTemporalError` 先拒收；2I.1 評估時再檢查一次（defence in depth）。
- 一個 artifact 綁多個 outcome → `AMBIGUOUS_OUTCOME`（fail-closed）。

## 4. 機率評估（只限 EVENT_PROBABILITY）

前置條件全部成立才計算：

```text
artifact_type = EVENT_PROBABILITY
value ∈ [0, 1]
outcome_kind 與 probability_type 家族一致（fail-closed，未知家族即拒）
actual_value ∈ {0, 1}（binary）
```

指標：

```text
Brier score、log loss、base rate、mean predicted probability、
reliability bins、ECE、MCE、sample_count
```

- log loss 以 `LOG_LOSS_EPSILON = 1e-15` clipping，且 `epsilon` 保存在
  `ProbabilityMetrics.log_loss_epsilon`（不得隱藏）。
- **`CLASS_SCORE` 永不當機率**：不能進 Brier / log loss；宣告為 `CLASS_SCORE` 的資料集
  評估結果為 typed `NOT_EVALUATABLE`。
- `NOT_AVAILABLE` artifact 不帶值，永不成為機率。
- 少於 `MIN_PROBABILITY_SAMPLES = 2` → `INSUFFICIENT_SAMPLE`（1 筆無法呈現 calibration）。

### 家族分離（永不合併）

```text
TERMINAL != TOUCH（FIRST_PASSAGE 屬 TOUCH 家族）!= BREAK != ACCEPTANCE != DIRECTION
1d != 5d     Osaka != Taiwan
```

由 manifest 欄位承載，跨家族即 `WRONG_PROBABILITY_TYPE`。

## 5. Reliability bins（deterministic）

```text
10 個等寬 bins：[0,.1) [.1,.2) ... [.9,1]
邊界規則：下界含、上界不含；最後一 bin 上界含（p = 1 落最後一 bin）
空 bin：保留（count = 0，mean_predicted/empirical_rate/gap 為 None）——contract 固定此選擇
ECE = Σ (n_b / N) * gap_b        MCE = max gap_b（僅非空 bin）
```

## 6. 其他 artifact 評估（皆非 calibration evidence）

| artifact_type | 需要的 settled outcome | 指標 |
|---|---|---|
| `POINT` | numeric | MAE、RMSE |
| `QUANTILE` | numeric | pinball loss（同一 manifest 只允許單一 `quantile_level`，混合 → `BLOCKED`） |
| `INTERVAL` | numeric | empirical coverage、mean width、coverage error vs nominal（單一 `nominal_coverage`） |
| `STATE` / `NOT_AVAILABLE` | — | typed `NOT_EVALUATABLE` |
| `CLASS_SCORE` | — | typed `NOT_EVALUATABLE`（永不機率） |

## 7. Evaluation status

```text
EVALUATED          指標已算出（描述性，非認證）
INSUFFICIENT_SAMPLE 樣本數不足
NOT_EVALUATABLE    型別本身不可評估（STATE / CLASS_SCORE / NOT_AVAILABLE / 無已結算樣本）
BLOCKED            資料集不合法（pairing / 洩漏 / 混合 quantile 等）
```

**不建立任何「好/壞」threshold**（沒有 pre-registered acceptance gate）。

## 8. CalibrationEvidence adapter

`evaluation_result_to_calibration_evidence(result)` 只可能產生：

```text
INSUFFICIENT_EVIDENCE      (status != EVALUATED)
EVALUATED_UNCALIBRATED     (status == EVALUATED)
```

**永不產生 `CALIBRATED`**，因為：

```text
2I.1 does not fit a calibration model
no pre-registered acceptance threshold
actual settled probabilistic sample = NONE_YET
```

`EVIDENCE_STATUSES` 只有兩個成員；adapter 內建 assert 擋住任何第三種輸出。

## 9. Readiness（正式回報）

檢查 default DB（`data/audit/prediction_audit.duckdb`）：

```text
無真實 settled EVENT_PROBABILITY samples：
  ACTUAL_PROBABILITY_EVALUATION = INSUFFICIENT_EVIDENCE
  ACTUAL_CALIBRATION_EVIDENCE   = NONE_YET
```

這是正常 PASS。Synthetic tests 只證明 engine。

## 10. 未做（2I.1 邊界）

NO calibration fitting · NO model training · NO threshold 調參 · NO probability 對外發布 ·
NO 資料下載 · NO order / trading · NO position / account query · NO recorder。
