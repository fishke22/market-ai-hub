# 疑難排解（TROUBLESHOOTING）

## Python 找不到

- 症狀：`python --version` 找不到。
- 原因：安裝時沒勾 `Add python.exe to PATH`，或沒開新的 PowerShell。
- 解法：關掉再開新 PowerShell；仍失敗 → 重新安裝並勾選 PATH，或用 `py -3.12 --version`。

## venv 問題

- 症狀：`找不到 .venv\Scripts\python.exe`。
- 解法：跑 `python -m venv .venv` 或直接 `scripts\setup_windows.ps1`。
- 若 `.venv` 損壞：刪除 `.venv` 後重建（不會影響原始碼）。

## Torch / CUDA

- 症狀：`cuda_available=False` 但你有 NVIDIA GPU。
- 原因：裝到 CPU wheel。
- 解法：
  ```powershell
  .venv\Scripts\python.exe -m pip install torch==2.14.0 --index-url https://download.pytorch.org/whl/cu130
  ```
- 沒有 GPU：可用 CPU，功能完整但較慢。

## 模型下載失敗

- 症狀：`401` / `403` / gated repo。
- 解法：執行 `huggingface-cli login`（瀏覽器登入）。**不要把 token 貼進任何檔案。**
- 網路受限：改用離線備份（`scripts\create_offline_backup.ps1 -IncludeModels`）在另一台還原。

## Hugging Face cache

- 位置：`%USERPROFILE%\.cache\huggingface\hub`（或 `HF_HOME` / `HF_HUB_CACHE` 指定的位置）。
- 若 cache 損壞：刪除對應 `models--*` 目錄後重新下載。
- FinCast checkpoint 可用環境變數 `FINCAST_CHECKPOINT` 指定路徑。

## MCP 啟動失敗

- 手動跑看錯誤：`D:\MARKET_AI_HUB\.venv\Scripts\market-ai-mcp.exe`
- 常見：Command 路徑錯、`.venv` 未建、依賴未裝、`logs/` 無法建立（權限）。
- 修正後在 Cherry Studio 重啟 MCP。

## Cherry Studio Tool Not Found

- MCP 未啟用 → 打開開關。
- 工具名稱拼錯 → 用 `get_system_info.mcp_tools` 看清單。
- 剛更新程式 → 重啟 MCP。

## 舊 MCP process / build_id 不更新（最常見）

- 原因：MCP 是長駐 process，持有啟動時的 code。
- 解法：在 Cherry Studio 把 `market-ai` **關掉再打開**（或重啟 Cherry Studio）。
- 驗證：`health_check.build.build_id` 應等於目前版本（V1 Freeze = `4742a33e5b17d1d0`）。

## XGBoost 相關

- 症狀：`XGBoostError`、`inf or a value too large`。
- 說明：本專案已在 feature 層把 ±inf 轉為 NaN（V1 已修）。若仍發生，請回報並附輸入 symbol / period。
- 症狀：`training labels contain only one class` → 該股票在該視窗幾乎無波動，分類器誠實回 unavailable（正常）。

## GPU OOM

- 關閉其他佔用 GPU 的程式（瀏覽器、遊戲、其他 AI）。
- 或改用 CPU（移除 CUDA torch）。

## 沒有 GPU

- 一切功能可用，只是模型推論較慢（首次載入數十秒）。
- `health_check.cuda_available=false` 是正常。

## Yahoo / TWSE 暫時失效

- yfinance 為 unofficial，Yahoo 可能暫時限流；稍後重試。
- TWSE / FinMind 偶爾維護中；系統會 graceful degrade（該來源 unavailable，其餘照常）。
- 系統**不會**用假資料填補。

## 網路離線

- 模型已下載時，Chronos/TimesFM 可離線推論。
- 但**市場資料**需要網路；離線時 provider 顯示 unavailable。
- 完全離線研究：請先在有網路時抓資料並落 DuckDB，再離線分析。
