# 歷史策略研究引擎（Historical Strategy Research）

本 phase 目標：用累積的歷史資料、Feature Store、Regime、Prediction Registry 與
Model Tournament 結果，研究哪些「可重現條件」具有歷史 Edge。

本棒**不做** Live Trading / Yuanta 即時 Recorder / 自動下單，不以 TradingView 為核心資料來源。

## 核心模組（`src/market_ai_hub/strategy/`）

| 檔 | 職責 |
|---|---|
| `contract.py` | StrategyCandidate + 狀態機 |
| `signal_dataset.py` | point-in-time correct 信號資料集 |
| `search.py` | 可解釋條件規則搜尋 |
| `edge_store.py` | HistoricalEdgeStore（條件 Edge 統計） |
| `cost.py` | 交易成本模型（ZERO/BASE/STRESS） |
| `walk_forward.py` | TRAIN→VALIDATION→FROZEN TEST + rolling |
| `metrics.py` | 完整策略績效 metrics |
| `overfitting.py` | 防 overfitting guard |
| `output.py` | TRADE_CANDIDATE / WAIT / NO_EDGE |
| `fine_tune.py` | FineTuneAdapter 介面 |
| `tradingview_bridge.py` | TradingView 選配橋接介面 |
| `yuanta.py` | Yuanta 未來 placeholder |

## 策略狀態機
```
EXPERIMENTAL → RESEARCH_CANDIDATE → SHADOW → REJECTED
（明確禁止 PRODUCTION_TRADING）
```

## 研究輸出（三態皆合法）
- `TRADE_CANDIDATE`：edge 成立且通過 overfitting guard
- `WAIT`：edge 存在但條件未對齊 / 疑慮
- `NO_EDGE`：無 edge 或樣本不足

不強迫每天 LONG / SHORT。

## 研究方法
1. 先找簡單可解釋 rule（forecast direction + strength + trend/risk/rates/JPY regime + event state）。
2. 研究 1d / 2d / 5d / 10d forward returns 分佈。
3. 找「多窗口仍成立」的 rule，不從複雜 RL 開始。

## Point-in-time correctness
- 每列只含「當時真的已知」資料；forward return 是 label，不是 feature。
- Regime 用 backward asof join，未來 regime 不得用於過去決策。
- 禁止 future leakage；不得因事後知道漲跌而回頭改 Regime/Feature。

## 交易成本
Backtest 一律回報三種成本：ZERO_COST / BASE_COST / STRESS_COST。不得只報無成本績效。
