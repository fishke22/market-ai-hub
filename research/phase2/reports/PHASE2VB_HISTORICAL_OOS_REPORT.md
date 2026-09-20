# PHASE 2V-B — HISTORICAL OOS VALIDATION REPORT

- Gate：**PHASE2VB_PASS**（exam 執行正確；PASS 不代表模型有 edge）
- Protocol：`HISTORICAL_OOS_PROTOCOL.yaml`（v1，pre-registered，跑完前凍結）
- 前置：PHASE2VA_PASS + PHASE2YH_PASS
- 禁止遵守：無 Live Trading / 無 PnL optimization / 無 parameter mining / 無 leakage / 無 champion promotion / 無 GitHub publication

---

## 0. 頭條結論
**在 point-in-time walk-forward 條件下，沒有任何模型（簡單 / ML / foundation / ensemble）在 ^N225 proxy 上顯著打敗 LAST_VALUE / DRIFT baseline。** 直接 OSE Micro target 因 settlement 歷史僅 1 交易日 → INSUFFICIENT_EVIDENCE。這是誠實結果，不是失敗。

## 1. Direct Micro 最佳 baseline？
**無法回答（INSUFFICIENT_EVIDENCE）**。OSE Micro settlement 官方歷史僅可取得 1 交易日（20260918，4 個契約月）。
JPX 公開 settlement CSV 為**當日-only**（hashed URL），歷史日期回 404（`DIRECT_TARGET_COVERAGE.json` 已驗證抽樣 7 個歷史日期全 404）。
→ 完整 settlement 歷史需 J-Quants API key（NEEDS_CONFIG）或授權來源。**未用 proxy 補 Micro settlement**（違反即 leakage）。

## 2. 哪些模型真正 beat baseline？
**沒有**。以下全部在 ^N225 上無法打敗 baseline（DM p 不顯著或更差）：

| model | h=1 MASE | h=3 MASE | h=5 MASE | 結論 |
|---|---|---|---|---|
| LAST_VALUE | 1.000 | 1.000 | 1.000 | baseline |
| DRIFT | 1.000 | 0.999 | 0.997 | baseline（h≥3 最佳） |
| RIDGE | 1.004 | 1.004 | 1.001 | 更差 |
| VAR | 1.001 | 0.998 | 0.997 | ≈baseline（不顯著） |
| KALMAN | 2.150 | 1.482 | 1.289 | 顯著更差 |
| chronos-2 | 1.067 | 1.026 | 1.031 | 更差 |
| timesfm-3.0 | 1.005 | 0.981 | 1.033 | ≈baseline（不顯著） |
| equal_weight ensemble | 1.169 | 1.044 | 1.017 | 更差 |
| dynamic ensemble | 1.053 | 1.013 | 0.999 | ≈baseline |

MASE = 1.0 代表與 LAST_VALUE 同；>1.0 更差；<1.0 更好。

## 3. 改善幅度多少？
**0 / 負值**。無模型提供正向 MAE 改善；delta_vs_baseline ≥ 0（`PROXY_REFERENCE_OOS_RESULTS.csv`）。

## 4. CI 是否跨 0？
**是**。所有模型 vs baseline 的 MAE delta 之 block-bootstrap 95% CI 皆跨 0（delta≈0，無顯著差異）。

## 5. DM / FDR 是否支持？
**否**。Diebold-Mariano（Newey-West HAC，overlap 修正）：
- RIDGE/VAR vs baseline：dm_p = 0.25~0.81（不顯著）。
- KALMAN：dm_p ≈ 0（顯著**更差**於 baseline）。
- 經 Benjamini-Hochberg FDR 後無任何模型通過「beat baseline」的 primary comparison。

## 6. 不同 regime 是否穩定？
**否 — 無 regime 一致的 edge**（`REGIME_OOS_RESULTS.csv`，h=1）：

| regime | N | last_value MAE | ridge MAE | ridge beats? |
|---|---|---|---|---|
| LOW_VOL / TREND_UP | 417 | 0.008006 | 0.008044 | 否 |
| LOW_VOL / TREND_DOWN | 203 | 0.008965 | 0.008930 | 是（~0.4%，noise） |
| HIGH_VOL / TREND_UP | 267 | 0.011171 | 0.011315 | 否 |
| HIGH_VOL / TREND_DOWN | 207 | 0.014987 | 0.014977 | 是（~0.07%，noise） |

TREND_DOWN 中 ridge 的「優勢」在誤差量級內，非可重複 edge。

## 7. 1d / 3d / 5d 哪個 horizon 較可預測？
**無一可預測**。三 horizon 下無模型打敗 baseline。direction accuracy 全落在 0.48~0.58（近 50% 隨機）。

## 8. Dynamic Ensemble 有沒有 evidence？
**NO_EVIDENCE_OF_ENSEMBLE_EDGE**。dynamic ensemble（recent inverse-error weighting）MASE 0.999~1.053，
與 static equal-weight（1.017~1.169）皆不 beat baseline。**不因名字叫 Dynamic 就升級**。

## 9. 哪些模型沒有 evidence？
**全部**。XGBoost / LightGBM（方向 acc 0.51~0.55，無 edge）、VAR / Kalman / Ridge、Chronos-2 / TimesFM-3.0、
equal-weight / dynamic ensemble —— 皆 **NO_EVIDENCE**。

## 10. 最大失效條件？
**HIGH_VOL / TREND_DOWN**（MAE 最大 0.01499，約 LOW_VOL/TREND_UP 的 1.9 倍）。
所有模型在高波動下行 regime 誤差放大；無模型能在此 regime 提供保護。
（見 `MODEL_FAILURE_ANALYSIS.md`。）

---

## Sample size（n）
- ^N225 proxy：1223 bars → h=1 **1094 origins**（SUBSTANTIAL_SAMPLE）、h=3 1092、h=5 1090。
- foundation models（chronos/timesfm）：subsample step=10 → ~110 origins（MODERATE_SAMPLE，已於 manifest 標記）。
- XGB/LGBM：subsample step=5 → ~207 origins（MODERATE_SAMPLE）。
- DIRECT OSE Micro：0 origins → INSUFFICIENT_EVIDENCE。

## 統計方法（已執行）
- 點-in-time：每 origin 只使用 origin 前資料（history_len=128），無 future leakage。
- Moving-block bootstrap（block=5，500 resamples）→ 95% CI。
- Diebold-Mariano + Newey-West HAC（overlap 修正）。
- Benjamini-Hochberg FDR（primary = champion_candidate vs BEST_SIMPLE_BASELINE）。
- expanding walk-forward（非 random split）；test 未用於 tuning。

## Evidence labels（最終）
| model | evidence |
|---|---|
| 全部 proxy 模型 | **NO_EVIDENCE** |
| DIRECT OSE Micro | **INSUFFICIENT_EVIDENCE**（data coverage） |
| NHITS / NBEATSx | **RUNTIME_BLOCKED**（training-only，無 runtime adapter） |

## 與 2V-A 一致性
2V-A 標記「Dynamic Ensemble UNVALIDATED_FORWARD」與「所有 base model UNVALIDATED」——
本棒 historical OOS 證實：即使跑完整 walk-forward，也**無 edge**，與先前誠實標記一致。

## Gate 判定
- ✅ walk-forward 正確（點-in-time、無 random split、無 test-for-tuning）
- ✅ settlement 未誤標 close；proxy 未誤標 target
- ✅ 統計正確（block bootstrap + DM HAC + FDR）
- ✅ 無 leakage / 無 target contamination / 無 silent exclusion
- ✅ 無 auto Champion promotion（AUTO_PROMOTE=false；最多 CHAMPION_CANDIDATE，此棒無 candidate）
- ✅ 模型 runtime unavailable → MODEL_NOT_EXAMINED / RUNTIME_BLOCKED（不是假 PASS）

**PHASE2VB_PASS**（exam 執行正確；結論 = 所有模型 NO_EVIDENCE，誠實保留）。
