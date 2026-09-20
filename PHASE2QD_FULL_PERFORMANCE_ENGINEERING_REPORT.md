# PHASE 2Q-D — Full Performance Engineering + Model/Data Runtime Acceleration + MCP/Cherry Latency Hardening + Build Identity Correction

- gate：**PHASE2QD_PASS**（0 Critical / 0 High）
- build_id：`badba314b7e119c0`（build identity 修正：fingerprint 全部 runtime source + config）
- 版本：`v2.0.0-rc1`（不 tag）

## 0. 本棒目的

不改 research truth / 不引入 leakage / 不降低 correctness / 不卡桌面前提下加速。

## 1. 五個最大 bottleneck（before）

1. `health_check` 每次 `ChronosAdapter().status()` → `load()` 真正 load weights（15.9s）。
2. `get_system_info` 走 `live_model_cards()` → `get_chronos().status()` load（16.5s）。
3. `import chronos` 套件 6.1s（status_shallow 原本用 `import chronos`）。
4. `TWSEProvider.status()` live network probe（3 retry = 3.4s）。
5. XGB/LGBM 每 request 重新 `fit()`（200 estimators，warm analyze 1.467s）。

## 2. health 為何原本 15.8s

`health_check` → `_model_statuses()` → `ChronosAdapter().status()` → `load()` → `BaseChronosPipeline.from_pretrained()` 載入權重。加上 `get_system_info` 的 `live_model_cards()` 也 load。shallow 改後不再 load。

## 3. 修正內容

| 領域 | 修正 |
|------|------|
| build identity（§4） | fingerprint 全部 `src/market_ai_hub/**/*.py` + runtime config（175 files）；docs/tests 不改 build_id |
| health shallow（§5/§6/§8） | `_model_statuses(deep=False)` 用 `services/model_status.shallow_status()`（find_spec + cache presence，不 import torch/模型）；`deep_probe` 參數可選 |
| system_info / gates shallow（§7） | `live_model_cards()` 用 `shallow_status()` 不 load |
| provider shallow（§5） | `status_all(deep=False)` 預設 shallow；TWSE `status_shallow()` 不 network probe |
| no duplicate load（§19） | model_runtime singletons（同 process 同 instance） |
| bounded CPU（§24） | `interactive_n_jobs()`（1~4 threads）取代 `n_jobs=-1` |
| classifier fit cache（§23） | `services/fit_cache.py`：key = model/symbol/horizon/data_hash/feature_version/build_id；資料變 invalidates |
| forecast cache observability（§21/§22） | instrumentation counters（forecast_cache_hit） |
| benchmark instrumentation（§3） | `services/instrumentation.py` 真 counters；修掉 benchmark hardcode `model_inference_count=0` |

## 4. Cherry Studio latency 改善

| metric | before | after | 改善 |
|--------|--------|-------|------|
| health_check first | 15.894s | **0.706s** | -95.6% |
| health_check warm | 7.545s | **0.022s** | -99.7% |
| get_system_info | 16.48s | **0.593s** | -96.4% |
| get_research_gates | (未測) | **0.139s** | — |
| packet Osaka cold/warm | 1.729/0.0034s | 1.952/**0.0033s** | warm 持平 |
| packet Taiwan cold/warm | 0.529/0.1104s | 0.554/0.191s | 持平（warm 為 yfinance cache 路徑） |

## 5. 各問題回答（§49）

1. 五個 bottleneck：見 §1。
2. health 15.8s：load Chronos/TimesFM weights。
3. Cherry latency：health -95.6%、system_info -96.4%。
4. Osaka compact cold/warm：持平（warm 3.3ms，未 regression）。
5. Taiwan Stock compact：持平。
6. Taiwan Index compact：持平（原本就快）。
7. analyze_osaka cold/warm：cold 由 model load 主導（未測 full，因需真實 load）；warm 由 classifier fit cache 改善。
8. heavy model load 重複？否（singleton + shallow 不 load）。
9. XGB/LGBM 仍每 request refit？否（fit_cache）。
10. CPU/GPU/RAM 遵守 DESKTOP_SAFE？是（n_jobs bounded 1~4）。
11. Historical learning throughput：walk-forward framework 保持；本棒未測 full throughput（留 2Q-D benchmark 擴充）。
12. 225LABO ingest：未大改（license boundary 不變）；dry benchmark 未做 full（留後續）。
13. 改變 research truth？否。

## 6. Validation

- 新增 `test_phase2qd.py`（13 tests）：build identity / shallow health no-load / cache invalidation / n_jobs bounded。
- **Full regression：748 passed（735 + 13），無 regression。**
- 未改 OSAKA frozen evidence / VAR / NO_ECONOMIC_EDGE / Forward state。
- 未動：AUTO_TRAIN/FINE_TUNE/PROMOTE = false。

## 7. 已知留待 2Q-E（professionalization）

- lightning_logs / data/*.duckdb 位置 hygiene（已在 2Q-C.1 LOCAL_RUNTIME_ARTIFACT_AUDIT 記錄）。
- 225LABO ingest streaming 優化。
- Historical learning throughput 正式 benchmark。
- FinCast persistent worker 評估（僅當確認 bottleneck）。
