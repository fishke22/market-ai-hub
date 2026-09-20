# Historical Learning Protocol

**Phase 2Q-C §8–§15** — 三市場共用的歷史學習規範。

## 原則

- 允許且鼓勵使用**合法**歷史資料訓練模型。
- Training / Validation / Final OOS 必須**時間隔離**；嚴禁 training 看到 OOS future。
- 禁止 random shuffle train/test 作為金融時間序列驗證。

## 三資料區（§10）

| 區 | 用途 |
|----|------|
| TRAIN | 可學習（fit） |
| VALIDATION | 可調參 / early stopping / calibration |
| FINAL_OOS_HOLDOUT | 模型與調參流程不得預先使用 |

## Walk-Forward（§11）

- 統一 `HistoricalWalkForwardProtocol`（`research/historical_learning.py`）。
- expanding window 與 rolling window 皆支援。
- 每 origin：fit only past → predict future → store immutable result → score after actual。
- 不得 leakage（`assert_origins_no_leakage`）。

## Nested Tuning（§12）

- Optuna / feature selection / model selection 若使用 OOS 資訊 = leakage。
- 所有 tuning 只在 TRAIN + inner validation；Final OOS 不得反覆挑參數。

## Pre-Register（§13）

- 每個正式 exam 在看結果前固定：target / dataset semantic / date range / horizons /
  baselines / metrics / models / cost assumptions / regime / success criteria。
- 產生 immutable protocol hash（`ProtocolSpec.protocol_hash()`）。

## Baselines（§14）

所有 forecast model 必須與簡單 baseline 比：LAST_VALUE / ZERO_RETURN / SEASONAL_NAIVE / DRIFT。不得只 AI vs AI。

## Metrics（§15）

- PRICE：MAE / RMSE / MASE / sMAPE / bias / median AE
- DIRECTION：accuracy / balanced accuracy / F1 / MCC
- QUANTILE：只有真 predictive quantile 才算 coverage / pinball / calibration
- **MASE 不得當勝率**；MASE≈1 = baseline-level。

## Model Promotion（§22/§23）

- Historical OOS PASS 最多標 CHAMPION_CANDIDATE；不得 auto production promotion。
- 仍需 causal / economic / forward / risk。
- 建立 historical training ≠ AUTO_TRAIN=true（保持 false）。

## Final OOS Discipline（§24/§25）

- Final OOS 被反覆查看 → `OOS_CONTAMINATED`，不得稱 untouched holdout；移到新 future holdout 或 Forward Shadow。
- unbiased exam 後可為 deployment research refit（train+validation 截至 current cutoff），
  但原 Final OOS evidence 只保留為 frozen historical exam；refit 後不得聲稱有新的 untouched OOS。

## Corporate Action（§17）

台股歷史學習必須處理 dividend / split / capital reduction，避免機械價格跳動被誤學成 market selloff / rally。
