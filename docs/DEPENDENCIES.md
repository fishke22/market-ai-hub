# 依賴清單（DEPENDENCIES）

V1 Freeze 實際使用與驗證的版本。精確傳遞依賴見 `requirements-lock-windows-x64.txt`。

## A. 系統需求（System Requirements）

| 名稱 | V1 版本 | 用途 | 是否必須 | 來源 | 安裝方式 | 備註 |
|------|---------|------|----------|------|----------|------|
| Windows | 10 / 11 x64 | 作業系統 | 必須 | Microsoft 官方 | 系統內建 | V1 Freeze 為 Windows 11 |
| Python | 3.12.13 x64 | 執行環境 | 必須 | python.org | 官方安裝檔（勾 Add to PATH） | 3.11 亦可；勿用 3.14 |
| Git | 2.x | 取得原始碼 | 必須（clone） | git-scm.com | 官方安裝檔 | 若用 ZIP 下載則可免 |
| PowerShell | 5.1+ | 執行安裝腳本 | 必須 | Microsoft | 系統內建 | — |
| NVIDIA driver | 616.56 | GPU 推論 | **只有 GPU 才需要** | NVIDIA 官方 | 官方驅動 | 無 GPU 可用 CPU |
| CUDA runtime | 13.0（torch 內建） | GPU 推論 | **只有 GPU 才需要** | PyTorch wheel 內含 | 隨 torch cu130 wheel | 不需另裝 CUDA Toolkit |
| Visual C++ Runtime | — | 部分 wheel 相依 | 視情況 | Microsoft 官方 | 官方可轉散發套件 | 若 import 失敗再裝 |

## B. Python Runtime Dependencies（執行必須）

| 套件 | V1 版本 | 用途 | 必須 | License |
|------|---------|------|------|---------|
| numpy | 2.5.3 | 數值運算 | 是 | BSD-3 |
| pandas | 3.0.6 | 資料處理 | 是 | BSD-3 |
| scipy | 1.18.1 | 科學運算 | 是 | BSD-3 |
| scikit-learn | 1.9.1 | 傳統 ML | 是 | BSD-3 |
| xgboost | 3.4.1 | 分類器 | 是 | Apache-2.0 |
| lightgbm | 4.7.0 | 分類器 | 是 | MIT |
| duckdb | 1.5.5 | 本地儲存 | 是 | MIT |
| pyarrow | 25.0.1 | Parquet | 是 | Apache-2.0 |
| yfinance | 1.7.0 | Yahoo 行情（unofficial） | 是 | Apache-2.0 |
| requests | 2.34.2 | HTTP | 是 | Apache-2.0 |
| httpx | 0.28.1 | HTTP | 是 | BSD-3 |
| pytz / tzdata | 2026.3.post1 / 2026.4 | 時區 | 是 | MIT / Apache-2.0 |
| PyYAML | 6.0.3 | 設定檔 | 是 | MIT |
| exchange-calendars | 4.13.2 | 交易所日曆 | 是 | Apache-2.0 |
| pandas-market-calendars | 5.4.0 | 日曆工具 | 是 | Apache-2.0 |
| pydantic | 2.13.5 | schema | 是 | MIT |
| python-dotenv | 1.2.3 | .env 讀取 | 是 | BSD-3 |
| mcp | 2.2.0 | MCP server | 是 | MIT |
| chronos-forecasting | 2.3.2 | Chronos-2 推論 | 是 | Apache-2.0 |
| timesfm | 3.0.2 | TimesFM-3 推論 | 是 | Apache-2.0（source） |
| torch | 2.14.0+cu130 | 深度學習推論 | 是 | BSD-3 |

## C. Development / Test Dependencies

| 套件 | V1 版本 | 用途 | 必須 | License |
|------|---------|------|------|---------|
| pytest | 9.1.1 | 測試 | 只有開發/測試 | MIT |

## D. Optional Dependencies

| 套件 / 元件 | 用途 | 是否必須 | 備註 |
|-------------|------|----------|------|
| FinCast（`.venv-fincast` + weights） | 額外價格模型 | 否 | 依賴與主環境衝突，隔離安裝；weights 非必需 |
| NVIDIA GPU | 加速推論 | 否 | CPU 可執行 |
| FINMIND_TOKEN | 台股資料 | 否 | 未設 → 該來源 needs_config，系統仍運作 |
| FRED_API_KEY | 總經資料 | 否 | 同上 |

## E. Model Dependencies（模型下載）

| 模型 | model_id | revision | 大小 | License | 可重新散布 |
|------|----------|----------|------|---------|-----------|
| Chronos-2 | amazon/chronos-2 | `29ec3766…` | ~456 MB | Apache-2.0 | 是（本專案仍不散布） |
| TimesFM-3.0 | google/timesfm-3.0-pytorch | `43046b85…` | ~1262 MB | **非商業** | **否** |
| FinCast（可選） | Vincent05R/FinCast | `2d7d90b1…` | ~3967 MB | Apache-2.0（repo）/ research | 否 |

下載：`scripts/download_models.py --download`（會 pin revision）。詳見 `config/model_manifest.yaml`。
