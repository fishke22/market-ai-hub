# Phase 2I-A — Performance + Accuracy Hardening

- Gate: **PHASE2IA_PASS**
- build_id：`ccabe1e1552d9ae7`（未變；本棒未改 fingerprinted 檔）
- 測試：**342 passed**（326 + 16 2I-A；5 live deselected）

## Before benchmark（`PERFORMANCE_BASELINE.json`）
| run | total latency | response bytes | est tokens |
|---|---|---|---|
| osaka/compact | 4.63s（首次冷啟動） | 2894 | 723 |
| osaka/normal | 1.44s | 6376 | 1594 |
| osaka/audit | 1.34s | 9938 | 2484 |
| taiwan/normal | 1.36s | 6357 | 1589 |

## After benchmark（`PERFORMANCE_AFTER.json`）
| run | cold latency | warm latency（cache） |
|---|---|---|
| osaka/compact | 3.80s | **0.004s** |
| osaka/normal | 1.25s | 0.005s |
| osaka/audit | 1.22s | 0.004s |
| taiwan/normal | 1.22s | 0.004s |

**核心改善**：重複分析（同 process）由 ~1.3s → ~0.004s（**~325x**）。
cold 由 ~1.4s → ~1.2s（移除 2 個 yfinance 404 symbol、減 regime panel fetch）。

## 改善項目
| 項 | 內容 |
|---|---|
| Data fetch | 進程級 TTL cache + request dedup（同 symbol/range 只抓一次）；修掉 US10Y/US2Y 404（改 ^TNX/^FVX） |
| Shared context | `AnalysisExecutionContext`（共用 panel / cutoff / feature snapshot，不重算） |
| Feature incremental | 只補 missing range（`missing_ranges`）；內容 hash 不變不重寫 |
| Model loading | `ModelRuntimeManager`：lazy load + reuse + VRAM 預算守衛（16GB 不無限制常駐）+ OOM graceful fallback |
| DuckDB/Parquet | 已有 projection/filter；Archive 讀取加入進程級 cache（settlement 只讀一次） |
| Packet lazy compute | compact 只建 5 項 coverage（非 28 全表）、event top-N=3、不先建 audit 再刪欄位 |
| Accuracy | `DataConsistencyValidator`（ordering/dup/price<=0/jump/frozen/tz）、`cross_source_check`（DATA_CONFLICT）、settlement≠close 語義 |
| Failure isolation | provider 失敗 → degrade（標 missing/error），不整份分析失敗 |

## 找到的 bottleneck / 修正
1. **yfinance regime panel 每 build 重抓 5 symbols（2 個 404）** → TTL cache + 換可用 symbol。**修正**。
2. **`ModelRuntimeManager` 用 `threading.Lock` 導致 `get()` 內呼叫 `current_vram_mb()` 死鎖**（測試抓到 hang）→ 改 `RLock`。**修正**。
3. **packet compact 先建完整 audit 再刪欄位** → lazy compute（compact 直接建精簡版）。**修正**。
4. **provider 失敗未隔離**（`_regime_panel` 例外會讓整份 packet 崩）→ try/except degrade。**修正**。

## 未修正原因（誠實揭露）
- **HTTP request count 量測不到**：yfinance 內部用 `requests` 但繞過我 patch 的 `Session.request`
  （其內部快取/連線在 patch 前已建立），故 benchmark `http_calls=0` 是低報。真實約 cold ~3-5 次。
  已記錄為 instrumentation gap，不影響 latency/RAM/VRAM 量測。
- **cold latency 仍由網路主導**（yfinance ~1.2s）：本地無官方跨資產 proxy 來源，無法完全消除；
  未來以 Data Lake 常駐官方資料取代 proxy fetch。

## Accuracy / correctness hardening（不因速度退步）
- DataConsistencyValidator：ordering / duplicate bars / price<=0 / abnormal jump / frozen target / tz mismatch。
- cross_source_check：Nikkei/USDJPY/VIX/Treasury 多來源差異超門檻 → DATA_CONFLICT，不默默選一個。
- settlement 語義：settlement≠live close；OSE Micro 只標 SETTLEMENT。
- target/proxy 分離：^N225=PROXY 維持。
- optimization output equivalence：cold/warm 核心語義欄位完全一致（`test_optimization_output_equivalence`）。

## Tests（16 新增）
request_dedup / datalake_cache_reuse / shared_execution_context / feature_incremental_update /
model_lazy_load / model_reuse / gpu_memory_guard / duckdb_filtered_read / data_conflict_detection /
stale_cache_rejection / settlement_semantics / target_proxy_separation / packet_compact_lazy_compute /
failure_isolation / optimization_output_equivalence / consistency_validator。

## 驗證
- `pytest tests/ -q` → 342 passed
- `scripts/benchmark_packet.py --out PERFORMANCE_AFTER.json` → 冷/暖量測完成
- build_id 維持 `ccabe1e1552d9ae7`
