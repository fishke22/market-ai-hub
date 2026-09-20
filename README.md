# MARKET_AI_HUB

> **金融研究、預測模型與驗證工具，封裝成 MCP tools 給本機 AI Client / Agent 使用。**
> 把 MARKET_AI_HUB 接到任何**支援 stdio MCP** 的 AI Client / Agent（Cherry Studio / Claude Desktop / Codex / 其他 MCP Host），AI 不用自己跑模型，而是透過 MCP 呼叫本機 Python 做研究。
>
> **Cherry Studio 只是其中一個使用例子，不是唯一或必備軟體。**
>
> **研究用途，不是自動交易系統。** 這不是 AI 聊天模型本身，而是金融研究後端。

> Release：**v2.0.0-rc1**（Phase 2 Research Release Candidate）

## 第一次使用？從這裡開始

- [第一次使用，從這裡開始](docs/START_HERE_BEGINNER.md)
- [在 Cherry Studio 使用（小白版）](docs/CHERRY_STUDIO_BEGINNER_GUIDE.md)
- [通用 MCP Client 設定](docs/MCP_CLIENT_SETUP.md)
- [Cherry Studio 技術設定](docs/CHERRY_STUDIO_SETUP.md)
- [每天怎麼用](docs/DAILY_WORKFLOW_FOR_BEGINNERS.md)
- [系統會不會自己學](docs/AUTO_LEARNING_FOR_BEGINNERS.md)
- [離「可交易」還有多遠](docs/TRADING_READINESS_FOR_BEGINNERS.md)
- [電腦資源會不會被吃滿](docs/SAFE_TRAINING_FOR_BEGINNERS.md)
- [資料要不要手動更新](docs/DATA_UPDATE_FOR_BEGINNERS.md)
- [常見問題 FAQ](docs/FAQ_BEGINNER.md)

---

## 系統定位

MARKET_AI_HUB 讓 AI Agent 透過 MCP（Model Context Protocol）取得：
- 官方與 proxy 市場資料（Data Lake）
- 模型預測（Prediction Registry / Model Tournament）
- 情境分析（Joint / Scenario Forecast + Dynamic Ensemble）
- 歷史策略研究（Historical Edge Store）
- 結構化分析封包（Analysis Packet）

**真正大阪研究 target = OSE Nikkei 225 Micro Futures**（`OSE_NIKKEI225_MICRO_FUTURES`，不是 `^N225`）。

- MCP tools：**21**（runtime introspection）
- Skills：**3**（osaka-micro-analysis / taiwan-stock-v28 / model-validation-audit）
- 完整測試：**649 passed**（DESKTOP_SAFE，無 GPU）

---

## 現在能做什麼

| 能力 | 狀態 |
|---|---|
| 大阪微型日經研究（OSE Micro TARGET / settlement / volume / OI） | ✅ AVAILABLE |
| 台股分析（2330 / 3706.TW 等） | ✅ AVAILABLE |
| `get_analysis_packet`（compact/normal/audit） | ✅ AVAILABLE |
| 模型預測（Chronos-2 / TimesFM / XGBoost / LightGBM） | ✅ AVAILABLE |
| NHITS / NBEATSx（training-only，runtime blocked） | ⚠️ BLOCKED |
| Model Tournament + Best Baseline | ✅ AVAILABLE |
| 歷史策略研究（Edge Store / walk-forward / cost） | ✅ AVAILABLE |
| 自動研究循環 + 受控自動學習 | ✅ AVAILABLE |
| 官方資料 live（JPX settlement/volume/OI + BLS/Cboe/EDGAR/BOJ） | ✅ PARTIAL |

## 現在不能做什麼

| 能力 | 狀態 |
|---|---|
| Live Trading / 下單 | ❌ PROHIBITED |
| Yuanta realtime recorder | ❌ DISABLED |
| TradingView 依賴 | ⚠️ OPTIONAL（未安裝） |
| 自動 Champion promotion | ❌ DISABLED（需 human approval） |
| Foundation model 微調 | ❌ DISABLED（僅 interface） |
| 宣稱可獲利策略 | ❌ PROHIBITED（歷史 OOS + 因果 audit 已驗證：無可執行 edge） |

---

## Research State（誠實結論）

> **Historical statistical signal does NOT imply executable trading edge.**

| 層級 | 結論 |
|------|------|
| Proxy（^N225）OOS | NO_EVIDENCE |
| Direct Micro 歷史 OOS | VAR(1) = STATISTICAL_FORECAST_EVIDENCE（MASE 0.958, direction 62.2%） |
| Executability（因果 audit） | NON_EXECUTABLE_FORECAST_EDGE（edge 在 overnight gap，需當日 full close，pre-close 失效） |
| Strategy（含成本） | NO_ECONOMIC_EDGE |
| Forward Shadow | NONE_YET（activated 2026-09-20，尚無真實交易日 evidence） |
| **Strategy candidate** | **NONE** |
| **Production candidate** | **NONE** |

詳見 [`docs/VALIDATION_EVIDENCE.md`](docs/VALIDATION_EVIDENCE.md) 與 [`PHASE2_RESEARCH_FREEZE.yaml`](PHASE2_RESEARCH_FREEZE.yaml)。

---

## 架構圖

```
Official Data Sources → Smart Data Lake → Data Quality → Feature Store
  → Regime/Events → Direct Models → Model Tournament → Joint/Scenario
  → Dynamic Ensemble → Historical Edge → Strategy Research
  → Analysis Packet → MCP → Skills → AI Client
```
詳見 [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)。

---

## 快速連結

- 重建指引（給 AI Agent）：[`docs/AI_RECONSTRUCTION_GUIDE.md`](docs/AI_RECONSTRUCTION_GUIDE.md)
- 系統 manifest：[`SYSTEM_MANIFEST.yaml`](SYSTEM_MANIFEST.yaml)
- MCP tool 清單：[`docs/MCP_TOOL_REFERENCE.md`](docs/MCP_TOOL_REFERENCE.md)
- 資料來源矩陣：[`docs/DATA_SOURCE_MATRIX.md`](docs/DATA_SOURCE_MATRIX.md)
- 模型 pipeline：[`docs/MODEL_PIPELINE.md`](docs/MODEL_PIPELINE.md)
- 自動學習：[`docs/AUTOMATED_LEARNING.md`](docs/AUTOMATED_LEARNING.md)
- Skills：[`docs/SKILLS_REFERENCE.md`](docs/SKILLS_REFERENCE.md)
- Client 整合：[`docs/CLIENT_INTEGRATION_MATRIX.md`](docs/CLIENT_INTEGRATION_MATRIX.md)
- System Prompt（推薦）：[`docs/prompts/SYSTEM_PROMPT_V4_PHASE2_RC1.md`](docs/prompts/SYSTEM_PROMPT_V4_PHASE2_RC1.md)
- 安裝（Windows）：[`docs/INSTALL_WINDOWS.md`](docs/INSTALL_WINDOWS.md)

## 安裝 / 驗證

```powershell
# 1. 建立環境
scripts\setup_windows.ps1

# 2. 下載 required models
python scripts\download_models.py --required

# 3. 驗證
pytest tests/

# 4. 啟動 MCP
.venv\Scripts\market-ai-mcp.exe
# 或
python -m market_ai_hub.mcp.server
```

## Research Gates

模型需通過 `ENGINEERING_GATE / DATA_GATE / MODEL_PREDICTIVE_GATE / TRADING_EDGE_GATE`。
`TRADING_EDGE_GATE` 預設 `UNPROVEN`（無 forward-validated edge）。

## Compute Resource Governor

**預設 `DESKTOP_SAFE`**（不是 TRAINING_MAX）。未來任何 training / fine-tuning / Optuna / GPU batch
不得吃滿整台電腦。GPU VRAM ≤ 65%（soft）/ 75%（hard，保留 ≥4GB）；CPU 保留 25% 給系統；
RAM ≤ 65%/75%；process priority BelowNormal；同時間最多一個 GPU_HEAVY job。

`AUTO_TRAIN=false` / `AUTO_FINE_TUNE=false` / `AUTO_PROMOTE=false`。

見 [`config/resource_profiles.yaml`](config/resource_profiles.yaml) 與 [`PHASE2VF_RESOURCE_GOVERNOR_REPORT.md`](PHASE2VF_RESOURCE_GOVERNOR_REPORT.md)。

## Security

NO LIVE TRADING / NO ORDER MCP / NO BROKER CREDENTIAL。見 [`SECURITY.md`](SECURITY.md)。

## Known Limitations

- **No validated executable edge**（VAR forecast 有統計訊號，但 non-causal / non-executable）。
- **Forward evidence NONE_YET**（activated 2026-09-20，需持續合法更新 Micro data）。
- OSE Micro settlement history 不足（JPX 公開源僅當日，歷史 404；需 J-Quants/Data Cloud）。
- 225LABO 為 LOCAL_ONLY center-month continuous dataset（非 contract-level，不得發布）。
- OSE Micro per-contract OHLC：CONTRACT_ONLY（官方 xlsx/csv 無）。
- BEA / e-Stat / EIA / EDINET：NEEDS_CONFIG（需 API key）。
- Yuanta Futures SPARK 0112：OBSERVED UNRESOLVED_EXTERNAL。
- Yuanta Legacy Quote T 盤：REQUIRES_SESSION_AWARE_RETEST。
- NHITS / NBEATSx：runtime blocked（training-only）。
- TradingView：OPTIONAL（免費 15 分鐘延遲）。
- 詳見 [`CURRENT_HANDOFF.md`](CURRENT_HANDOFF.md)、[`PHASE2_RESEARCH_FREEZE.yaml`](PHASE2_RESEARCH_FREEZE.yaml) 與 [`docs/DATA_SOURCE_MATRIX.md`](docs/DATA_SOURCE_MATRIX.md)。

## Yuanta API（四條 family，勿混用）

元大 API 分成四條：SPARK（證券+期貨）、Futures Legacy Quote、Futures Legacy Trading、
**Leveraged Trading「槓桿全球贏家」Web API（CFD，獨立槓桿帳戶）**。

⚠️ **不要到「槓桿全球贏家」API 申請頁（`ltm.yuantafutures.com.tw/member/api-apply`）申請一般 Futures API。**
OSE Micro / JNU 是 JPX Futures，應走一般 Futures / SPARK 路徑。

見 [`docs/YUANTA_SETUP_AND_LOGIN.md`](docs/YUANTA_SETUP_AND_LOGIN.md)、
[`docs/YUANTA_API_ARCHITECTURE.md`](docs/YUANTA_API_ARCHITECTURE.md)、
[`docs/YUANTA_LEVERAGED_TRADING_API.md`](docs/YUANTA_LEVERAGED_TRADING_API.md)。

---

### V1 Freeze 歷史

V1 為 Freeze 快照（`build_id bbf3cb2f9a80d20e`）。歷史報告見 `V1_*_REPORT.md` 與 `docs/history/`（HISTORICAL V1 SNAPSHOT）。
