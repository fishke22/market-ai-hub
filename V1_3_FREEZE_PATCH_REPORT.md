# V1_3_FREEZE_PATCH_REPORT.md

日期：2026-09-19
範圍：`D:\MARKET_AI_HUB`（V1.3 FREEZE PATCH）
Gate：**READY_FOR_V1_FREEZE**

本輪只做兩件事，未新增模型 / 交易功能 / 未重構架構。

---

## A. Forecast Reproducibility

### 實作
- 新增 `services/reproducibility.py`：
  - `input_hash(series)`：輸入序列 float32 內容 sha256（跨平台穩定）
  - `forecast_config_hash(model_id, horizon, steps, quantiles, seed, freq)`：config sha256
  - `model_revision_local(model_id, cache_dir)`：從 HF 本地 cache `snapshots/<sha>` 讀 commit（離線）
  - `model_revision_remote(model_id)`：HF API 查 commit（需網路，失敗回 "unknown"）
  - `sampling_metadata(deterministic, method, n_samples)`
- `ForecastOutput` 新增欄位：`inference_seed` / `input_data_hash` / `forecast_config_hash` /
  `model_revision` / `model_build_id` / `deterministic_mode` / `forecast_stochastic` / `sampling_config`。
- Chronos-2 與 TimesFM-3 的 forecast builder 皆注入上述欄位（`seed` 預設 42）。

### 模型本質（以實測為準，非宣稱）
- **Chronos-2**：deterministic quantile 模型（無 MC sampling）→ `deterministic_mode=true`、
  `forecast_stochastic=false`、`sampling_config={"method":"none","deterministic_quantiles":true,"n_samples":null}`。
- **TimesFM-3.0**：同上，deterministic。
- 實測：兩模型在 CUDA 上連續 3 次輸出 **bit-identical**（`p50` 序列全等）。

### Reproducibility 保證
同一「模型版本 + input_data_hash + horizon + forecast_config + seed」→ 相同 forecast。
若未來接入本質使用 MC sampling 的模型：`deterministic_mode=false`、`forecast_stochastic=true`
（STOCHASTIC_FORECAST），保留 sample count 與 seed，不得拿不同抽樣結果直接比較模型優劣
（`sampling_metadata` 已備好此路徑）。

### 測試
- `tests/test_reproducibility.py`：hash 穩定/敏感、config hash 隨 seed/horizon 變、revision 從 cache 讀、
  sampling metadata、fake adapter 10x 一致 + metadata 存在。
- `tests/test_reproducibility_smoke.py`（integration）：**真實 Chronos-2 / TimesFM-3 各 10 次**，
  `point_forecast` / `forecast_path` / `input_data_hash` / `forecast_config_hash` 全部 bit-identical。

## B. Market Open / Quote Freshness

### 實作
- 新增 `services/market_session.py`：
  - `asset_class(symbol)`：fx / crypto / index / equity / proxy
  - `session_status(symbol, as_of)`：依資產類別判斷（非 timestamp 新舊）
    - fx（USDJPY）：週六/週日休市（UTC，文件化簡化）
    - crypto（BTC）：24/7 open
    - index/equity（^N225/台股）：exchange_calendars（XTKS/XTAI）session 日
    - proxy（期貨 proxy）：`unknown`（保守，不宣稱 live）
  - `quote_freshness(symbol, source_timestamp, received_at)`：
    - `source_timestamp` 與 `received_at` **分離**
    - `quote_age_seconds = received_at - source_timestamp`
    - `freshness_status ∈ {fresh, stale, unknown}`（門檻依資產類別：fx 1h / crypto 15min / 日線 24h）
    - **stale 不得標 live**：freshness=stale → market_open/tradable_now=false、session_status=stale
- `ForecastOutput` 新增：`market_open` / `tradable_now` / `source_timestamp` / `received_at` /
  `quote_age_seconds` / `freshness_status` / `session_status`；Chronos/TimesFM forecast 皆注入。

### 測試（`tests/test_market_session.py`）
- 週六 USDJPY → closed（即使資料供應商回傳較新 timestamp）
- 週六 BTC → open（24/7）
- stale quote 不得標 live（source 3 天前 → freshness=stale → market_open=false）
- source_timestamp 與 received_at 分離（欄位獨立、age 精算）
- 週一 USDJPY open、TSE 週六 closed、proxy=unknown

## 驗證結果

```
python -m pytest tests -q        → 154 passed（121 unit + 19 integration/其他 + 14 integration）
python tests/smoke_mcp.py        → MCP SMOKE: PASS（13 tools）
build_id                          → e66008537830c0ad
```

Live MCP 檢查（predict_chronos ^N225 / 3706.TW）：
- 14 個 repro/freshness 欄位全數存在
- `inference_seed=42`、`deterministic_mode=true`、`model_revision=29ec3766...`（chronos 真實 commit）
- 週六（2026-09-19）→ `session_status=stale`、`market_open=false`、`freshness_status=stale`（正確：休市 + 日線資料 >24h）

## Unresolved issues（誠實列出）

1. FX session 為簡化模型（週六/週日全天休市，未含週五 22:00Z 收盤 / 週日 22:00Z 開盤的精確邊界）。
2. 期貨 proxy（NQ=F 等）session=unknown（保守，不宣稱 live）。
3. `model_revision` 離線時可能為 "unknown"（本地 cache 無 snapshots 目錄時）。
4. 日線資料的 quote 在非交易時段必然 >24h → 標 stale（符合預期；這是研究代理，非即時行情）。

## Gate

**READY_FOR_V1_FREEZE**

（使用者唯一動作：Cherry Studio 重啟 market-ai MCP process，以 `health_check.build.build_id == e66008537830c0ad` 驗證載入 V1.3。）
