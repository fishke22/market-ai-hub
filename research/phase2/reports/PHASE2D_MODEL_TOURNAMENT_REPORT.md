# PHASE2D_MODEL_TOURNAMENT_REPORT

日期：2026-09-19
範圍：`D:\MARKET_AI_HUB`（Phase 2D — Model Tournament + Challenger Models）

> ⚠️ 本報告只呈現「完全相同 OOS / walk-forward 條件」下的實測結果。
> 樣本為 bounded demonstration（每 target × horizon 用 4 個 rolling origins），
> **不足以做強結論**；本報告不寫「預測準確率已提高」這類未經充分證據支持的宣稱。

## 1. 安裝成功模型（已接入並實測）

| 模型 | 版本 | 類型 | 狀態 |
|------|------|------|------|
| Chronos-2 | 29ec3766… | price | AVAILABLE（實測） |
| TimesFM-3.0 | 43046b85… | price | AVAILABLE（實測） |
| XGBoost | 3.4.1 | direction | AVAILABLE（實測） |
| LightGBM | 4.7.0 | direction | AVAILABLE（實測） |
| FinCast | 2d7d90b1… | price（bridge, point only） | PARTIAL（實測） |
| naive baselines（5） | — | price/direction | 內建（實測） |
| statistical（Ridge/VAR/DFM/Kalman） | statsmodels 0.15.0 | price | 內建（實測） |
| NHITS / NBEATSx | neuralforecast 3.2.2 | price | INSTALLED（**adapter 未接，未跑**） |

## 2. 未安裝模型與原因

| 模型 | 原因 |
|------|------|
| Kronos-TW | license metadata UNKNOWN（HF 無 license 欄位），需查 model card；tokenizer 相依未驗證 → 未下載 |
| Sundial | **gated repo（401）**，需登入接受條款 → BLOCKED_LICENSE |
| Moirai-2 | **gated repo（401）** + 權重非商業 → BLOCKED_LICENSE |
| TinyTimeMixer (TTM) | 存在於 HF（Apache-2.0），但 `granite-tsfm` 依賴較重，inference adapter 延後 |

## 3. License 問題

- TimesFM-3.0 weights：**非商業**（`timesfm-non-commercial-license-v1.0`）。
- Moirai-2 / Sundial：**gated**（需登入接受），且 Moirai 權重非商業 → `BLOCKED_LICENSE`。
- FinCast：repo Apache-2.0，README 標 research/education。
- 完整矩陣：`docs/MODEL_LICENSE_MATRIX.md`。

## 4. Hardware 問題

- RTX 4060 Ti **16GB** 為上限。已實測模型皆未 OOM（chronos ~1.2GB、timesfm ~3GB、
  FinCast 走 CPU bridge）。無 `BLOCKED_HARDWARE`。

## 5. 各模型實際版本

見 `config/model_registry.yaml`（revision 欄位已 pin）。Chronos/TimesFM/FinCast 用既有 cache 的 snapshot revision。

## 6. ^N225 leaderboard（MASE，越低越好；<1 = 打敗 last-price naive）

| horizon | 最佳 | chronos-2 | timesfm-3.0 | fincast | last_price | random_walk |
|---------|------|-----------|-------------|---------|------------|-------------|
| 1d | seasonal 0.774 | 0.884 | 1.000 | 0.952 | 1.000 | 1.377 |
| 2d | seasonal 0.785 | 0.934 | 0.930 | 0.975 | 1.000 | 1.238 |
| 5d | seasonal 0.580 | 0.968 | 1.104 | 0.978 | 1.000 | 1.405 |
| 10d | chronos 0.980 | 0.980 | 1.521 | 0.999 | 1.000 | 1.355 |

## 7. 3706.TW leaderboard（**退化，無訊號**）

3706.TW 在評估窗期內 TWSE 日線價格**凍結在 80.5**（181 列、唯一收盤價、std=0）。
所有模型 trivially tie（MAE=0、方向全 flat）。**該標的在目前窗期無價格變動，無法排名**。

## 8. 各 Horizon 表現摘要

- **1d/2d/5d**：`seasonal_naive` 最強（MASE 0.77/0.79/0.58），顯示 ^N225 近期有強週期性；
  chronos-2 穩定打敗 naive（0.88/0.93/0.97）。
- **10d**：chronos-2 最佳（0.980），ridge 緊追（0.983）。
- **timesfm-3.0**：2d 尚可（0.93），但 5d/10d 明顯輸（1.10/1.52）。

## 9. Baseline 結果

- `last_price_naive` MASE 恆為 1.000（基準）。
- `random_walk` 最差（MASE 1.24–1.41）。
- `moving_average` 多數輸（1.02–1.34）。
- 統計模型（Ridge/VAR/DFM/Kalman）落在 naive 附近或略優（Ridge 1d 0.939、10d 0.983）。

## 10. 哪些模型打贏 Baseline（MASE < 1.0，vs last_price_naive）

- 穩定打贏：**chronos-2**（4/4 horizon）、seasonal_naive（1d/2d/5d）、ridge（1d/5d/10d）、fincast（4/4，但差距小）。
- 部分打贏：dynamic_factor（2d/5d）、kalman（5d/10d）、drift（1d/2d）、timesfm（2d）。

## 11. 哪些模型輸給 Baseline（MASE >= 1.0）

- **random_walk**（全部）、moving_average（多數）、var（多數 ~1.0）、
  **timesfm-3.0**（5d 1.10、10d 1.52）。

## 12. Regime 分析是否已有足夠樣本

- 已依 vol 標 regime（low/normal/high）並存入 performance store。
- **樣本不足**：每個 (target×horizon) 僅 4 origins → 任何 regime 分組
  `sample_size < minimum_sample_size`，**標 REGIME_EVIDENCE_INSUFFICIENT，不做 regime 冠軍排名**。

## 13. Runtime / VRAM

- chronos-2：~1–2s/forecast，peak ~1.2GB；timesfm-3.0：~2–3s，~3GB；
- fincast（CPU bridge）：~6–10s/forecast（subprocess 冷啟動）；classifier/統計/naive：<1s。
- 無 OOM。

## 14. Tests

`pytest` 全部 **211 passed**（154 V1 + 12 2A + 12 2B + 17 2C + 16 2D）。
build_id 維持 `bbf3cb2f9a80d20e`（V1 correctness 未變）。

## 15. Blockers

1. 3706.TW 目前窗期價格凍結（80.5）→ 對該標的 Tournament 退化，無法排名。
2. Kronos-TW license 未知；Sundial/Moirai-2 gated → 未下載。
3. NHITS/NBEATSx/TTM 已安裝/可安裝，但 adapter 未接（runtime 考量）。
4. n_origins=4 為 bounded demonstration，樣本小，非最終排名。
5. AUTO_PROMOTE=false：無 Production Champion（需等 Forward Paper Test 累積新樣本）。

## 結論

在完全相同的 OOS walk-forward 條件下，**chronos-2 穩定打敗 last-price naive（4/4 horizon）**；
seasonal_naive 在短 horizon 極強；timesfm-3.0 在長 horizon 輸給 naive。
這是實測結果，非「新模型一定較準」。
