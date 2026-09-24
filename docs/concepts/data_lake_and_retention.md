# Data Lake 與資料保留政策

## 目錄結構
`data/`（canonical env 為 `MARKET_AI_DATA_ROOT`；舊 `MARKET_AI_HUB_DATA_ROOT` 僅保留 migration fallback。可搬移到其他磁碟，未來 Yuanta L2/Tick 可外移）：

```
data/
  raw/          原始 official market observations
  normalized/   正規化資料
  features/     特徵快照（feature_store）
  predictions/  Prediction Registry 備份
  analysis_archive/  分析與結算（DuckDB）
  cache/        HTTP 暫存（可 TTL 清理）
  manifests/    資料 manifest + scheduler 狀態
```

## Manifest
`DataManifest`（pydantic）紀錄：provider / dataset / instrument / frequency / start / end /
row_count / source / source_hash / downloaded_at / available_at / schema_version。

- `DataLakeManager.save_manifest()` / `load_manifest()` / `coverage()`

## 增量下載
`automation/incremental.py`：
- `missing_ranges(covered, requested)` → 只補缺漏日期區段
- `dedupe()` → 依 key_cols 去重（保留最後）
- `atomic_write()` → temp + rename（避免半寫入）
- `dedupe_and_write()` → 內容 hash 不變則不重寫

## 保留政策（`config/data_retention.yaml`）
| 類別 | 政策 |
|---|---|
| historical market observations | KEEP_FOREVER |
| prediction registry | KEEP_FOREVER |
| analysis archive | KEEP_FOREVER |
| training metadata | KEEP_FOREVER |
| HTTP temporary cache | TTL 7 天 |
| derived rebuildable cache | TTL 30 天 |

**不得自動刪除**：raw official historical data / prediction history / analysis history。
