# Automated Learning（受控自動學習）

## 每次分析
- 保存 forecast（Prediction Registry）+ 分析（Analysis Archive，只存 structured，不存 CoT）。

## 每日背景（`automation/loop.py`）
1. 補資料（只補 missing range）
2. settle outcomes（預測/分析到期結算）
3. 更新分數（Performance Store / leaderboard）

## 每週 / trigger（`automation/training_policy.py`）
- 可自動重訓：xgboost / lightgbm / nhits / nbeatsx。
- trigger：weekly / drift / degradation / manual（且 new samples ≥ min）。

## 之後
validation → walk-forward → shadow → forward paper。

## 最後
**只推薦 promotion**（`AUTO_PROMOTE_CHAMPION = false`，需 human approval）。

## PC 可以關機
- 開機後 catch-up（`automation/loop.py::run_catchup`）補缺。
- 只有未來啟用 Yuanta realtime Tick/L2 Recorder 才需要交易期間保持開機。
