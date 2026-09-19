# CHERRY STUDIO 設定（MCP）

本文件教你如何在 Cherry Studio 加入 MARKET_AI_HUB 的 MCP server。
**所有路徑請換成你自己的實際路徑**（本文件用 `D:\MARKET_AI_HUB` 當範例，不含任何個人名稱）。

---

## 0. 前置條件

- 已依 `docs/INSTALL_WINDOWS.md` 安裝完成。
- 已下載模型：`D:\MARKET_AI_HUB\.venv\Scripts\python.exe scripts\download_models.py --download`
- 已驗證：`powershell -ExecutionPolicy Bypass -File scripts\verify_install.ps1` → `INSTALLATION VERIFIED`

先確認這個檔案存在：

```powershell
Test-Path "D:\MARKET_AI_HUB\.venv\Scripts\market-ai-mcp.exe"
```

應顯示 `True`。

---

## 1. 在 Cherry Studio 新增 MCP

1. 打開 Cherry Studio。
2. 左側最下方 → **設定**（齒輪）。
3. 左側選 **MCP 伺服器**（MCP Servers）。
4. 點 **新增伺服器 / Add Server**。
5. 依下表填入：

| 欄位 | 值 |
|------|-----|
| Name | `market-ai` |
| Type / 類型 | `stdio` |
| Command / 指令 | `D:\MARKET_AI_HUB\.venv\Scripts\market-ai-mcp.exe` |
| Args / 參數 | （留空） |
| Working directory | `D:\MARKET_AI_HUB`（若介面有此欄位才填） |
| Environment | 可留空；或加 `FINMIND_TOKEN`、`FRED_API_KEY`（值放你的免費 token） |

> **不要**把 token 寫進 command 或 args。若需要，用 Environment 欄位或 `.env`。

6. 儲存並**啟用**（打開開關）。
7. 稍等數秒，Cherry Studio 應顯示工具清單（13 個工具）。

### 關於 Python executable

- **建議**：Command 直接指向 `.venv\Scripts\market-ai-mcp.exe`（它會自動使用專案 venv 的 Python）。
- 若你的介面要求填 Python executable，填：
  `D:\MARKET_AI_HUB\.venv\Scripts\python.exe`
  並在 Args 填：
  `-m market_ai_hub.mcp.server`

---

## 2. 如何啟動

Cherry Studio 會在你啟用時自動以 stdio 啟動 server，不需要手動常駐。
手動測試（會等待輸入，Ctrl+C 結束）：

```powershell
D:\MARKET_AI_HUB\.venv\Scripts\market-ai-mcp.exe
```

---

## 3. 如何確認 health_check

在 Cherry Studio 對話中請 AI 呼叫 `health_check`，或在開發者工具查看工具輸出。預期：

```json
{
  "service": "market-ai-hub",
  "status": "ok",
  "cuda_available": true,
  "chronos": "ready",
  "timesfm": "ready",
  "build": { "build_id": "bbf3cb2f9a80d20e", ... }
}
```

---

## 4. 如何確認 build id

呼叫 `health_check` 或 `get_system_info`，看 `build.build_id`。
本 V1 Freeze 應為 `bbf3cb2f9a80d20e`。

若 build_id 與你剛安裝的版本不符 → **你正在用舊 process**（見下一節）。

---

## 5. ⚠️ MCP 是長駐 process：更新程式後一定要重啟

Cherry Studio 的 MCP server 是**長駐（long-running）process**。
它只在你「啟用 / 啟動」的那一刻載入程式碼；之後你改了檔案，**它不會自動重載**。

**症狀**：明明修好了 bug，Cherry Studio 仍出現舊行為（例如舊的錯誤、舊的 build_id）。

**解法**：在 Cherry Studio 把 `market-ai` MCP **關掉再打開**（或重啟 Cherry Studio），
讓它重新 spawn process，然後用 `health_check.build.build_id` 確認已載入新版本。

---

## 6. 常見錯誤

| 症狀 | 原因 / 解法 |
|------|------------|
| 工具清單是空的 / 連線失敗 | Command 路徑錯、`.venv` 未建、或未下載依賴。手動跑 `market-ai-mcp.exe` 看錯誤。 |
| `Tool Not Found` | MCP 未啟用，或該工具名稱拼錯。重啟 MCP。 |
| 回傳仍是舊行為 / build_id 不更新 | 長駐 process 持有舊 code → 關掉再打開 MCP。 |
| `chronos: unavailable` | 模型未下載 → 跑 `download_models.py --download`。 |
| 第一次呼叫很慢 | 模型首次載入（數十秒）；之後會快取。 |
| GPU OOM | 關閉其他佔用 GPU 的程式，或改用 CPU（移除 CUDA torch）。 |

更多：`docs/TROUBLESHOOTING.md`。
