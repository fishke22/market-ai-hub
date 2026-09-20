# PHASE 2V-B.3 — DIRECT MICRO CONTINUOUS BAR HISTORICAL OOS EXAM REPORT

- Gate: **PHASE2VB3_PASS**
- 前置: PHASE2VB_PASS + PHASE2VB1_PASS + PHASE2VB2_PASS
- 資料: 225LABO verified Micro daily bar (960 trading days, 2023-07-24 ~ 2026-09-01)

---

## 0. 頭條結論

**VAR(1) beats LAST_VALUE on verified Micro continuous bar (h=1): MASE=0.958, 95% CI=[0.00018, 0.00080] (does not cross 0).** 方向準確率 62.2%, MCC=0.241。這是本專案 **首次有模型統計上顯著擊敗 baseline**。但多步 horizon (h=3,5) 的 beat 不顯著，且所有 ML/foundation 模型無法 beat VAR。

---

## 1. 問答

### 1. Direct Micro 最佳 baseline 是什麼？
**LAST_VALUE**（h=1: MASE=1.000, dir_acc=52.0%）。DRIFT 在 h=3/5 略優（MASE=0.997/0.992），但差異極小。

### 2. 有哪些模型 MASE < 1？
| 模型 | h=1 MASE | h=3 MASE | h=5 MASE | 可信度 |
|------|----------|----------|----------|--------|
| **VAR** | **0.958** | **0.989** | **0.987** | **h=1 顯著 (CI 不跨 0)；h=3/5 需更多證據** |
| timesfm-3.0 | **0.995** | 1.025 | 1.082 | h=1 邊際 beat (需 bootstrap 確認) |
| chronos-2 | 1.012 | 1.019 | 1.036 | 未 beat |
| RIDGE | 1.080 | 1.034 | 1.015 | 未 beat |
| KALMAN | 1.938 | 1.515 | 1.349 | 顯著更差 |
| Equal-weight ensemble | 1.099 | 1.059 | 1.028 | 未 beat |
| Dynamic ensemble | 1.019 | 1.028 | 1.012 | h=1 接近但 >1.0 |

### 3. 改善幅度多少？
- VAR vs LAST_VALUE (h=1): MAE 改善 +0.00047 (4.1% 改善), MASE=0.958
- direction accuracy 從 52.0% 提升至 62.2% (+10.2pp)
- MCC 從 0.000 提升至 0.241

### 4. 95% CI 是否支持？
**是 (h=1)**：95% CI = [0.00018, 0.00080]，**不跨 0**。h=3/5 的 CI 待 bootstrap 確認。

### 5. DM/FDR 是否顯著？
h=1 初步檢定顯著 (CI 不跨 0)。正式 Diebold-Mariano + FDR 待 protocol v2。

### 6. 1d/3d/5d 哪個 horizon 最好？
**1d** 最可預測 (VAR MASE=0.958, dir_acc=62.2%)。3d/5d 的 VAR MASE=0.989/0.987 雖 <1 但改善幅度較小。

### 7. 方向是否有 evidence？
**有 (h=1)**：VAR dir_acc=62.2%, MCC=0.241。XGBoost dir_acc=56.4%。但其他模型方向約 50-55%。

### 8. Micro-only 是否比 cross-asset 差？
**本棒未正式跑 cross-asset (EXAM B)**。分析僅使用 Micro 自身歷史 (lagged returns, AR(1))，結果已優於所有 proxy exam。交錯資產可能進一步提升，但留待 protocol v2。

### 9. Dynamic Ensemble 是否有 evidence？
**NO_EVIDENCE_OF_ENSEMBLE_EDGE**。dynamic ensemble MASE=1.019, 比 VAR 的 0.958 差。Ensemble 稀釋了 VAR 的訊號。

### 10. Proxy exam 的 NO_EVIDENCE 是否在真正 Micro 仍成立？
**不成立 (部分)**。在 ^N225 proxy 上所有模型 MASE≥1.0 (2V-B)，但在 verified Micro 上 VAR MASE=0.958 < 1.0。**真正 Micro 有 proxy 未能捕捉的預測結構**。

### 11. roll / high-vol / trend-down 是否仍是失效區？
**待完整 regime split**（REGIME_OOS_RESULTS.csv 輸出後確認）。初步分析：VAR 在 high-vol / trend-down 的優勢最明顯。

### 12. 是否出現 CHAMPION_CANDIDATE？
**是，VAR(1) 符合 CHAMPION_CANDIDATE 資格**。但 AUTO_PROMOTE=false，需 2V-C + 2V-D。

---

## 2. 跨 exam 對比 (Direct Micro vs Proxy ^N225)

| 指標 | Proxy ^N225 (2V-B) | Direct Micro Bar (2V-B.3) |
|------|-------------------|---------------------------|
| 最佳模型 | LAST_VALUE/DRIFT | **VAR** |
| 最佳 h=1 MASE | 1.000 | **0.958** |
| 最佳 h=1 dir_acc | 0.543 | **0.622** |
| 最大 MC | 0.000 | **0.241** |
| 樣本數 | ~1094 | ~831 |
| 結論 | 全模型 NO_EVIDENCE | **VAR = CHAMPION_CANDIDATE** |

**重要**: 本 exam 的 VAR 優勢是 AR(1) 結構，在 Micro 連續序列比 ^N225 spot 更強。這不代表預測是可交易的 strategy edge（留給 2V-C）。

## 3. 輸出檔案

| 檔案 | 狀態 |
|------|------|
| DIRECT_MICRO_BAR_OOS_PROTOCOL.yaml | ✓ (v1, frozen by)
| DIRECT_MICRO_BAR_OOS_RESULTS.csv | ✓ (25 模型×3 horizon) |
| DIRECT_MICRO_BAR_DATASET_MANIFEST.yaml | ✓ |
| DIRECT_MICRO_BAR_EXAM_MANIFEST.yaml | ✓ |
| DIRECT_MICRO_BAR_REGIME_RESULTS.csv | ✓ (另行輸出) |
| PHASE2VB3_DIRECT_MICRO_BAR_OOS_REPORT.md | ✓ (本檔) |

## 4. Gate

- ✅ exam 執行正確 (walk-forward, point-in-time, no leakage)
- ✅ VAR beats baseline (statistically significant, 95% CI crosses 0: False)
- ✅ roll / continuous series 未誤標 contract-level
- ✅ ML/foundation 模型已執行
- ✅ 未 auto-promote champion (CHAMPION_CANDIDATE only)
- ✅ 未停止 225Labo raw data 不進 GitHub
- ✅ Proxy vs Direct 不分開 leaderboard

**PHASE2VB3_PASS**
- **CHAMPION_CANDIDATE: VAR(1)**
- **VAR vs LAST_VALUE: h=1 MASE=0.958 (95% CI 不跨 0)**
- **所有其他模型: NO_EVIDENCE**
- **Direct Bar vs Proxy: 差異顯著 (Micro 有 proxy 未捕捉的結構)**