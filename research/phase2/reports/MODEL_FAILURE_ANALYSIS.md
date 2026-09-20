# MODEL FAILURE ANALYSIS（Phase 2V-B）

> 找每個模型的失效條件（worst-decile errors 落在哪些 regime / vol 條件）。
> 目的不是修模型，是標記「何時不可信」。

## 方法
- target：^N225 proxy，h=1 forward return。
- 每個 origin 的 |error| 排序取 top-10% decile，統計其 regime / vol 分布。

## 觀察（來自 REGIME_OOS_RESULTS.csv + exam）
| 條件 | 平均 |MAE| | 說明 |
|---|---|---|---|
| LOW_VOL / TREND_UP | 0.008006 | 最低誤差（calm 上行） |
| LOW_VOL / TREND_DOWN | 0.008965 | 低波動下行 |
| HIGH_VOL / TREND_UP | 0.011171 | 高波動上行 |
| HIGH_VOL / TREND_DOWN | 0.014987 | **最高誤差（高波動下行）** |

## 失效條件結論
1. **高波動下行（HIGH_VOL / TREND_DOWN）** 是所有模型誤差放大最多的 regime（約 calm 上行 1.9×）。
2. 所有模型（含 Chronos/TimesFM）在此 regime 無保護，方向準確率掉向 50%。
3. **roll period / event window**：因直接 Micro settlement 歷史不足，roll 分段無法統計（INSUFFICIENT_EVIDENCE）；
   僅 proxy ^N225 無 roll，此為 DIRECT 資料缺口所致。

## 對使用者的意義
- 任何模型在此專案的預測，**於高波動下行 regime 均不具備可依賴 edge**。
- 不應在任何 regime 下以模型預測作為交易依據（本專案無 strategy/execution，僅 research）。
