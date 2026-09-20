# Forward Paper Test（前向樣本外測試）

Phase 2A 的**前向紙面測試**：在「當下」建立並永久保存預測，等 horizon 到期後用**實際值**結算。
**不得用事後資料重建後冒充 Forward Test。**

## CLI

```powershell
python -m market_ai_hub.research.forward run        # 建立預測（^N225、3706.TW）
python -m market_ai_hub.research.forward settle     # 結算到期預測
python -m market_ai_hub.research.forward status     # 檢視 open/settled
python -m market_ai_hub.research.forward leaderboard # 依 model 聚合績效
```

## 命令說明

### run

```powershell
python -m market_ai_hub.research.forward run --symbols "^N225,3706.TW" --horizon 1d [--mlflow]
```

- 對每個 symbol 用既有 V1 模型（chronos-2 / timesfm-3.0 / xgboost / lightgbm / ensemble）
  產生預測，並**立即永久註冊**到 Prediction Registry。
- 每筆預測帶 `forecast_origin`、`forecast_target_dates`、`information_cutoff`、`input_data_hash` 等。
- `--mlflow`：同時以 MLflow 記錄 run（params / metrics / artifact reference）。

### settle

```powershell
python -m market_ai_hub.research.forward settle --forecast-id <ID>
python -m market_ai_hub.research.forward settle --all
```

- 對**已到期**（target date ≤ 今天）且尚未結算的預測，抓實際收盤價並結算。
- 目標日期還沒到 → 回「尚未到達，無法結算」，不做假。
- 結算為 append-only：計算 `absolute_error / squared_error / scaled_error /
  direction_result / interval_hit / pinball_loss`，不回頭改 forecast。

### status / leaderboard

- `status`：列出預測（open / settled）。
- `leaderboard`：對已結算預測，依 model 聚合 `n / MAE / RMSE / direction_accuracy /
  interval_coverage / pinball_loss`。

## 目前支援 symbol

- `^N225`（TSE / XTKS 日曆）
- `3706.TW`（TWSE / XTAI 日曆，優先 TWSE 官方資料，fallback yfinance）

## No look-ahead 保證

- 預測只使用 `information_cutoff`（= `forecast_origin`，最後一根已觀察 bar）之前的資料。
- `assert_no_lookahead(cutoff, timestamps)`：任何 `available_at > cutoff` 的資料都會被拒絕
  （拋 `LookAheadError`）。

## 標準化評估（FEV adapter）

`market_ai_hub.research.evaluation.FEVAdapter` 提供統一評估入口：

- 價格 baselines：Last Price Naive / Random Walk / Drift / Moving Average
- 分類 baselines：Majority Class / Always Flat
- 價格 metrics：MAE / RMSE / MASE / Pinball Loss / Interval Coverage / Calibration Error
- 分類 metrics：Accuracy / Balanced Accuracy / Macro F1 / MCC
- **不固定 50% 當門檻**（門檻 = max(majority_class_baseline, uniform)）
- autogluon / fev 為**可選整合**（未安裝 → `available=False`，用內建 baselines）。

保留既有 `backtest/walk_forward.py` 不變。

## 注意

- Forward test 產物存 `data/registry/`（gitignored，不入 repository）。
- MLflow 使用本地 sqlite backend（`mlflow.db`，gitignored），不啟動 server。
