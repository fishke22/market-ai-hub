# MARKET_AI_HUB

**把市場資料、預測模型與驗證工具封裝成 MCP tools 的本機金融研究服務。**

白話說：你可以把 MARKET_AI_HUB 接到任何**支援本機 stdio MCP** 的 AI Client / Agent。AI 不必自己計算金融模型，而是透過 MCP 呼叫本機 Python：抓資料、跑 Chronos / TimesFM / XGBoost / LightGBM、做模型驗證，再把結構化結果交回 AI 解釋。

> Cherry Studio 只是其中一個使用範例，不是本專案的必要元件。

> **研究用途，不是自動交易系統。** V1 沒有券商登入、沒有下單工具，也沒有證明模型能穩定獲利。

---

## 目前公開版本

這個 README 描述的是 **V1 Freeze** 公開基線。

- Freeze tag：`v1-freeze-2026-09-19`
- 發布 build_id：`bbf3cb2f9a80d20e`
- 本機完整測試：`154 passed`
- Clean clone 輕量測試：`134 passed`
- MCP smoke：`PASS`（13 tools）
- `ENGINEERING_GATE`：已通過
- `MODEL_PREDICTIVE_GATE`：`UNPROVEN`
- `TRADING_EDGE_GATE`：`UNPROVEN`

**最重要的一句：V1 Freeze 代表「工程底座已能穩定重建與執行」，不代表「模型已證明能賺錢」。**

發布細節：[`GITHUB_PUBLICATION_REPORT.md`](GITHUB_PUBLICATION_REPORT.md)

> Phase 2 正在另外施工中；在完成驗收以前，不會把尚未完成的功能寫成目前能力。

---

## 這套工具目前能做什麼？

例如讓 MCP Client 的 AI 幫你：

- 分析台灣上市櫃股票。
- 以目前可取得的資料研究大阪日經／日經 225。
- 分別取得 Chronos、TimesFM 的價格預測。
- 取得 XGBoost / LightGBM 的方向分類研究結果。
- 比較模型是否真的優於簡單基準，而不是只看模型名稱。
- 執行 walk-forward / 時序驗證。
- 查看資料來源是否正常、模型是否可用、GPU 是否啟用。
- 檢查 Research Gates，知道「程式能跑」和「模型有預測力」是不是同一件事。
- 把多個工具結果整理成 `analyze_osaka_nikkei` 或 `analyze_taiwan_stock` 的結構化分析資料，再交給 AI 用白話說明。

### 目前不能做什麼？

V1 **不能**：

- 登入券商。
- 自動下單、改單、刪單。
- 取得 OSE Nikkei Micro 的交易所級即時 Tick / Order Book。
- 把 `^N225` 冒充 OSE Micro。
- 用日線資料假裝產生真實 5 分鐘預測。
- 宣稱某模型已證明能長期打敗市場。

---

## 用一句圖看懂系統

```text
市場資料
TWSE / FinMind / FRED / yfinance
        │
        ▼
資料處理
時區、交易日曆、完整性、新鮮度、features
        │
        ▼
獨立模型
Chronos-2 / TimesFM 3 / XGBoost / LightGBM
        │
        ▼
Ensemble
價格集成 + 方向集成
        │
        ▼
Analysis Wrapper
台股 / 大阪日經結構化研究結果
        │
        ▼
MCP Server（stdio）
        │
        ▼
任何支援 stdio MCP 的 AI Client
Cherry Studio / 其他 MCP Host / Agent
        │
        ▼
AI 負責推理、整理與白話解釋
```

詳細架構：[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)

---

## 為什麼要做成 MCP？

因為大型語言模型適合做「理解、比較、解釋」，但不應自己憑空算金融模型。

MARKET_AI_HUB 把真正需要程式執行的工作留在本機：

```text
AI：請分析大阪日經未來 5 個交易日
        ↓
MCP Client 呼叫 market-ai tools
        ↓
Python 抓資料、跑模型、驗證 horizon / calendar / freshness
        ↓
回傳結構化 JSON
        ↓
AI 根據結果說明，不自行捏造數字
```

這樣的好處是：

1. 模型與資料處理可重現。
2. 工具輸出可以單獨測試。
3. 不綁定某一家聊天軟體。
4. AI 換成不同模型時，不需要重寫金融計算核心。

---

## 13 個 MCP tools

| Tool | 白話用途 |
|---|---|
| `health_check` | 看 MCP、模型、CUDA、資料庫是否正常 |
| `get_system_info` | 看目前版本、build_id、Python 與執行環境 |
| `get_data_source_status` | 看 TWSE / FinMind / FRED / Yahoo 等來源狀態 |
| `get_market_data` | 取得標準化市場資料 |
| `predict_chronos` | 執行 Chronos 價格預測 |
| `predict_timesfm` | 執行 TimesFM 價格預測 |
| `predict_ensemble` | 整合模型結果；**不是另一個獨立模型票** |
| `get_model_performance` | 查看已記錄的模型歷史績效 |
| `backtest` | 執行研究型 walk-forward / backtest |
| `analyze_osaka_nikkei` | 整理大阪日經研究所需資料與模型結果 |
| `analyze_taiwan_stock` | 整理台股研究所需資料與模型結果 |
| `get_research_gates` | 檢查工程、資料、模型、交易優勢是否真的通過 Gate |
| `run_ts_validation` | 對時間序列模型做標準化樣本外驗證 |

工具名稱以 Runtime 實際暴露內容為準；更新後可先呼叫 `health_check` / `get_system_info` 確認版本。

---

## 模型角色不要混在一起

V1 把模型分成兩種不同工作。

### 價格預測

- Chronos-2
- TimesFM 3
- FinCast（可選、隔離環境）

它們可以輸出價格路徑／預測分位數等研究結果。

### 方向分類

- XGBoost
- LightGBM

它們處理 Up / Flat / Down 類型的分類研究。

**分類器沒有真正的 P10 / P50 / P90；未校準的分類分數也不能叫「上漲機率」。**

此外：

- Base Model = 獨立模型。
- Ensemble = 整合層，不是額外一票。
- Analysis Wrapper = 分析封裝，不是額外一票。

---

## 資料來源

| 類型 | 目前來源 | V1 用途 |
|---|---|---|
| 台股 | TWSE OpenAPI / FinMind Free | 官方資料、日線研究 |
| 日經 225 | yfinance `^N225` | **研究代理標的**，不是 OSE Micro |
| 跨市場 | USDJPY、NQ、ES、VIX、SOX、Gold、WTI、BTC 等 | 跨市場參考 |
| 美國總經 | FRED | DGS2 / DGS10 / FEDFUNDS 等 |

### 大阪日經的重要限制

V1 目前沒有合法免費的 exchange-grade OSE Micro 即時資料。

因此：

```text
^N225 ≠ OSE Nikkei Futures
^N225 ≠ OSE Mini
^N225 ≠ OSE Micro
```

當工具使用 `^N225` 時，應把它當「日經 225 現貨指數代理資料」理解。

資料矩陣：[`docs/DATA_SOURCE_MATRIX.md`](docs/DATA_SOURCE_MATRIX.md)

---

## Research Gates 是什麼？

這是本專案刻意加入的防呆。

| Gate | 白話意思 |
|---|---|
| `ENGINEERING_GATE` | 程式本身能不能正常跑 |
| `MARKET_DATA_GATE` | 市場資料是否能正確取得 |
| `CALENDAR_GATE` | 交易日曆是否可靠 |
| `TEMPORAL_ALIGNMENT_GATE` | 有沒有把未來／歷史日期弄錯 |
| `DATA_GATE` | 資料層整體是否合格 |
| `MODEL_PREDICTIVE_GATE` | 模型是否真的被證明有預測力 |
| `TRADING_EDGE_GATE` | 扣除實際交易條件後是否有交易優勢 |

目前最重要的狀態：

```text
ENGINEERING_GATE       PASS
MODEL_PREDICTIVE_GATE  UNPROVEN
TRADING_EDGE_GATE      UNPROVEN
```

所以不要把「程式跑成功」翻譯成「AI 已經會賺錢」。

---

# 安裝（Windows）

V1 Freeze 實測環境是 Windows 11 + Python 3.12。

## 1. Clone

```powershell
git clone https://github.com/fishke22/market-ai-hub.git D:\MARKET_AI_HUB
cd D:\MARKET_AI_HUB
```

如果你要完全重現公開 Freeze，可 checkout：

```powershell
git checkout v1-freeze-2026-09-19
```

## 2. 一鍵建立環境

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1 -WithDev
```

## 3. 下載模型

```powershell
.venv\Scripts\python.exe scripts\download_models.py --check
.venv\Scripts\python.exe scripts\download_models.py --download
```

模型 weights 不放在 GitHub repository；腳本會從官方來源下載。

## 4. 驗證

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify_install.ps1
```

完整說明：[`docs/INSTALL_WINDOWS.md`](docs/INSTALL_WINDOWS.md)

---

# 接到 MCP Client

只要 Client 能啟動**本機 stdio MCP Server**，理論上就能使用 MARKET_AI_HUB。

核心設定只有：

```text
Transport: stdio
Command: D:\MARKET_AI_HUB\.venv\Scripts\market-ai-mcp.exe
Args: 空白
Working directory: D:\MARKET_AI_HUB（Client 有此欄位時再填）
```

不同 MCP Client 的設定介面不一樣，所以欄位名稱可能不同。

通用設定說明：[`docs/MCP_CLIENT_SETUP.md`](docs/MCP_CLIENT_SETUP.md)

Cherry Studio 使用者可直接看：[`docs/CHERRY_STUDIO_SETUP.md`](docs/CHERRY_STUDIO_SETUP.md)

> 更新程式後，記得重啟 MCP process。MCP 是長駐 process，舊 process 不會自動載入新程式。

---

## 建議先做的三個測試

### 1. 系統健康檢查

請 AI 呼叫：

```text
health_check
```

確認：

- `status = ok`
- build_id 正確
- Chronos / TimesFM 狀態
- CUDA 是否可用

### 2. Research Gates

```text
請呼叫 get_research_gates，告訴我哪些 Gate 已通過、哪些仍是 UNPROVEN，並用白話解釋。
```

### 3. 模型驗證

```text
請用 run_ts_validation 檢查目前大阪日經代理標的的 Chronos 與 TimesFM 是否真的優於 Naive baseline；不要把 engineering PASS 當成 predictive VALIDATED。
```

更多可直接複製的問題：[`docs/prompts/QUICK_PROMPTS.md`](docs/prompts/QUICK_PROMPTS.md)

---

## Agent 系統提示詞

專案不要求一定使用某一個 System Prompt，但如果你希望 AI 比較嚴格地遵守：

- 商品／Proxy 分離
- 交易日曆
- 模型 Eligibility
- 不重複計票
- 不把未校準分數說成機率
- Research Gates
- 白話輸出

可以參考：

[`docs/prompts/SYSTEM_PROMPT_V3_3_REFERENCE.md`](docs/prompts/SYSTEM_PROMPT_V3_3_REFERENCE.md)

這份 Prompt 原本是在 Cherry Studio 中使用，但 **MARKET_AI_HUB 本身不是 Cherry Studio 專用**。只要其他 MCP Host 能提供相同工具與外部資料能力，也可以調整後使用。

---

## 硬體需求

### 可以執行

- Windows 10 / 11 x64
- Python 3.11 或 3.12 x64
- 16 GB RAM 建議值
- 無 GPU 也可以使用 CPU

### 建議

- NVIDIA GPU
- 32 GB RAM
- SSD

V1 Freeze 驗證機器：RTX 4060 Ti 16 GB。

---

## 常見限制

1. Chronos / TimesFM 在目前完整市場驗證中仍屬 `UNVALIDATED`，不要假設 Foundation Model 一定比簡單模型準。
2. `^N225` 是 proxy，不是 OSE Micro 即時行情。
3. 日線來源不能用來假裝支援 5m / 15m / 30m / 60m 真實日內預測。
4. 分類模型 probability 尚未完成正式 calibration。
5. FinMind / FRED 若未提供 token，相關 provider 會顯示 `needs_config`，其他功能仍可工作。
6. V1 沒有券商、Tick、Order Book 或下單能力。

---

## 文件導覽

| 文件 | 用途 |
|---|---|
| [`docs/MCP_CLIENT_SETUP.md`](docs/MCP_CLIENT_SETUP.md) | 通用 MCP Client 接法 |
| [`docs/CHERRY_STUDIO_SETUP.md`](docs/CHERRY_STUDIO_SETUP.md) | Cherry Studio 設定範例 |
| [`docs/INSTALL_WINDOWS.md`](docs/INSTALL_WINDOWS.md) | Windows 詳細安裝 |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | 系統架構與模型角色 |
| [`docs/DATA_SOURCE_MATRIX.md`](docs/DATA_SOURCE_MATRIX.md) | 資料來源與限制 |
| [`docs/LICENSE_MATRIX.md`](docs/LICENSE_MATRIX.md) | 第三方授權 |
| [`docs/BACKUP_AND_RESTORE.md`](docs/BACKUP_AND_RESTORE.md) | 備份與完整還原 |
| [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md) | 故障排除 |
| [`docs/prompts/QUICK_PROMPTS.md`](docs/prompts/QUICK_PROMPTS.md) | 可直接貼給 AI 的快捷問題 |
| [`docs/prompts/SYSTEM_PROMPT_V3_3_REFERENCE.md`](docs/prompts/SYSTEM_PROMPT_V3_3_REFERENCE.md) | 完整 Agent Prompt 參考 |

---

## 安全與授權

- `.env`、token、模型 cache、市場資料與本機 logs 不應提交 GitHub。
- 模型 weights 不隨 repository 散布。
- TimesFM 3 pretrained weights 有非商業使用限制，請看 [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)。
- Security 說明：[`SECURITY.md`](SECURITY.md)
- 研究免責：[`DISCLAIMER.md`](DISCLAIMER.md)

---

## 最後再用一句白話說明

**MARKET_AI_HUB 是「金融分析 AI 的本機工具箱」，不是另一個聊天機器人。**

它讓支援 MCP 的 AI 可以呼叫真正的資料與模型，再根據工具回傳的證據回答你；目前 V1 已把工程、時間語義與模型驗證框架做好，但「模型是否真的能穩定預測市場」仍必須繼續用 OOS、Forward Test 與後續資料驗證。
