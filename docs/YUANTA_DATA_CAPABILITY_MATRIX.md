# Yuanta Data Capability Matrix

本棒**不登入、不啟動 Recorder**。realtime recording 仍 disabled。

| API / 功能 | 能力 | 用途 | 狀態 |
|---|---|---|---|
| `GetKLine` | 僅 TWSE/TWOTC 歷史 K 線 | 加入台股 Data Lake | ACTIVE（台股） |
| `GetStkTickDetail` | 當日 Tick | 保留 OSE capability probe | PROBE（realtime disabled） |
| `GetStkClassifyPrice` | 當日分價量 | 保留 capability probe | PROBE |
| `Watchlist` / `FiveTick` | streaming only | 目前 disabled | DISABLED |

## 規則
- OSE（日經期貨）不依賴 Yuanta；OSE 資料走 JPX official OSE Daily Report。
- Yuanta `GetKLine` 只涵蓋台股歷史，不含 OSE 期貨歷史。
- Tick/L2 Recorder 未來啟用才需要市場交易期間保持電腦開機。
- 本 phase 不得登入 Yuanta、不得啟動 Recorder。
