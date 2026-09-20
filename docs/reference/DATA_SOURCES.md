# 資料來源（DATA SOURCES）

Phase 2B 擴充的免費資料來源總表。所有來源透過統一 `DataProviderContract`
（`src/market_ai_hub/providers/contract.py`）記錄來源品質。

## 統一契約（DataProviderContract）

每筆資料記錄：`source_name` / `authority` / `market` / `instrument` /
`event_time` / `source_timestamp` / `received_at` / `available_at` /
`freshness` / `frequency` / `data_grade` / `license` / `delay_status` /
`target_match` / `information_cutoff_compatible`。

- `available_at` = `source_timestamp` + 已知延遲（供 no-look-ahead）。
- `information_cutoff_compatible`：來源是否提供可信的 available_at（官方來源皆 true）。

## 來源總表

| 來源 | authority | 免費/限制 | 用途 | 時效 | 授權/注意 |
|------|-----------|-----------|------|------|-----------|
| **TWSE** OpenAPI | 台灣證交所 | 免費 | 台股上市日線 | 日線（收盤後） | TWSE 公開資料 |
| **FinMind** | FinMind | Free tier；部分 dataset 需 Backer/Sponsor | 台股/法人/財報 | 日線 | FinMind 條款；付費 tier 回 DATA_REQUIRES_PAID_TIER |
| **FRED** | St. Louis Fed | 免費（需免費 key） | 美債/聯邦基金利率等總經 | 日線（非高頻即時） | 美國政府公開資料 |
| **yfinance** | Yahoo（unofficial） | 免費（個人研究） | 全球代理行情 | BEST_EFFORT / DELAYED_POSSIBLE | unofficial wrapper，**非交易所級** |
| **TAIFEX** | 台灣期交所 | 免費 | 期貨日資料 + 近 30 日 Time & Sales | 日資料（收盤後）；T&S 近 30 日 | TAIFEX 公開資料 |
| **BOJ Time-Series** | 日本銀行 | 免費 | 日本總經時序列 | 日/月 | BOJ 公開資料 |
| **U.S. Treasury** | 美國財政部 | 免費 | 2Y/5Y/10Y/30Y 殖利率 | 每日 | 美國政府公開資料 |
| **CFTC COT** | CFTC | 免費 | 期貨持倉（Commitments of Traders） | 每週（有延遲） | 美國政府公開資料 |
| **J-Quants Free** | JPX | Free plan（JPY 0） | 日本市場（延遲） | **~12 週延遲**；Futures OHLC 需 Premium | J-Quants 條款；**不得當 OSE 即時期貨來源** |

## 來源品質（不誤標）

- **J-Quants Free**：`delay_status=FREE_PLAN_LIMITED`、`data_grade=OFFICIAL_DELAYED`。
  不是 OSE 即時期貨來源。
- **Yahoo/yfinance**：`data_grade=RESEARCH_PROXY`、`delay_status=BEST_EFFORT`。
  不是交易所級資料。
- **TAIFEX / TWSE / U.S. Treasury / BOJ / CFTC**：官方公開資料（OFFICIAL_DAILY / OFFICIAL_DELAYED）。

## Cache / Rate limit / Retry

所有新來源使用共用 `RateLimitedClient`（`providers/http_client.py`）：

- 合理 cache（TTL），避免重複呼叫。
- retry + exponential backoff（上限 `max_retries`、`max_backoff`），**不得無限制重試**。
- 失敗拋 `ProviderError`，由 provider 做 graceful degradation。

## 已保留

- TWSE、FRED、yfinance fallback（既有 V1 provider 不變）。
- FinMind 仍只使用真正 Free tier。

## 設定

需要自備免費 key 的來源（未設定 → `needs_config`，系統仍可用其他來源）：

- `FINMIND_TOKEN`（FinMind）
- `FRED_API_KEY`（FRED）
- `JQUANTS_API_KEY`（J-Quants Free，格式 `mail:password`）

詳見 `.env.example`。絕不硬編碼 token。
