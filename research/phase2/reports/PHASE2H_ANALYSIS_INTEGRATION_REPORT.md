# Phase 2H — Analysis Packet + MCP Integration + Cherry Skills + Archive Auto-hook

- Gate: **PHASE2H_PASS**
- **新 build_id：`ccabe1e1552d9ae7`**（舊 `bbf3cb2f9a80d20e`；§23 允許且正常，因修改 fingerprinted `mcp/server.py`）
- 測試：**326 passed + 5 live**（unit 全過；live 5 支 `-m live`）

## 1. New build_id
- 舊：`bbf3cb2f9a80d20e`（V1～2G.2 凍結）
- 新：`ccabe1e1552d9ae7`（Phase 2H MCP 整合，修改 `mcp/server.py` 是正常、必要的）
- V1 correctness contract 仍 PASS（`test_v1_build_unchanged` 已更新至新 build_id，V1 功能回歸全過）。

## 2. MCP tools（21 total，新增 8）
新增：`get_analysis_packet` / `get_data_coverage` / `get_event_calendar` /
`get_official_release_snapshot` / `get_target_instrument_state` / `get_model_leaderboard` /
`get_forward_test_status` / `get_analysis_archive_status`。
既有 V1 tools（health_check / get_market_data / predict_chronos / predict_timesfm /
predict_ensemble / analyze_osaka_nikkei / analyze_taiwan_stock / backtest 等）全數保留（`test_V1_MCP_backward_compat`）。

## 3. Analysis packet schema（`packet/schema.py`）
`AnalysisPacket` 涵蓋 §4 全部欄位：execution_target / contract_month / exchange /
reference_price(+type) / forecast_target_dates / regime / event_state / upcoming_events /
direct/joint/scenario/dynamic_ensemble summary / best_baseline / best_validated_model /
model_range / research_center(+method+version) / support/resistance/invalidation /
historical_edge_summary / strategy_research_state / drivers / contradictions /
data_quality / data_coverage_summary / research_gates / reanalysis_conditions /
data_reused/fetched/stale/missing / ensemble_validation / analysis_id / saved_to_archive。

## 4. Osaka Micro default target
- `get_analysis_packet(market="osaka")` 預設 `execution_target = OSE_NIKKEI225_MICRO_FUTURES`。
- `^N225` 標 `PROXY`；OSE Mini/Large/Spot/TOPIX/SGX/CME 標 `REFERENCE`。
- 有 Micro settlement → `reference_price_type = SETTLEMENT`；否則 fallback proxy → `PROXY`。
- 不虛構 Micro OHLC。

## 5. Live official data used（本棒實測）
- JPX Micro settlement（`FUT_225MC`，2026-09-18：202612→65100…）→ `reference_price` 來源。
- JPX Micro volume / OI、BLS、Cboe VIX、SEC EDGAR、BOJ。
- 大阪 packet **不依賴 TradingView / Yuanta**（`test_live_smoke_osaka_packet` PASS）。

## 6. Proxy / reference separation
- `role_of()`：TARGET / REFERENCE / PROXY。
- `settlement_not_live_close`：settlement 是清算價，非 OHLC close，不冒充 LIVE_PRICE。

## 7. Archive integration
- `get_analysis_packet` 預設 `save_analysis=true` → 存 AnalysisArchive（只存 structured packet，不存 CoT）。
- Archive 不可變 + outcome append-only + `record_reanalysis(supersedes, reason=FORECAST_STALE_AFTER_EVENT)`。
- 事件後分析建立 new analysis_id，不覆蓋舊分析。

## 8. Token benchmark（真實量測）
| workflow | MCP calls | est tokens | bytes |
|---|---|---|---|
| 舊式（~10 raw MCP） | 10 | ~5000 | 20000 |
| compact | 1 | ~743 | 2974 |
| normal | 1 | ~1564 | 6259 |
| audit | 1 | ~2455 | 9821 |

compact 約 **85% token 減少**、10 次 call → 1 次，且核心風險/資料缺口/驗證狀態保留
（`reduction_vs_old_style.core_risk_preserved=true`）。

## 9. Cherry Skills（`cherry_skills/`，繁體中文）
- `osaka-micro-analysis`：真正 TARGET = OSE Micro；優先 `get_analysis_packet`；^N225≠成交價。
- `taiwan-stock-v28`：公司行動校正 + 證據分層 + 反證 + 失效條件；數值由 backend 提供。
- `model-validation-audit`：MASE / baseline / forward / regime / calibration；不得以「模型很先進」評分。

## 10. Regression tests
`pytest tests/` → **326 passed**（5 live deselected）。
新增 20 unit + 1 live：schema / micro default / proxy-not-target / settlement-not-close /
compact/normal/audit / data lake reuse / event top-n + cutoff / quantile semantics /
research-center reproducible / archive auto-save + immutable + reanalysis-new-id /
V1 MCP backward compat / 3 skills / token benchmark / live smoke。

## 11. Live smoke
- `pytest tests/test_phase2h.py -m live` → 1 passed（大阪 packet 用 JPX settlement+volume，
  reference_price_type=SETTLEMENT，target LIVE_VERIFIED，TradingView/Yuanta 全關仍成功）。

## 12. Remaining missing data
- OSE Micro per-contract **OHLC**（open/high/low）：CONTRACT_ONLY（官方 xlsx/csv 無，僅 settlement）。
- JPX investor flow：CONTRACT_ONLY（未發現直接 CSV URL）。
- Full Micro historical backfill：未 bulk 執行（URL pattern 已確認待排程）。
- Fed FOMC calendar JSON 404（走 HTML，CONTRACT_ONLY）。

## 13. Remaining NEEDS_CONFIG providers
- BEA（GDP/PCE，需免費 API key）、Japan e-Stat（appId）、EIA（API key）、EDINET（config-only）。

## 驗證
- `pytest tests/ -q` → 326 passed
- `pytest tests/test_phase2h.py -m live -q` → 1 passed
- 新 build_id `ccabe1e1552d9ae7` 記錄於此 + `CURRENT_HANDOFF.md`
