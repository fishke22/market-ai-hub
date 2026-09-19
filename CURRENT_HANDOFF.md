# MARKET_AI_HUB — CURRENT HANDOFF

## Published baseline

- Public phase: **V1 Freeze — published**
- Freeze tag: `v1-freeze-2026-09-19`
- Publication gate: `PUBLICATION_COMPLETE`
- Published build_id: `bbf3cb2f9a80d20e`
- Freeze date: 2026-09-19

> 這份 handoff 描述的是目前公開 V1 基線。Phase 2 正在另外施工中；尚未驗收的 Phase 2 功能不要視為 V1 已有能力。

---

## V1 已完成什麼

### 工程底座

- Python 3.12 / Windows x64
- DuckDB + Parquet
- stdio MCP Server
- 13 MCP tools
- clean-clone restore 驗證
- reproducible build / build_id
- lightweight CI

### 模型

- Chronos-2
- TimesFM 3
- XGBoost
- LightGBM
- FinCast（optional / isolated）

### 正確性保護

- PRICE_FORECAST 與 DIRECTION_CLASSIFICATION 分離
- Base Model / Ensemble / Analysis Wrapper 不重複計票
- quantile contract
- 未校準分類分數不得當真實機率
- Horizon / forecast_target_dates 驗證
- Exchange Calendar / trading_date 語義
- OSE Holiday Trading 與 ^N225 calendar 分離
- Session 與 Quote Freshness 分離
- Forecast reproducibility metadata
- Research Gates

---

## V1 驗證結果

- 本機完整 pytest：**154 passed**
- Clean clone 輕量測試：**134 passed**
- MCP smoke：**PASS（13 tools）**
- Clean restore：**PASS**
- Security scan：**CLEAN**

詳細發布證據：

[`GITHUB_PUBLICATION_REPORT.md`](GITHUB_PUBLICATION_REPORT.md)

---

## Research Gate 狀態

```text
ENGINEERING_GATE       PASS
MODEL_PREDICTIVE_GATE  UNPROVEN
TRADING_EDGE_GATE      UNPROVEN
```

這代表：

- 工程基線已可重建、可執行。
- 目前仍不能宣稱模型已證明能穩定勝過簡單 baseline。
- 目前仍不能宣稱存在已驗證交易優勢。

---

## V1 重要限制

1. 大阪日經目前主要使用 `^N225` 研究代理資料，不是 OSE Micro 即時行情。
2. Chronos / TimesFM 的市場預測能力仍屬 `UNVALIDATED / UNPROVEN`。
3. 分類器 probability 尚未正式 calibration。
4. 日線資料不能冒充 5m / 15m / 30m / 60m 真實日內資料。
5. V1 沒有 broker login、下單、Tick、L2 Order Book 或 order-flow AI。
6. FX session 邊界仍是簡化實作；某些期貨 proxy session 仍可能是 `UNKNOWN`。

---

## MCP 定位

MARKET_AI_HUB 是：

**Client-neutral stdio MCP Server**

不是：

**Cherry Studio 專用外掛**

Cherry Studio 是已驗證的一個 Client 範例；其他支援 local stdio MCP 的 Host / Agent 也可以使用。

通用設定：

[`docs/MCP_CLIENT_SETUP.md`](docs/MCP_CLIENT_SETUP.md)

---

## 下一階段

Phase 2 可以在 V1 Freeze 之上擴充，但不要回頭把未驗收能力寫進 V1 基線。

任何 Phase 2 合併前應重新：

1. 更新 build / schema version。
2. 跑完整 tests。
3. 更新 Research Gates。
4. 更新 MCP tool contract。
5. 更新 README / Architecture / Data Source Matrix。
6. 明確列出新增能力與仍未證明的能力。
