# PHASE 2Q-C.2 — Target-Family Runtime Isolation + Taiwan Packet Correctness + Historical OOS Metric Correctness

- gate：**PHASE2QC2_PASS**（0 Critical / 0 High）
- build_id：`1afb6888eec3fbdc`（未變；本棒只改非 fingerprinted files）
- 版本：`v2.0.0-rc1`（不 tag）

## 0. Confirmed HIGH Defect

`build_analysis_packet(market="taiwan", target="3706.TW")` 錯誤回傳 OSE Micro settlement（65310 / 202703 / SETTLEMENT / LIVE_VERIFIED）→ **CROSS_MARKET_DATA_CONTAMINATION**。

**Root cause**：reference routing 用二分法（taiwan_index vs else-osaka），taiwan/taiwan_stock 錯誤走 `_load_latest_micro_settlement()`。

## Fix

### 1. Target-family resolution（§1/§2）

`services/primary_targets.py.resolve_market_family()`：正式辨識 OSAKA_MICRO / TAIWAN_STOCK / TAIWAN_INDEX；未知 market **fail clearly**（不默認 Osaka）。

### 2. Reference routing（§3/§4/§5/§6）

| family | reference route |
|--------|-----------------|
| OSAKA_MICRO | `_load_latest_micro_settlement()` → ^N225 proxy fallback |
| TAIWAN_STOCK | `_taiwan_stock_reference(symbol)`：FinMind → TWSE → yfinance（只回該股票本身） |
| TAIWAN_INDEX | `_index_proxy_reference()`（^TWII，PROXY / DIRECT_NOT_IMPLEMENTED） |

### 3. Market-specific context / coverage / archive（§7/§8/§9/§10）

- `_regime_panel(family)`：local context 分離（Osaka→^N225，Taiwan→^TWII），global（VIX/US rates/USDJPY）共通。
- `_coverage_summary(family)` / `_coverage_summary_compact(family)`：family 隔離。
- `_archive_packet(packet, family)`：market_name（osaka/taiwan_stock/taiwan_index）+ dataset/feature semantic（Taiwan = UNVERSIONED，不假裝 jpx-micro-v1）。

### 4. MASE defect（§14–§19）

`HistoricalWalkForwardProtocol.score()` 修正：
- 每 fold MASE denominator 只用該 fold **TRAINING** naive in-sample scale（`naive_scale(train, m=1)`）。
- 不得跨 fold diff、不得讓 future test 進 scale。
- 新增 `baseline_scores()`（LAST_VALUE / ZERO_RETURN / SEASONAL_NAIVE / DRIFT 同 origin 比較）。
- fold-level metrics：n_train / n_test / mae / rmse / mase / mase_scale（auditability）。

### 5. yfinance timezone（§21）

`yfinance_provider.py` naive timestamp 之前：`timestamp_utc = ts.tz_localize("UTC")`（與 `timestamp_local = ts.tz_localize(local_tz)` 同一 naive 兩套解讀）。
修正：先 localize 到 instrument local tz，再 convert UTC（`utc_ts = local_ts.tz_convert("UTC")`）。

## Validation（§24）

MCP E2E（真實 get_analysis_packet stdio）：

| market | reference_price | price_type | source | contract |
|--------|-----------------|-----------|--------|----------|
| taiwan 3706.TW | 80.5 | PROXY | yfinance | (empty) |
| taiwan_index TAIEX | 47368 | PROXY | proxy_index | (empty) |
| osaka | 65310 | SETTLEMENT | settlement | 202703 |

無 cross-market contamination。

## Tests（§12/§13/§19）

新增 `test_phase2qc2.py`（22 tests）：contamination matrix（12）、negative sentinel、metric leakage（7）、timezone regression、family resolution。

**Full regression：765 passed（743→765，+22，無 regression）。**

## 禁區未動

不 performance optimization / 不新模型 / 不 training / 不 broker / 不 mega-restructure。
OSAKA frozen evidence / VAR / NO_ECONOMIC_EDGE / Forward state 未改。
