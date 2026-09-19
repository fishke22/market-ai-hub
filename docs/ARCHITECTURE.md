# 系統架構（ARCHITECTURE）

MARKET_AI_HUB 的定位不是聊天機器人，而是**本機金融研究 MCP Server**。

它負責：

- 抓取與整理市場資料
- 做時區 / 交易日曆 / 新鮮度檢查
- 執行模型
- 執行研究型驗證
- 把結果整理成結構化 MCP tool output

真正的自然語言回答由外部 AI Client / Agent 負責。

因此 Cherry Studio 只是其中一個 Host 範例；任何支援本機 stdio MCP 的 Client 都可以接入。

---

## 1. 資料流

```text
資料來源
TWSE / FinMind / FRED / yfinance
        │
        ▼
Data Layer
清理 / 時區 / trading calendar / freshness / features
        │
        ▼
Independent Base Models
Chronos-2 / TimesFM 3 / XGBoost / LightGBM
        │
        ▼
Ensemble Layer
price_ensemble + direction_ensemble
        │
        ▼
Analysis Wrapper
analyze_osaka_nikkei / analyze_taiwan_stock
        │
        ▼
MCP Server（stdio，13 tools）
        │
        ▼
MCP Client / LLM Host
Cherry Studio 或其他支援 stdio MCP 的 Agent
        │
        ▼
自然語言推理與白話說明
```

---

## 2. 為什麼這樣拆？

讓不同工作放在最適合的地方。

### Python / MARKET_AI_HUB 負責

- 數值計算
- 模型推論
- 資料格式驗證
- 日曆與 horizon 檢查
- walk-forward / validation
- 可重現性
- 回傳結構化結果

### LLM / MCP Client 負責

- 理解使用者問題
- 決定要呼叫哪些 tools
- 比較證據
- 揭露矛盾與限制
- 用白話整理結果

LLM 不應自行「腦補」模型數字。

---

## 3. 三層模型角色（不可混淆）

| 層 | 角色 | 說明 |
|---|---|---|
| Level A | **BASE_MODEL** | 獨立模型：Chronos-2、TimesFM 3、XGBoost、LightGBM（+ optional FinCast） |
| Level B | **ENSEMBLE** | 整合層，**不是**額外一個獨立模型 |
| Level C | **ANALYSIS_WRAPPER** | 分析封裝，**不是**額外一個獨立模型 |

白話說：

```text
Chronos + TimesFM + XGBoost + LightGBM
= 4 個獨立模型

Ensemble
= 把上面結果整合

Analysis Wrapper
= 把資料 + 模型 + Ensemble 整理成一份分析包
```

所以不能寫成「六個模型裡五個看多」。

系統另外維護：

```text
independent_base_model_count
eligible_direction_vote_count
eligible_price_reference_count
```

避免把「存在幾個模型」與「有幾個模型有資格投票」混在一起。

---

## 4. PRICE_FORECAST vs DIRECTION_CLASSIFICATION

這是 V1 最重要的語義分離之一。

### PRICE_FORECAST

| 模型 | 主要輸出 |
|---|---|
| Chronos-2 | forecast path、point forecast、p10/p50/p90 |
| TimesFM 3 | forecast path、point forecast、p10/p50/p90 |
| FinCast（optional） | 價格研究輸出，隔離環境 |

驗證後可看：

- MAE
- RMSE
- MASE
- interval coverage
- calibration

### DIRECTION_CLASSIFICATION

| 模型 | 主要輸出 |
|---|---|
| XGBoost | Up / Flat / Down + class score |
| LightGBM | Up / Flat / Down + class score |

分類模型**不得**偽裝成價格分布模型。

如果：

```text
quantile_type = NOT_AVAILABLE
```

就不能替它顯示真正的 P10 / P50 / P90。

另外目前分類 score 尚未完成正式 probability calibration，所以：

```text
class_up = 0.84
```

不能直接翻譯成：

```text
上漲機率 84%
```

---

## 5. Ensemble 語義

### Price Ensemble

只聚合真正具有價格預測資格的 component。

### Direction Ensemble

處理方向分類結果。

V1 研究狀態：

```text
weighting_method = EQUAL_WEIGHT_RESEARCH
validation_level = RESEARCH
```

意思是：

> 這是研究用集成，不代表已經找出最佳模型權重。

`component_table` 會記錄：

- role
- validation status
- eligibility
- raw weight
- effective weight
- excluded reason

未通過資格的模型不得偷偷進正常權重。

---

## 6. V1 correctness rules

### Horizon

`data_frequency = 1d` 時：

```text
1d = 1 個 future trading bar
2d = 2 個 future trading bars
5d = 5 個 future trading bars
```

日線資料要求 5m / 15m / 30m / 60m：

```text
UNSUPPORTED_WITH_CURRENT_DATA
```

不能用日線假造 intraday bars。

### Calendar

- TWSE：XTAI
- 日本現貨：XTKS

Forecast target 必須全部是**未來 session**。

OSE Holiday Trading 不能被錯誤映射成 `^N225` 現貨 K 棒。

### Timezone

交易日期由交易所當地時間推導：

- Taiwan：Asia/Taipei
- Japan：Asia/Tokyo

禁止直接拿 UTC calendar date 當交易日期。

### Quantile Contract

真正價格預測 quantile 必須：

```text
p10 <= p50 <= p90
```

不符合就標記無效，不進 Ensemble。

---

## 7. Session 與 Freshness 分開

這是 V1.3.1 的重要修正。

### 市場是否正在交易

由：

```text
market_open
tradable_now
session_status
```

表示。

`session_status` 例如：

```text
OPEN
CLOSED
PREOPEN
AFTER_HOURS
HOLIDAY_SESSION
UNKNOWN
```

### 手上的資料新不新

由：

```text
source_timestamp
received_at
quote_age_seconds
freshness_status
quote_live
usable_for_live_decision
```

表示。

`freshness_status` 例如：

```text
LIVE
RECENT
STALE
HISTORICAL
UNKNOWN
```

兩者不能互相覆蓋。

例如：

> 市場可以正在開盤，但你手上的 quote 是昨天的。

這時：

```text
market_open = true
freshness_status = STALE
quote_live = false
```

而不是錯誤地說市場休市。

---

## 8. Forecast Reproducibility

V1 會保存／回傳可重現相關 metadata：

```text
inference_seed
input_data_hash
forecast_config_hash
model_revision
model_build_id
deterministic_mode
forecast_stochastic
sampling_config
```

Chronos / TimesFM 在 V1 Freeze 測試中使用 deterministic path。

這些欄位是為了讓後續：

- 模型排名
- OOS 比較
- Forward Test
- Champion / Challenger

可以公平比較，而不是同一輸入每次得到無法追蹤的結果。

---

## 9. Research Gates

系統刻意區分：

```text
程式有沒有正常執行
```

和：

```text
模型有沒有真的預測能力
```

主要 Gates：

```text
ENGINEERING_GATE
MARKET_DATA_GATE
CALENDAR_GATE
TEMPORAL_ALIGNMENT_GATE
DATA_GATE
MODEL_PREDICTIVE_GATE
TRADING_EDGE_GATE
```

V1 Freeze 最重要的結論：

```text
ENGINEERING_GATE       PASS
MODEL_PREDICTIVE_GATE  UNPROVEN
TRADING_EDGE_GATE      UNPROVEN
```

所以 V1 是一個可靠的**研究底座**，不是「已經證明能賺錢的策略」。

---

## 10. Storage

V1 使用：

```text
DuckDB
Parquet
```

原則：

- raw data append-only
- processed data 可以重建
- provenance / checksum 保留
- market data 不提交 repository

主要本機目錄：

```text
data/
data/raw/
```

GitHub 只保留必要的空目錄 placeholder。

---

## 11. MCP Server

Entry point：

```text
market-ai-mcp
```

Python entry：

```text
market_ai_hub.mcp.server:main_sync
```

Transport：

```text
stdio
```

因此任何支援 local stdio MCP 的 Host 都可以接入，不限定特定聊天軟體。

通用設定：

[`MCP_CLIENT_SETUP.md`](MCP_CLIENT_SETUP.md)

Cherry Studio 設定：

[`CHERRY_STUDIO_SETUP.md`](CHERRY_STUDIO_SETUP.md)

---

## 12. 目錄結構

```text
src/market_ai_hub/
  config/      設定載入
  data/        時間與資料工具
  providers/   TWSE / FinMind / FRED / yfinance / disabled adapters
  features/    feature 計算與 sanitation
  models/      Chronos / TimesFM / baseline ML / FinCast adapter
  ensemble/    Ensemble 邏輯
  backtest/    walk-forward
  storage/     DuckDB / performance store
  services/    calendar / horizon / freshness / reproducibility / validation / build info / analysis
  schemas/     Pydantic schemas
  mcp/         MCP server
```

---

## 13. V1 的邊界

V1 沒有：

- broker login
- live order placement
- true OSE Micro realtime feed
- Tick recorder
- L2 Order Book
- order-flow AI
- execution-aware backtester

如果未來版本加入上述能力，也應以新的 Gate / 文件明確標示，不應回頭改寫 V1 Freeze 當時已驗證的能力。
