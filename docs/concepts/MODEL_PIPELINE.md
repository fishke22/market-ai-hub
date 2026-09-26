# Model Pipeline

## 已有 adapter 的模型（不等於每個 runtime / target 均可用）
| Model | Task | 說明 |
|---|---|---|
| Chronos-2 | PRICE_FORECAST | quantile forecaster |
| TimesFM-3.0 | PRICE_FORECAST | 非商業 weights |
| XGBoost | DIRECTION_CLASSIFICATION | baseline ML |
| LightGBM | DIRECTION_CLASSIFICATION | baseline ML |
| NHITS | PRICE_FORECAST | challenger；fit-on-the-fly，依 runtime 依賴與資料 eligibility 決定 |
| NBEATSx | PRICE_FORECAST | challenger；fit-on-the-fly，依 runtime 依賴與資料 eligibility 決定 |

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
- TrainingEligibilityPolicy 提供 weekly/drift/degradation/manual 與樣本條件；存在 policy 不代表 AUTO_TRAIN 已啟用。保留現有關閉狀態，不因文件改寫自動訓練。

登錄/adapter、依賴可載入、權重存在、一次 smoke inference、通過真實 OOS 是不同狀態；以實際 model_status 與目標資料證據回答。舊 BLOCKED_RUNTIME 報告保留日期，不可直接當永久現況。
