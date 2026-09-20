# Feature Store（特徵倉儲）

Phase 2C 的 **versioned Feature Store**：統一存放 cross-asset 特徵，每個特徵帶
`event_time` / `available_at` / `feature_version` / `source` / `data_grade`。

## 大阪日經 Panel（16 個符號）

```
^N225  TOPIX(^TPX)  CME Nikkei(NKD=F)  NQ  ES  SOX  VIX
USDJPY  DXY(DX-Y.NYB)  US2Y  US5Y  US10Y  US30Y  Gold(GC=F)  WTI(CL=F)  BTC
```

| 類別 | 符號 | 來源 | data_grade |
|------|------|------|-----------|
| 指數/期貨/外匯/加密 | 大部分 | yfinance | RESEARCH_PROXY |
| 美債殖利率 | US2Y/5Y/10Y/30Y | U.S. Treasury | OFFICIAL_DAILY |

> 注意：^N225 是現貨指數 proxy；NKD=F 是 **CME** 日經期貨（非 OSE）；DXY 為 best-effort proxy。

## 事件排程特徵（event schedule features）

| feature | 來源 | data_grade | 說明 |
|---------|------|-----------|------|
| boj_schedule | schedule | SCHEDULE | 日銀金融政策決定會合 |
| fomc_schedule | schedule | SCHEDULE | FOMC 會議 |
| cpi / nfp | schedule | SCHEDULE | CPI / 非農公布 |
| holiday | exchange_calendars | OFFICIAL | 交易所休市日 |
| ose_holiday_session | none | UNAVAILABLE | OSE Holiday Trading（無免費來源） |
| contract_expiry | schedule | SCHEDULE | 期貨契約到期日 |

## FeatureRecord 欄位

`feature_name` / `symbol` / `event_time` / `available_at` / `feature_version` /
`source` / `data_grade` / `value`。

- `available_at`：特徵值成為「已知」的時間（日終可用 = event_time；延遲來源 = event_time + delay）。
- 儲存統一為 **naive UTC**（DuckDB TIMESTAMP 不帶 tz，避免 round-trip 時區偏移）。

## No look-ahead

- `build_panel_features(..., as_of)`：只產生 `available_at <= as_of` 的特徵。
- `FeatureStore.get(..., as_of)`：查詢時再過濾一次 `available_at <= as_of`。
- 未來資料一律不進模型。

## 儲存

- DuckDB：`data/feature_store/features.duckdb`（版本化，`feature_version` 欄位）。
- `versions()` 列出所有 feature_version；`get(...)` 可依版本查詢。

## 使用

```python
from market_ai_hub.feature_store.store import FeatureStore, build_panel_features
from market_ai_hub.feature_store.panel import PANEL, EVENT_SCHEDULE_FEATURES

store = FeatureStore()
for r in build_panel_features({"^N225": closes}, as_of=as_of):
    store.put(r)
df = store.get("^N225", "close", as_of=as_of, feature_version="v1")  # no look-ahead
```

## 注意

- 本模組為 Phase 2C 新增，不改動 V1 核心（build_id 維持 `bbf3cb2f9a80d20e`）。
- `data/feature_store/` 在 `.gitignore` 排除（研究產物，不入 repository）。
