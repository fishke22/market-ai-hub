# Historical Edge Store

條件 Edge 統計（`strategy/edge_store.py`），DuckDB 儲存於 `data/strategy/edges.duckdb`。

## HistoricalEdge 欄位
- market / instrument / horizon / conditions
- sample_size
- mean_forward_return / median_forward_return
- positive_rate
- downside_quantile（5%）/ upside_quantile（95%）
- max_adverse_excursion / max_favorable_excursion
- expected_value
- confidence_interval（95%）
- status

## 狀態判定
- `EDGE_FOUND`：95% CI 下限 > 0
- `NO_EDGE`：95% CI 上限 < 0
- `INSUFFICIENT_EVIDENCE`：樣本不足（預設 < 30），或 CI 跨 0 不顯著

## 用法
```python
from market_ai_hub.strategy.edge_store import HistoricalEdgeStore, compute_edge
from market_ai_hub.strategy.search import search_edges, search_condition_combos, stable_across_horizons

# 單一條件值 edge
e = compute_edge(returns, market="Nikkei", instrument="^N225", horizon="fwd_5d",
                 conditions={"trend_regime": "bull"})

# 深度搜尋 + 多窗口穩定 rule
edges = search_condition_combos(dataset, "Nikkei", "^N225")
stable = stable_across_horizons(edges, min_horizons=2)

store = HistoricalEdgeStore(); store.record(e)
```

## 範例（Nikkei 條件）
```
TREND_UP + RISK_ON + JPY_WEAKENING
→ sample_size / mean_forward_return / positive_rate / MAE / MFE / EV / CI
```
樣本不足 → 直接標 `INSUFFICIENT_EVIDENCE`，不得宣稱 Edge。

## 防 overfitting（`strategy/overfitting.py`）
- minimum_trade_count（預設 30）：5 筆贏 4 次不得稱 EDGE_FOUND。
- multiple-window validation：同 rule 需在多 horizon 仍成立。
- parameter-complexity penalty：參數過多折減 edge。
- stability check：跨窗口 sign 一致且 std 小於平均絕對值。
