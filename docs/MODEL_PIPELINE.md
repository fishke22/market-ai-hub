# Model Pipeline

## 啟用模型（Phase 2 實際使用）
| Model | Task | 說明 |
|---|---|---|
| Chronos-2 | PRICE_FORECAST | quantile forecaster |
| TimesFM-3.0 | PRICE_FORECAST | 非商業 weights |
| XGBoost | DIRECTION_CLASSIFICATION | baseline ML |
| LightGBM | DIRECTION_CLASSIFICATION | baseline ML |
| NHITS | PRICE_FORECAST | neuralforecast fit-on-the-fly |
| NBEATSx | PRICE_FORECAST | neuralforecast fit-on-the-fly |

## 已登錄但未啟用
| Model | 原因 |
|---|---|
| Moirai-2 | CC-BY-NC，uni2ts 缺，未建 adapter |
| TTM | torch 2.11 衝突（DEFERRED） |
| Kronos-TW / Sundial | adapter 未建 |
| FinCast | optional，需隔離 venv |

## PRICE_FORECAST vs DIRECTION_CLASSIFICATION
- price ensemble（chronos/timesfm）：真 quantile。
- direction ensemble（xgb/lgbm）：分類（up/flat/down）。

## Direct / Joint / Scenario / Dynamic Ensemble 不是同一層
- DIRECT：單標的直接預測（分開計分）。
- JOINT：cross-asset 聯合分佈（var/factor/kalman baseline）。
- SCENARIO：rule 產生情境路徑（UNVALIDATED_WEIGHT）。
- DYNAMIC_ENSEMBLE：程式計算權重組合（未 forward-validated → UNVALIDATED_FORWARD）。

## 模型學習時機
- 模型**不會**因為 MCP 被呼叫就開始學習。
- 重訓由背景 loop 依 `TrainingEligibilityPolicy` 觸發（weekly/drift/degradation/manual + min samples）。
