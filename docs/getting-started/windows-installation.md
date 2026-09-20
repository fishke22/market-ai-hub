# 安裝指南（Windows，給不太懂 Python 的人）

本文件從「完全空白的 Windows」開始，一步一步帶你裝好 MARKET_AI_HUB。
每一步都告訴你：**去哪、下載什麼、怎麼裝、怎麼確認成功、看到什麼才算成功**。

> 本文件用 `D:\MARKET_AI_HUB` 當範例路徑（不含任何個人名稱）。你可以換成自己的路徑。

---

## Step 0. 你需要什麼

- 一台 Windows 10/11 x64 電腦
- 網路連線
- 約 5 GB 磁碟空間（Python 環境 + 模型）

---

## Step 1. 安裝 Python 3.12

1. **去哪**：官方網站 <https://www.python.org/downloads/windows/>
2. **下載什麼**：`Python 3.12.x` 的 **Windows installer (64-bit)**
3. **怎麼裝**：
   - 執行安裝檔。
   - **務必勾選最下方的 `Add python.exe to PATH`**。
   - 點 `Install Now`。
4. **怎麼確認**：開一個**新的** PowerShell（開始選單搜尋 PowerShell），輸入：
   ```powershell
   python --version
   ```
5. **看到什麼才算成功**：`Python 3.12.x`。
   - 若顯示「找不到」，請關掉 PowerShell 再開一次；仍失敗代表 PATH 沒勾到，重裝並勾選。

---

## Step 2. 安裝 Git

1. **去哪**：官方網站 <https://git-scm.com/download/win>
2. **下載什麼**：`64-bit Git for Windows Setup`
3. **怎麼裝**：一路 Next（預設即可）。
4. **怎麼確認**：
   ```powershell
   git --version
   ```
5. **看到什麼才算成功**：`git version 2.x.x`。

---

## Step 3. Clone（下載）專案

```powershell
git clone https://github.com/<你的帳號>/market-ai-hub.git D:\MARKET_AI_HUB
cd D:\MARKET_AI_HUB
```

**看到什麼才算成功**：`cd` 後沒有錯誤，且 `dir` 能看到 `README.md`、`src`、`scripts` 等。

---

## Step 4. 一鍵安裝

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1 -WithDev
```

這個腳本會自動：檢查 Python → 建立 `.venv` → 安裝依賴 → 檢查 Torch/CUDA → 檢查 import。

**看到什麼才算成功**：最後顯示 `=== 安裝完成 ===`。

> 若出現紅色 `[FAIL] 找不到 Python`，回到 Step 1。
> 安裝依賴可能需數分鐘（會下載數百 MB）。

---

## Step 5. 下載模型

```powershell
D:\MARKET_AI_HUB\.venv\Scripts\python.exe scripts\download_models.py --download
```

**看到什麼才算成功**：`[OK] chronos-2`、`[OK] timesfm-3.0`，最後 `all models downloaded`。

> 需要約 1.7 GB。若出現 401/403，代表模型需要登入：
> 執行 `huggingface-cli login`（瀏覽器登入），**不要**把 token 貼進任何檔案。

---

## Step 6. 驗證安裝

```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify_install.ps1
```

**看到什麼才算成功**：最後一行是

```
INSTALLATION VERIFIED
```

若顯示 `FAIL`，會列出原因（例如模型沒下載、依賴缺漏），照原因處理後再跑一次。

---

## Step 7. 設定 Cherry Studio

照 [`CHERRY_STUDIO_SETUP.md`](CHERRY_STUDIO_SETUP.md) 做。重點：

- Type：`stdio`
- Command：`D:\MARKET_AI_HUB\.venv\Scripts\market-ai-mcp.exe`
- Args：留空

---

## Step 8. 確認可用

在 Cherry Studio 呼叫 `health_check`，看到 `"status": "ok"` 與正確的 `build_id` 即成功。

---

## Step 9. 跑測試（可選）

```powershell
D:\MARKET_AI_HUB\.venv\Scripts\python.exe -m pytest tests -q -m "not integration"
```

**看到什麼才算成功**：`passed`，0 failed。

---

## 完成後

- 更新程式：`git pull` 後重跑 Step 4，並**重啟 Cherry Studio 的 MCP**。
- 備份 / 還原：見 [`BACKUP_AND_RESTORE.md`](BACKUP_AND_RESTORE.md)。
- 問題排除：見 [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md)。
