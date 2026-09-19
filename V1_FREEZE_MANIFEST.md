# V1 FREEZE MANIFEST

- **Freeze date**：2026-09-19
- **Freeze build_id**：`4742a33e5b17d1d0`
- **market_ai_version**：1.1.0（schema_version 1.1）
- **Freeze tag**：`v1-freeze-2026-09-19`

## 測試

| 項目 | 結果 |
|------|------|
| pytest（全部） | 154 passed |
| MCP smoke | PASS |
| MCP tools | 13 |

## 環境

| 項目 | 值 |
|------|-----|
| OS | Windows 11 (10.0.26200) x64 |
| Python | 3.12.13 |
| Torch | 2.14.0+cu130 |
| CUDA（torch） | 13.0（可用） |
| GPU | NVIDIA GeForce RTX 4060 Ti 16GB |
| GPU driver | 616.56 |

## MCP tools

`health_check`, `get_system_info`, `get_data_source_status`, `get_market_data`,
`predict_chronos`, `predict_timesfm`, `predict_ensemble`, `get_model_performance`,
`backtest`, `analyze_osaka_nikkei`, `analyze_taiwan_stock`,
`get_research_gates`, `run_ts_validation`

## 模型 revisions

| 模型 | model_id | revision | license |
|------|----------|----------|---------|
| Chronos-2 | amazon/chronos-2 | `29ec3766d36d6f73f0696f85560a422f50e8498c` | Apache-2.0 |
| TimesFM-3.0 | google/timesfm-3.0-pytorch | `43046b85ec22d584a13f8098c2ed39c889e129c2` | 非商業（research only） |
| FinCast（可選） | Vincent05R/FinCast | `2d7d90b159db8961d27c2cf165d51195902ef92b` | Apache-2.0（repo）/ research |

## 關鍵 correctness rules（V1 已凍結）

1. **Horizon**：`data_frequency="1d"` 時 `Nd` = N 根 trading bars；日線資料 + 日內 horizon → UNSUPPORTED。
2. **Calendar**：TWSE=XTAI、TSE=XTKS（exchange_calendars）；forecast targets 全為未來 sessions。
3. **Timezone**：trading_date 由交易所時區推導（Asia/Taipei、Asia/Tokyo），禁用 UTC date。
4. **Quantile Contract**：`p10 <= p50 <= p90`，否則標 NOT_AVAILABLE；分類器無 predictive quantile。
5. **Calibration**：分類器 probability 未校準（`probability_calibrated=false`）。
6. **Session/Freshness 分離**：`market_open`/`tradable_now`/`session_status` 與
   `freshness_status`/`quote_live`/`usable_for_live_decision` 各自獨立。
7. **Reproducibility**：`input_data_hash` + `forecast_config_hash` + `seed` + `model_revision`；
   Chronos/TimesFM 為 deterministic_mode=true（10x 一致）。

## Known limitations

- 大阪日經為 ^N225 INDEX proxy（非 OSE 微型期貨即時）。
- `MODEL_PREDICTIVE_GATE` / `TRADING_EDGE_GATE` = **UNPROVEN**。
- 分類器 probability 未 calibration；TS 模型 predictive_validation_status = UNVALIDATED。
- FinMind / FRED 需自備免費 token。

## ⚠️ 重要語義

**V1 Freeze = 工程與正確性已凍結。**
**不得解讀為「模型已證明能賺錢」。**
`MODEL_PREDICTIVE_GATE` 與 `TRADING_EDGE_GATE` 仍可能是 UNPROVEN，這是誠實的現狀。
