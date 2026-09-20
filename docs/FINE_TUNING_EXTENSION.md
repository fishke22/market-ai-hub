# Fine-Tuning 擴充點（FineTuneAdapter）

`strategy/fine_tune.py`。只提供 extension point，**不得因 interface 存在就開始重度微調**。

## Interface
```
FineTuneAdapter
  supported        布林（此模型是否 enable）
  foundation       布林（是否 foundation model）
  prepare_dataset()
  train()
  evaluate()
  save_artifact()
  rollback()
```

## 目前狀態
| Model | supported | foundation |
|---|---|---|
| xgboost | ✅ true | false |
| lightgbm | ✅ true | false |
| nhits | ✅ true | false |
| nbeatsx | ✅ true | false |
| kronos-tw / sundial / moirai-2 / ttm / timesfm / chronos | ❌ disabled | true |

- `get_adapter(model)` 回傳對應 adapter；未登錄 → `FoundationModelAdapter`（disabled）。
- 四個 enabled adapter 的 `train/evaluate/...` 目前是 `NotImplementedError`（extension point），
  實際 heavy 訓練需手動觸發，避免無人時鎖 GPU。

## 使用原則
- Model prediction 不是交易策略本身。
- 模型偏多只在「該模型於此 target/horizon 有足夠 OOS evidence」且
  「目前 Regime 歷史條件有 Edge」時，才提升 Strategy Candidate 信心（Model-assisted，見 I）。
