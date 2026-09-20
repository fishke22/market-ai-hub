# Analysis Packet（分析封包）

`get_analysis_packet` 由 Python backend 先完成大部分工作，DeepSeek 不再自行抓數十個 raw MCP result。

## MCP tool
```
get_analysis_packet(market, target, horizon, detail_level, save_analysis)
```
- market：`osaka` | `taiwan`
- target：`OSE_NIKKEI225_MICRO_FUTURES` | `3706.TW` ...
- horizon：`1d` / `2d` / `5d` / `10d`
- detail_level：`compact` | `normal` | `audit`
- save_analysis：預設 true（存 Analysis Archive）

## Schema（§4）
- analysis_packet_id / created_at / information_cutoff
- execution_target / contract_month / exchange
- reference_price / reference_price_type / price_timestamp / target_data_status
- forecast_target_dates / horizon / market_session / freshness
- regime / event_state / upcoming_events
- direct/joint/scenario/dynamic_ensemble summary
- best_baseline / best_validated_model / challenger_status
- model_range / research_center / research_center_method / research_center_version
- support/resistance/invalidation levels
- historical_edge_summary / strategy_research_state
- top_positive_drivers / top_negative_drivers / contradictions
- data_quality / data_coverage_summary / research_gates / reanalysis_conditions
- data_reused / data_fetched / data_stale / data_missing（Data Lake 狀態）
- ensemble_validation / ensemble_distribution_validated / ensemble_quantile_method
- analysis_id / saved_to_archive

## 語義守則
- **Micro price**：只有 settlement → `price_type=SETTLEMENT`，不得稱 LIVE_PRICE/CLOSE。
- **Forecast 分層**：DIRECT / JOINT / SCENARIO / DYNAMIC_ENSEMBLE / BEST_BASELINE 保留，不混成 single final_prediction。
- **Ensemble**：未 forward-validated → `RESEARCH_ENSEMBLE / UNVALIDATED_FORWARD`。
- **Quantile**：component summary → `ENSEMBLE_RESEARCH_QUANTILE_SUMMARY`，非 predictive interval。
- **research_center**：必須附 method/inputs/version，deterministic。
- **Data coverage**：不得隱藏缺口（LIVE_VERIFIED / CONTRACT_ONLY / NEEDS_CONFIG / MISSING）。

## detail_level
- compact：只回最重要結果，不塞 debug。
- normal：加模型與資料來源細節。
- audit：加 model revisions / data provenance / gate status / coverage / validation metadata。
