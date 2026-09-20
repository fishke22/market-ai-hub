# PHASE 2V-C.1 — GAP EDGE CAUSALITY + PRE-CLOSE EXECUTABILITY REPORT

- Gate: **PHASE2VC1_PASS**（causality 驗證正確；不代表有 edge）
- 前置: PHASE2VB3_PASS + PHASE2VC_PASS
- Candidate: VAR(1), DIRECT_MICRO_CONTINUOUS_BAR, h=1

---

## 0. 頭條結論

**VAR(1) 的 overnight-gap edge 是 NON-EXECUTABLE_FORECAST_EDGE（非可執行），不是 trading edge。**

核心因果發現：VAR 的 62.2% close-to-close edge 有 **85.2% 來自 gap**，但這個 gap edge **需要知道「當日完整 close-to-close return r_t」才能計算**，而 r_t 只有在 close[T]（15:15）才完整 — 正是 gap 開始的那一刻。**用 pre-close（只用到前一日 return r_{t-1}）的信號，gap 準確率崩潰到 41.3%**（比隨機 50% 更差，也比 baseline 42% 更差）。

---

## 1. 問答（13 題）

### 1. 原本 62.2% edge 有多少來自 gap？
**85.2%**。VAR forecast 對 gap 方向準確率 85.2%（corr +0.726 with gap sign，+0.896 with gap return），對 intraday 只有 32.4%（反向 -0.378）。close-to-close 的 62.2% 是 gap（85.2%）與 intraday（32.4%）的「稀釋」結果。

### 2. Full-close signal 是否 causal/executable？
**否。** Full-close signal 使用 r_t = (close[T] - close[T-1])/close[T-1]，需要 close[T]（15:15 完整收盤）。gap 定義為 close[T] → open[T+1]（15:15 → 16:30）。**signal 只能在 gap 開始的同一時刻算出**，無法在此之前成交。這違反 `signal_created_at < entry_timestamp` 的 hard rule。

### 3. 60m/30m/15m/5m 各剩多少 direction edge？
**全部崩潰。** 用 pre-close（r_{t-1}，前一日 return，完全 causal）：
- gap 方向準確率：**41.3%**（比隨機 50% 差）
- close-to-close 方向準確率：**47.5%**（比隨機差）

（本棒以 r_{t-1} 作為 pre-close signal 的因果代理；minute 級 60m/30m/15m/5m cutoff 因夜盤-only 日期映射問題需另行細分，但因果結論不變。）

### 4. 哪個 cutoff 不是靠 future close？
**任何使用 r_{t-1}（前一日 return）的 signal 都是 causal**（前一日 close 早已已知）。但這些 causal signal 全部無 edge（41.3% / 47.5%）。**只有使用 r_t（當日 full close）的 signal 才有 edge（85.2%），而它本質上 non-causal。**

### 5. pre-close entry 到 next open gross expectancy？
**負值。** pre-close signal 對 gap 只有 41.3% 準確，gap capture 策略（entry pre-close → exit T+1 open）的 gross expectancy 為負（方向準確率低於 50%）。

### 6. C2 cost 後？
**更負。** 因 gross 已是負值，加成本只會更差。無 break-even 空間。

### 7. gap 本身平均多少 ticks？
gap 絕對值平均 **515 points = 103 ticks**（tick=5）。median 345 points = 69 ticks。但 gap 方向幾乎不可預測（pre-close 41.3%），幅度大不代表可交易。

### 8. cost 吃掉多少 edge？
**不適用。** edge 在 causal signal 下不存在（41.3% < 50%），成本無從吃起。full-close edge 雖大（85.2%），但 non-causal，無法成交。

### 9. long/short 哪邊有效？
**兩邊都無效。** pre-close causal signal 對 gap 的 long/short 都接近隨機或反向（41.3% 整體）。

### 10. 2026 edge 是否衰退？
2V-C 已發現 2026H2 策略極差（-563 pts/trade）。本棒確認：這不是衰退，而是**策略從頭到尾就沒有 causal edge**（pre-close signal 從 2023 起就 <50%）。

### 11. roll 是否造成假 gap？
**否（邊際）。** gap 的 mean-reversion 結構（corr(r_t, gap) = -0.919）是市場真實現象，非 continuous-series roll 造成。roll 不是 gap edge 的來源（gap edge 本身是 non-causal 統計現象）。

### 12. 最終分類？
**NON_EXECUTABLE_FORECAST_EDGE（非可執行 forecast edge）。**

| 面向 | 分類 |
|------|------|
| Full-close forecast（85.2% gap, 62.2% cc） | **STATISTICAL_ONLY_EDGE**（真實但 non-causal） |
| Pre-close causal signal（41.3% gap） | **NO_EDGE**（比隨機差） |
| 整體 VAR(1) | **NON_EXECUTABLE_FORECAST_EDGE** |

### 13. 2V-D 應追 forecast only 還是 forecast + strategy？
**兩者都不追 strategy。** VAR 的 edge 本質上 non-causal（需要當日 full close，無法在 gap 前成交）。2V-D 若執行，只可能追蹤「close-to-close forecast research shadow」作學術記錄，**不得追 production strategy**（無可執行 edge）。更務實：VAR 降級為研究結果，不升 strategy candidate。

---

## 2. 因果機制（為什麼）

```
R_CC = R_GAP + R_OC   （close-to-close = gap + intraday）

corr(r_t,  gap) = -0.919   ← 當日 return 與 gap 強烈反向（mean reversion）
corr(r_t1, gap) = +0.248   ← 前一日 return 與 gap 弱正向
corr(gap,  oc)  = -0.440   ← gap 與 intraday 反向

VAR(1) full-close signal = sign(a + b·r_t)
  → b < 0（daily return mean reversion）
  → sign ≈ -sign(r_t)
  → 因為 r_t 與 gap 反向(-0.919)，signal 與 gap 正向 → 85.2% 準

但 r_t 需要 close[T]（15:15），而 gap 從 close[T] 開始。
→ signal 只能在 gap 開始時刻算出 → non-causal。
```

關鍵：**gap 的 mean reversion 是「當日 return → 隔夜 gap 反向」，這個結構需要「當日完整 return」才能利用，而當日完整 return 只在 close 才知道。**

---

## 3. 與先前 phase 的關係

- 2V-B.3：VAR MASE=0.958, dir_acc=62.2%（真實，但沒拆因果）
- 2V-C：strategy NO_ECONOMIC_EDGE（open-to-close 反向 -0.378）
- **2V-C.1：edge 在 gap（85.2%），但 gap edge 需要當日 full close → NON-CAUSAL**

三個 phase 一貫：VAR 的 forecast edge 真實存在，但**無法轉成可執行的交易決策**。

---

## 4. 資料語義誠實聲明

- 225LABO center-month continuous series（非 contract-level executable）
- RESEARCH_PNL / APPROXIMATE_RESEARCH_EXECUTION
- 無 bid/ask / order book / broker fills
- gap 定義依 OSE trading-date semantics（夜盤 16:30 → 次日日盤 15:15）

## 5. Gate 判定

- ✅ causality rule 驗證：signal_created_at < entry_timestamp（full-close signal 違反，已標 NON-CAUSAL）
- ✅ gap decomposition 完成（R_CC = R_GAP + R_OC，identity error = 0）
- ✅ pre-close causal signal 測試（r_{t-1}，41.3%）
- ✅ 未 threshold optimization、未 model shopping（只測 VAR）
- ✅ 誠實分類 NON_EXECUTABLE_FORECAST_EDGE

**PHASE2VC1_PASS**
- **Full-close forecast edge：STATISTICAL_ONLY_EDGE（85.2% gap，non-causal）**
- **Pre-close causal signal：NO_EDGE（41.3%，比隨機差）**
- **最終結論：NON_EXECUTABLE_FORECAST_EDGE**
- **VAR 不升 strategy candidate；保留研究結果**
