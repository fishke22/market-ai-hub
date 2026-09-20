# Model Tournament（模型錦標賽）

Phase 2D 的**公平模型錦標賽**：所有模型在同一套 OOS / walk-forward 規則下比較。

## CLI

```powershell
python -m market_ai_hub.research.tournament run --targets "^N225,3706.TW" --horizons "1d,2d,5d,10d"
python -m market_ai_hub.research.tournament leaderboard [--target X] [--horizon H]
python -m market_ai_hub.research.tournament inspect --model MODEL
python -m market_ai_hub.research.tournament compare MODEL_A MODEL_B
```

## 公平規則（same exam）

所有模型必須用**同一** `target` / `horizon` / forecast origins / `information_cutoff` /
dataset version / feature version 才能進同一 leaderboard。

- `ExamSpec(target, horizon, dataset_version, feature_version, min_train, n_origins)` 產生
  `exam_hash`；`assert_same_exam` 拒絕不同 exam 直接比較。
- 禁止：不同測試期間 / 不同 horizon / 不同 cutoff 直接比較排名。

## Walk-forward OOS

- `n_origins` 個 rolling origins；每個 origin 只用 `information_cutoff` 之前資料。
- 每個 origin 每個模型 `fit(history)` + `forecast(history, steps)`，與 realized actual 比對。

## Metrics

- **價格**：MAE / RMSE / MASE / Pinball Loss / Interval Coverage / Interval Width / Calibration Error。
  point-only 模型**不假造** interval metrics（coverage/width/calibration = None）。
- **方向**：Accuracy / Balanced Accuracy / Macro F1 / MCC。
  `probability_calibrated=true` 才可加 Brier / ECE；未校準不得把 raw score 當真實機率。

## Leaderboard 分組

依 `target × horizon` 分開（例如 `^N225 / 5d`、`3706.TW / 5d`），**不做混合市場總分榜**。
顯示 baseline 是否被打敗（MASE < 1 = 打敗 last-price naive）。

## Champion 狀態（AUTO_PROMOTE = false）

- 新模型預設 `CHALLENGER`；安裝完成 ≠ VALIDATED。
- 只允許 `CHALLENGER` / `SHADOW` / `VALIDATED_CANDIDATE`。
- 真正 Champion 必須等 Forward Paper Test 累積足夠新樣本（本棒**不**建立 Production Champion）。

## Regime-aware reporting

Tournament 統計 `model × target × horizon × regime`，但**只做績效分組與報告**（不做 Dynamic Routing）。
regime `sample_size < minimum_sample_size` → `REGIME_EVIDENCE_INSUFFICIENT`，不得排名該 regime 冠軍。

## GPU 安全

- RTX 4060 Ti 16GB；一次只載入必要模型；`release()` 釋放 model / CUDA tensor / cache。
- `GpuGuard` 記錄 model_name / peak_vram / load_seconds / inference_seconds。
- OOM → `BLOCKED_HARDWARE`，不得無限重試。

## 結果儲存

`PerformanceStore`（`data/tournament/performance.duckdb`）保存 model / revision / target / horizon /
regime / evaluation_window / sample_size / effective_sample_size + 全部 metrics + runtime / peak_vram /
failure_rate。**不得只存 overall_accuracy。**
