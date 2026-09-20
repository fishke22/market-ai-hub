# PHASE 2V-C — EXECUTION-AWARE STRATEGY VALIDATION REPORT

- Gate: **PHASE2VC_PASS**（strategy validation 執行正確；不代表 profitable）
- 前置: PHASE2VB3_PASS
- Candidate: VAR(1), DIRECT_MICRO_CONTINUOUS_BAR, horizon=1

---

## 0. 頭條結論

**VAR(1) 的 forecast edge 無法轉成標準 open-to-close 執行下的正期望值。** 策略在零成本下就虧損，所有 cost scenario、所有 regime、所有 subperiod 皆負。**分類：NO_ECONOMIC_EDGE**。

**關鍵發現**：VAR 預測的 close-to-close 方向準確率 62.2%（真實 edge），但 tradable 的 open-to-close 方向與 VAR 預測**反向相關 (-0.378)**，只有 32.4% 準確。**edge 集中在 overnight gap（close→open），不在 intraday（open→close）。**

---

## 1. 問答（13 題）

### 1. VAR gross expectancy 是多少？
**-259.4 points/trade**（負值）。831 筆 OOS trades，gross PnL = -215,570 points。

### 2. BASE_CONSERVATIVE_COST (C2) 後 expectancy？
**-280.4 points/trade**（比 gross 更差）。因為成本只會加劇已存在的負期望值。

### 3. 可以承受多少 ticks 才 break even？
**0 ticks**。策略在**零成本下就已是負期望值**，無 break-even 空間。gross expectancy 本身為負。

### 4. 每年大約交易幾次？
**252 trades/year**（每天反手，full turnover）。因為 zero-threshold 讓策略每天都有倉位（多或空）。

### 5. LONG/SHORT 誰貢獻 edge？
**兩邊都虧**。LONG：-153 pts/trade（484 trades）；SHORT：-408 pts/trade（347 trades）。SHORT 虧損更嚴重。

### 6. HIGH_VOL/TREND_DOWN 是否仍失效？
**是，且更嚴重**。HIGH_VOL|TREND_DOWN = -406 pts/trade（最差 regime）。LOW_VOL|TREND_DOWN = -81 pts/trade（相對最好，但仍負）。與 2V-B.3 一致：高波動下行是失效區。

### 7. 最大 drawdown？
**-215,125 points**（C0 zero-cost）。這不是帳戶 NAV，是 continuous series 的點數累積虧損。

### 8. 最差 subperiod？
**2026H2（-563 pts/trade）**。且隨時間惡化：2023H2 -126 → 2026H2 -563。edge 不是靜態的。

### 9. edge 是否集中在少數月份？
**否**。所有 7 個 subperiod 皆負，且隨時間持續惡化。無「少數月份貢獻全部利潤」的假象，而是「全週期穩定虧損」。

### 10. roll window 是否造成假利潤？
**否（相反）**。continuous series 的 roll 沒有製造假利潤；策略在所有週期都虧損，roll 不是利潤來源。edge 不存在，故無 roll 假利潤問題。

### 11. execution delay 是否消滅 edge？
**不適用**。策略在**零成本、零延遲**下就已是負期望值。execution delay 只會更差，edge 根本不存在於 open-to-close 執行。

### 12. VAR 是 ROBUST / TENTATIVE / FRAGILE / NO_EDGE？
**NO_ECONOMIC_EDGE**（對 open-to-close 執行）。

原因拆解（關鍵）：
- VAR forecast 對 close-to-close 方向準確 62.2%（MASE=0.958，2V-B.3 的真實 edge）
- 但 close-to-close = **overnight gap（close→open）** + **intraday（open→close）**
- VAR 的 edge 集中在 **gap**（夜盤開盤跳空 momentum）
- intraday（open→close）與 VAR 預測**反向相關 (-0.378)**（盤中均值回歸）
- 標準執行「signal at close → enter at open → exit at close」只 capture 到 intraday 反轉，錯過 gap

### 13. 是否值得進 2V-D Forward Shadow？
**Forecast 值得，Strategy 不值得（以現行執行方式）**。
- VAR 的 close-to-close forecast edge（62.2%）是**真實 research signal**，值得 forward 追蹤。
- 但**沒有可執行的 strategy edge**（open-to-close 反轉）。
- 若 2V-D，應追蹤「close-to-close forecast 準確率」而非「open-to-close strategy PnL」。
- 若要 trade gap，需另建 gap-specific 執行（屬 future protocol，非本棒）。

---

## 2. Cost Scenario 表（全部公開）

| Scenario | 成本模型 | Net expectancy | Net PnL | Win rate | Max DD |
|----------|----------|----------------|---------|----------|--------|
| C0 | ZERO_COST | -259.4 pts | -215,570 | 32.1% | -215,125 |
| C1 | LOW (1 tick/side) | -269.9 pts | -224,296 | 31.5% | -223,798 |
| C2 | BASE_CONSERVATIVE (2 ticks) | -280.4 pts | -233,021 | 30.7% | -232,475 |
| C3 | HIGH_STRESS (4 ticks) | -301.4 pts | -250,472 | 29.5% | -249,905 |

## 3. Regime 表

| Regime | Trades | Avg gross pts | Avg net (C2) |
|--------|--------|---------------|--------------|
| LOW_VOL\|TREND_DOWN | 89 | -80.7 | -101.7 |
| LOW_VOL\|TREND_UP | 259 | -184.8 | -205.8 |
| HIGH_VOL\|TREND_UP | 289 | -282.6 | -303.6 |
| HIGH_VOL\|TREND_DOWN | 194 | -406.4 | -427.4 |

## 4. Subperiod 表

| Subperiod | Trades | Avg gross pts |
|-----------|--------|---------------|
| 2023H2 | 9 | -126.1 |
| 2024H1 | 153 | -154.5 |
| 2024H2 | 155 | -272.0 |
| 2025H1 | 152 | -185.2 |
| 2025H2 | 157 | -190.5 |
| 2026H1 | 152 | -399.5 |
| 2026H2 | 53 | -562.8 |

## 5. 統計

- Block bootstrap (block=5, 500 resamples) 95% CI: C0 net expectancy CI = [-316.8, -212.2]，**完全不跨 0**（負期望值顯著）。
- 所有 cost scenario 的 CI 皆為負，無一跨 0。

## 6. 資料語義誠實聲明

- PnL 標籤：**RESEARCH_PNL**（非 REALIZED_EXECUTABLE_PNL）
- execution_quality：**APPROXIMATE_RESEARCH_EXECUTION**
- continuous series：**CENTER-MONTH CONTINUOUS**（非 contract-level executable）
- 無 historical contract identifier / bid-ask / order book / broker fills

## 7. 執行細節

- Entry：T+1 open（夜盤開盤，T close 後 75 分鐘）
- Exit：T+1 close（日盤收盤）
- Position：fixed 1 unit（±1），no leverage/Kelly/pyramiding
- 無 SL/TP（fixed horizon exit）
- 無 threshold optimization（zero-threshold，training-only threshold 未在 test 調）

## 8. Lookahead Audit

- 逐 trade 驗證：signal_created_at (T close) < entry_timestamp (T+1 open)，無 lookahead。
- Reconciliation：抽樣驗證，ledger 與 aggregate summary 一致。

---

## 9. 最終分類

**VAR(1) strategy = NO_ECONOMIC_EDGE**（對 open-to-close 執行）。

**但 VAR forecast（close-to-close）= 真實 research edge 保留**（MASE=0.958, dir_acc=62.2%）。

兩者不矛盾：forecast edge 在 gap，strategy 只 trade 到 intraday 反轉。

## 10. Champion 狀態

- 維持：**CHAMPION_CANDIDATE（forecast 層級）**，不是 PRODUCTION_CHAMPION。
- 但 strategy 層級：**NO_ECONOMIC_EDGE**，不得以 strategy 名義進 production。
- AUTO_PROMOTE=false。

## Gate 判定

- ✅ strategy validation 執行正確（walk-forward, no lookahead, no same-close fill）
- ✅ cost scenarios 全公開（C0-C3），未挑最好看 cost
- ✅ break-even cost 計算（=0，零成本即負）
- ✅ long/short 分開、regime/subperiod 全報
- ✅ continuous series 標 RESEARCH_PNL，未誤標 executable
- ✅ no test-set threshold optimization
- ✅ 結果誠實：NO_ECONOMIC_EDGE（仍可 PASS）

**PHASE2VC_PASS**
- **Strategy 分類：NO_ECONOMIC_EDGE**
- **Forecast 保留：CHAMPION_CANDIDATE（close-to-close 62.2%）**
- **關鍵發現：VAR edge 在 overnight gap，不在 intraday open-to-close**
