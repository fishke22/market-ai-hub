# 備份與還原（BACKUP AND RESTORE）

## 情境

假設 `D:\MARKET_AI_HUB` 整個消失、或換一台全新的 Windows 電腦，
你手上**只有這個 GitHub repository**。以下從零恢復到 MCP 可用的狀態。

---

## 從零還原（Step by Step）

### Step 1. 安裝 Git
- 官方：<https://git-scm.com/download/win>
- 確認：`git --version`

### Step 2. 安裝 Python 3.12 x64
- 官方：<https://www.python.org/downloads/windows/>
- 安裝時可勾 **Add python.exe to PATH**；但 MARKET_AI_HUB installer 不只相信 PATH，會實測 Python 版本與 64-bit pointer width。
- 只接受 CPython 3.11/3.12 64-bit；32-bit Python 會被拒絕。
- 可先用 `scripts\setup_windows.ps1 -BootstrapOnly` 做不下載依賴的新 venv 驗證。

### Step 3. Clone repository
```powershell
git clone https://github.com/<你的帳號>/market-ai-hub.git D:\MARKET_AI_HUB
cd D:\MARKET_AI_HUB
```

### Step 4. 一鍵安裝
先做無下載 bootstrap：
```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1 -BootstrapOnly
```
再做完整依賴安裝：
```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup_windows.ps1 -WithDev
```
若要先驗證 source checkout 搬到其他磁碟/中文空白路徑後不依賴舊 checkout，執行：
```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify_source_relocation_bootstrap.ps1
```
（完整安裝會連外抓依賴；無網路或未授權時只做 bootstrap。）

### Step 5. 下載模型
```powershell
D:\MARKET_AI_HUB\.venv\Scripts\python.exe scripts\download_models.py --download
```
- 會 pin V1 當時的 model revision 從官方 Hugging Face 下載。
- **若你在同一台機器已有 HF cache**，會直接重用，不需重下。

### Step 6. 驗證
```powershell
powershell -ExecutionPolicy Bypass -File scripts\verify_install.ps1
```
- 看到 `INSTALLATION VERIFIED` 即成功。

### Step 7. 設定 Cherry Studio
- 照 `docs/CHERRY_STUDIO_SETUP.md`。
- Command：`D:\MARKET_AI_HUB\.venv\Scripts\market-ai-mcp.exe`，Args 留空。

### Step 8. health_check
- 在 Cherry Studio 呼叫 `health_check`，確認 `status=ok` 且 `build_id` 正確。

### Step 9. 跑 tests（可選）
```powershell
D:\MARKET_AI_HUB\.venv\Scripts\python.exe -m pytest tests -q -m "not integration"
```

---

## GitHub 上「有」與「沒有」的東西

| 內容 | 在 GitHub？ | 說明 |
|------|-------------|------|
| 原始碼、測試、文件、腳本 | ✅ 有 | 完整可重建 |
| requirements lock | ✅ 有 | 精確依賴版本 |
| 模型 manifest | ✅ 有 | 下載方式與 revision |
| 模型 weights | ❌ 沒有 | 依 license，需自行下載 |
| `.venv` | ❌ 沒有 | 用 setup 重建 |
| 市場資料 / DuckDB / Parquet | ❌ 沒有 | 需重新抓取 |
| `.env` / token | ❌ 沒有 | 自行設定 |

**結論**：GitHub repo + 可取得的合法依賴來源足以重建 **core source/environment**；但不能據此宣稱完整功能已自動恢復。模型 weights、私人市場資料、WinCred、憑證、元大 proprietary SDK/COM、帳號 entitlement 與 Startup/排程都必須依各自流程重新取得/建立並分別驗收。`.venv` 不搬移，目的地重新建立。

---

## 離線備份（可選）

GitHub 不適合放模型 weights / 大量 wheels / 市場資料。使用：

```powershell
# 基本（source + lock + manifests）
powershell -ExecutionPolicy Bypass -File scripts\create_offline_backup.ps1 -Destination E:\MARKET_AI_BACKUP

# 連 Python wheels
... -Destination E:\MARKET_AI_BACKUP -IncludePythonPackages

# 連本地模型 cache
... -Destination E:\MARKET_AI_BACKUP -IncludeModels
```

- 會產生 `SHA256SUMS.txt` 供日後驗證完整性。
- 還原：把備份目錄內容複製回對應位置，或依 manifest 重新安裝。

> ⚠️ **本地私人備份 ≠ 公開重新散布。**
> TimesFM-3.0 / FinCast 的 weights 受非商業 / research-only 授權限制，
> 你的離線備份**僅供自用**，禁止公開分享或上傳到任何公開位置。

---

## 環境快照

```powershell
powershell -ExecutionPolicy Bypass -File scripts\export_environment.ps1
```

輸出到 `environment_export/`（預設不 commit；含本機路徑，分享前請自行檢視）。

---

## 資料備份（研究資料，非程式）

若你有重要的 DuckDB / Parquet 研究資料，請**自行**備份 `data/`（本專案不代管）。
這些檔案含 provider 資料，散布前請確認各來源條款。
