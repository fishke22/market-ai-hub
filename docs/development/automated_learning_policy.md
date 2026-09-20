# 受控自動學習政策

## 可自動重訓模型
`xgboost` / `lightgbm` / `nhits` / `nbeatsx`（`TrainingEligibilityPolicy.RETRAINABLE_MODELS`）。
其他模型（含尚未建 adapter 的 Kronos-TW / Sundial / Moirai / TTM）預設不自動重訓。

## 觸發條件（至少符合其一）
1. scheduled weekly retrain **且** new labeled observations ≥ min_new_samples（預設 5）
2. River drift warning **且** new samples 滿足
3. performance degradation **且** new samples 滿足
4. manual research request

不得「每預測錯一次就重訓」。

## Champion 安全
- `AUTO_PROMOTE_TO_CHAMPION = False`（永不自動換 champion）
- Champion 更新需 **human approval**
- 全自動化只到：AUTO_TRAIN / AUTO_EVALUATE / AUTO_RANK / AUTO_RECOMMEND_PROMOTION

## Optuna（bounded）
- `BoundedOptuna(max_trials=20, max_runtime_seconds=300, gpu_budget_mb=4000)`
- 只搜 train/validation（nested walk-forward）；**Final Test 不得作調參資料**

## River（shadow only）
- `DriftMonitor`（PSI）→ `DRIFT_WARNING` / `NORMAL`
- 僅產生 drift 警告 + retrain 建議；**不 AUTO_PROMOTE**

## 防 self-reinforcement
LLM 文字不得拿來訓練價格模型。
