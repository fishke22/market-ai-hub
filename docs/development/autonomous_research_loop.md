# 自主研究循環（Autonomous Research Loop）

與 MCP / Cherry Studio 完全獨立，**不含交易**。

## CLI
```
python -m market_ai_hub.automation status
python -m market_ai_hub.automation tick
python -m market_ai_hub.automation catchup
python -m market_ai_hub.automation run-job JOB
```

## 10 步每日循環（`loop.py`）
1. sync_market_data     增量補資料（offline → OFFLINE_DEFERRED）
2. validate_data        資料品質（TargetDataQualityValidator）
3. update_normalized    正規化更新
4. update_features      特徵更新
5. settle_predictions   結算到期預測
6. settle_analysis      結算到期分析
7. recompute_metrics    重算 metrics
8. update_leaderboard   更新 leaderboard
9. river_shadow         drift 監測
10. training_due_check  自動學習 eligibility

## 行為規則
- 無工作 → 快速結束
- offline → `OFFLINE_DEFERRED`（不刪資料、不偽造）
- GPU busy → `TRAINING_DEFERRED_GPU_BUSY`
- 開機 catchup 補 missing data / unsettled / metrics / features

## 狀態
`scheduler.py`（DuckDB `jobs` 表）：job_name / last_success / last_attempt / next_due /
status / error / retry_count。
