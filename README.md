# MARKET_AI_HUB

**台股與大阪日經的金融市場「研究、預測與分析」系統，透過 MCP 提供給 Cherry Studio 使用。**

> 白話說明：這是一套幫你做**市場研究**的工具。你在 Cherry Studio 裡輸入「分析大阪日經」或
> 「分析 2330」，它會去抓市場資料、用幾個時間序列模型與傳統機器學習模型做預測，回傳
> **結構化證據**（數字、方向、信心來源），最後由 Cherry Studio 的 AI 幫你寫成白話分析。
>
> **它不是什麼：** 不是保證獲利的工具、不是投資建議、**沒有券商登入、沒有任何自動下單功能**。
> 它不會、也不能幫你買賣股票。所有輸出都只是研究參考，可能出錯。

---

## 1. V1 Freeze 狀態

- **Freeze build_id**：`4742a33e5b17d1d0`
- **Freeze 日期**：2026-09-19
- **測試**：`154 passed`（pytest）；MCP smoke `PASS`（13 tools）
- **Research Gates**：`ENGINEERING_GATE` 已通過（工程正確性）；`MODEL_PREDICTIVE_GATE` /
  `TRADING_EDGE_GATE` **仍為 UNPROVEN**（尚無完整 OOS 證據證明模型有預測力或交易優勢）
- ⚠️ **V1 Freeze 代表「工程與正確性已凍結」，不代表「模型已證明能賺錢」。**

## 2. 支援市場

| 市場 | 資料來源 | 等級 |
|------|---------|------|
| 台股（TWSE） | FinMind（Free tier）/ TWSE OpenAPI | OFFICIAL_DAILY |
| 大阪日經（^N225 proxy） | yfinance（Nikkei 225 INDEX） | RESEARCH_PROXY / DELAYED |
| 跨市場（USDJPY、NQ、ES、VIX、SOX、Gold、WTI、BTC） | yfinance | RESEARCH_PROXY / DELAYED |
| 總經（DGS2 / DGS10 / FEDFUNDS） | FRED（需免費 API key） | OFFICIAL_DAILY |

> ⚠️ **^N225 是「日經 225 現貨指數」代理，不是 OSE 微型期貨即時行情。** 本系統沒有免費的
> exchange-grade OSE 微型期貨資料源，大阪分析目前是研究用 PROXY 骨架。

## 3. 系統架構

```
資料來源 (TWSE / FinMind / FRED / yfinance)
        ↓
   Data layer（清理 / 時區對齊 / trading calendar）
        ↓
   Base Models（Chronos-2、TimesFM-3.0、XGBoost、LightGBM）
        ↓
   Ensemble（price_ensemble + direction_ensemble）
        ↓
   Analysis Wrapper（analyze_osaka_nikkei / analyze_taiwan_stock）
        ↓
   MCP Server（stdio，13 tools）
        ↓
   Cherry Studio（LLM 生成自然語言分析）
```

## 4. Base Model / Ensemble / Wrapper

- **BASE_MODEL（獨立模型）**：chronos-2、timesfm-3.0、xgboost、lightgbm
- **ENSEMBLE**：不是第 5 個獨立模型。分 `price_ensemble`（價格）與 `direction_ensemble`（方向）。
- **ANALYSIS_WRAPPER**：不是第 6 個獨立模型。包裝資料 + base models + ensemble 成一份結構化證據。
- 模型分兩類任務：`PRICE_FORECAST`（chronos/timesfm）與 `DIRECTION_CLASSIFICATION`（xgb/lgbm）。

## 5. 目前模型

| 模型 | 任務 | 授權 | 狀態 |
|------|------|------|------|
| Chronos-2 | PRICE_FORECAST | Apache-2.0 | engineering PASS / predictive UNVALIDATED |
| TimesFM-3.0 | PRICE_FORECAST | **非商業（research only）** | engineering PASS / predictive UNVALIDATED |
| XGBoost | DIRECTION_CLASSIFICATION | Apache-2.0 | engineering PASS |
| LightGBM | DIRECTION_CLASSIFICATION | MIT | engineering PASS |
| FinCast（可選） | PRICE_FORECAST | Apache-2.0（repo）/ research | 隔離環境，非必需 |

## 6. Research Gates（研究驗證閘門）

| Gate | 意義 |
|------|------|
| ENGINEERING_GATE | 程式能否正確執行 |
| MARKET_DATA_GATE | 市場資料來源是否可用 |
| CALENDAR_GATE | 交易所日曆是否可靠 |
| TEMPORAL_ALIGNMENT_GATE | 預測目標日期是否全為未來 session |
| DATA_GATE | 上述子 gate 綜合 |
| MODEL_PREDICTIVE_GATE | 模型是否被證明有預測力（目前 UNPROVEN） |
| TRADING_EDGE_GATE | 是否有交易優勢（目前 UNPROVEN） |

## 7. 目前重要限制

1. 大阪日經是 ^N225 INDEX proxy，不是 OSE 微型期貨。
2. 時間序列模型（Chronos/TimesFM）尚未通過完整 OOS 驗證（UNVALIDATED）。
3. 分類器 class probability 未經 calibration（已明確標記）。
4. 日內（5m/15m/30m/60m）horizon 在日線資料下不支援（回 UNSUPPORTED_WITH_CURRENT_DATA）。
5. 無券商 / 下單 / 即時 tick 能力。
6. FinMind / FRED 需要自備免費 token（未設定時系統仍可運作，該來源顯示 needs_config）。

## 8. 最低硬體要求

- **無 GPU 也可執行**（CPU 模式）：模型載入較慢，但功能完整。
- 記憶體：建議 16 GB 以上。
- 磁碟：模型約 1.7 GB（Chronos 456 MB + TimesFM 1262 MB；FinCast 另約 4 GB）。

## 9. 建議硬體

- NVIDIA GPU（V1 Freeze 使用 RTX 4060 Ti 16 GB），CUDA 可用時推論較快。
- 32 GB RAM、SSD。

## 10. 必備軟體

| 軟體 | 版本 | 說明 |
|------|------|------|
| Windows | 10 / 11 x64 | V1 Freeze 為 Windows 11 |
| Python | 3.11 或 3.12 x64 | 建議 3.12（V1 Freeze：3.12.13） |
| Git | 任一近期版本 | clone repository |
| NVIDIA driver | 近期版本（可選） | 只有要用 GPU 才需要 |

## 11. Python 安裝

1. 到官方網站：<https://www.python.org/downloads/windows/>
2. 下載 **Python 3.12.x (64-bit)** 安裝檔。
3. 安裝時**勾選 "Add python.exe to PATH"**。
4. 安裝後開新的 PowerShell，執行 `python --version`，看到 `Python 3.12.x` 即成功。

## 12. Git 安裝

1. 官方網站：<https://git-scm.com/download/win>
2. 下載並安裝（一路 Next 即可）。
3. 開新的 PowerShell，執行 `git --version` 確認。

## 13. Clone repository

```powershell
git clone https://github.com/<你的帳號>/market-ai-hub.git D:\MARKET_AI_HUB
cd D:\MARKET_AI_HUB
```

> 以下指令以 `D:\MARKET_AI_HUB` 為例，可換成你自己的路徑。

## 14. 建立環境（一鍵）

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1 -WithDev
```

腳本會：檢查 Python → 建 `.venv` → 安裝依賴 → 檢查 Torch/CUDA → 檢查 import → 提醒下載模型。

## 15. 安裝 Python dependencies（手動）

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-runtime.txt
pip install -e .
pip install -r requirements-dev.txt   # 開發/測試才需要
```

GPU（CUDA）torch：

```powershell
pip install torch==2.14.0 --index-url https://download.pytorch.org/whl/cu130
```

## 16. 下載 models

```powershell
.venv\Scripts\python.exe scripts\download_models.py --check      # 只檢查
.venv\Scripts\python.exe scripts\download_models.py --download   # 下載缺少的
```

模型 weights 不會進 repository；本腳本會 pin V1 當時的 revision 從官方 Hugging Face 下載。
若遇到需授權的 repo，請用官方 `huggingface-cli login`（瀏覽器登入），不要把 token 寫進檔案。

## 17. 啟動 MCP

MCP server 由 Cherry Studio 自動啟動（stdio），不需手動常駐。手動測試：

```powershell
D:\MARKET_AI_HUB\.venv\Scripts\market-ai-mcp.exe
```

（正常會等待 stdin；按 Ctrl+C 結束。）

## 18. Cherry Studio 設定

詳見 [`docs/CHERRY_STUDIO_SETUP.md`](docs/CHERRY_STUDIO_SETUP.md)。重點：

- Type：`stdio`
- Command：`D:\MARKET_AI_HUB\.venv\Scripts\market-ai-mcp.exe`
- Args：留空

## 19. 驗證 health_check

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify_install.ps1
```

或在 Cherry Studio 呼叫 `health_check`，確認 `status=ok` 且 `build.build_id` 正確。

## 20. 跑 tests

```powershell
.venv\Scripts\python.exe -m pytest tests -q                      # 全部
.venv\Scripts\python.exe -m pytest tests -q -m "not integration" # 只跑輕量（不需模型）
```

## 21. 更新程式

```powershell
git pull
.venv\Scripts\python.exe -m pip install -r requirements-runtime.txt
.venv\Scripts\python.exe -m pip install -e .
```

> ⚠️ 更新後**務必在 Cherry Studio 重新啟動 market-ai MCP**（見第 23 節）。

## 22. 常見問題

見 [`docs/TROUBLESHOOTING.md`](docs/TROUBLESHOOTING.md)。最常見：Cherry Studio 的 MCP 是
**長駐 process**，改完程式一定要重啟它，否則仍跑舊 code（用 build_id 判斷）。

## 23. 如何從完全空白 Windows 恢復

完整步驟見 [`docs/BACKUP_AND_RESTORE.md`](docs/BACKUP_AND_RESTORE.md)。摘要：

1. 安裝 Git 與 Python（官方來源）。
2. `git clone` repository。
3. 跑 `scripts\setup_windows.ps1`。
4. 跑 `scripts\download_models.py --download`。
5. 跑 `scripts\verify_install.ps1`（看到 `INSTALLATION VERIFIED`）。
6. 設定 Cherry Studio → 呼叫 `health_check`。

## 24. Backup

- **原始碼**：GitHub 即為第一層備份（release 的 Source ZIP 為不可變快照）。
- **模型 / wheels / 市場資料**：不適合放 GitHub，使用 `scripts\create_offline_backup.ps1`
  （可選 `-IncludePythonPackages`、`-IncludeModels`）備份到你指定的磁碟，並產生 `SHA256SUMS.txt`。
- **環境快照**：`scripts\export_environment.ps1`。

## 25. 第三方授權

見 [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)。**本 repository 公開可讀，但專案自身授權尚未另行指定**；
第三方元件仍依各自 license。模型 weights 不隨 repository 散布。

## 26. 免責聲明

見 [`DISCLAIMER.md`](DISCLAIMER.md)。**本系統為研究用途，非投資建議；模型可能錯誤；過去績效不保證未來；
目前不包含自動下單。**
