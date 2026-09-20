# Forecast Synthesis（預測統合層）

`forecast/synthesis.py`。

## ForecastSynthesisResult（分開保留，不混成單一 final_price）
- direct_forecast
- joint_forecast
- scenario_forecast
- dynamic_ensemble
- best_baseline
- historical_edge
- regime
- event_state
- research_state

## research_center（Q）
- 禁止 LLM 看完結果後手動改 P50 成 research center 而無法重現。
- 若提供 `research_center`，必須附 `research_center_method` / `research_center_inputs` /
  `research_center_version`，全部 deterministic + reproducible。
- 否則不建立獨立 research_center。

## Historical Edge 整合（R）
- Phase 2F HistoricalEdgeStore 只作 Research Evidence，不修改模型 forecast。
- 例：Forecast 偏多 + Edge 無足夠證據 → 輸出 `MODEL_BULLISH + EDGE_UNPROVEN`，不偷改為 bearish。

## ResearchState（S，不強迫多空）
```
BULLISH_EVIDENCE / BEARISH_EVIDENCE / MIXED / WAIT / NO_EDGE /
INSUFFICIENT_DATA / MODEL_DISAGREEMENT / BASELINE_DOMINANT
```

## Forward test registration（V）
Joint / Scenario / Dynamic Ensemble 也註冊到 Prediction Registry
（`forecast/registration.py`），Outcome 到期後由 Phase 2E automation settlement 自動計分。
