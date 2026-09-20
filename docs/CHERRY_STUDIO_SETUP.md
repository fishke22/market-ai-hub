# Cherry Studio 設定範例（MCP）

> MARKET_AI_HUB **不是 Cherry Studio 專用**。它是一個 stdio MCP Server；本文件只是示範如何在 Cherry Studio 這個 MCP Client 中接入。
>
> 其他 MCP Client 請先看通用文件：[`MCP_CLIENT_SETUP.md`](MCP_CLIENT_SETUP.md)。

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

> **不要**把 token 寫進 command、args 或聊天 Prompt。

6. 儲存並**啟用**（打開開關）。
7. 稍等數秒，Cherry Studio 應顯示工具清單（Phase 2 v2.0.0-rc1 為 21 個 tools）。

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

在 Cherry Studio 對話中請 AI 呼叫 `health_check`，或在開發者工具查看工具輸出。預期類似：

```json
{
  "service": "market-ai-hub",
  "status": "ok",
  "cuda_available": true,
  "chronos": "ready",
  "timesfm": "ready",
  "build": { "build_id": "ccabe1e1552d9ae7" }
}
```

---

## 4. 如何確認 build id

呼叫 `health_check` 或 `get_system_info`，看 `build.build_id`。

Phase 2（v2.0.0-rc1）：

```text
ccabe1e1552d9ae7
```

若你使用後續版本，build_id 可能不同；重點是同一個 runtime 的 tools 必須回傳一致版本。

---

## 5. MCP 是長駐 process：更新程式後一定要重啟

Cherry Studio 啟動的 MCP server 是長駐 process。
它只在啟動時載入程式碼；你後來改了檔案，它**不會自動 reload**。

症狀：

> 程式明明更新了，但 AI 還在回舊行為或舊 build_id。

解法：

1. 在 Cherry Studio 關閉 `market-ai` MCP。
2. 再重新啟用。
3. 呼叫 `health_check`。
4. 確認 build_id。

---

## 6. 建議第一個 Prompt

```text
先不要分析市場。
請呼叫 market-ai 的 health_check、get_system_info 與 get_research_gates。
告訴我 MCP 是否正常、目前 build_id、哪些模型 ready、哪些 Research Gate 已通過，以及哪些能力尚未被證明。
```

更多範例：[`prompts/QUICK_PROMPTS.md`](prompts/QUICK_PROMPTS.md)

完整 Agent 行為參考（推薦）：[`prompts/SYSTEM_PROMPT_V4_PHASE2_RC1.md`](prompts/SYSTEM_PROMPT_V4_PHASE2_RC1.md)

（歷史 / 相容性參考：[`prompts/SYSTEM_PROMPT_V3_3_REFERENCE.md`](prompts/SYSTEM_PROMPT_V3_3_REFERENCE.md)）

---

## 7. 常見錯誤

| 症狀 | 原因 / 解法 |
|------|------------|
| 工具清單是空的 / 連線失敗 | Command 路徑錯、`.venv` 未建、或未安裝依賴。手動跑 `market-ai-mcp.exe` 看錯誤。 |
| `Tool Not Found` | MCP 未啟用，或 tool 名稱拼錯。重啟 MCP。 |
| 回傳仍是舊行為 / build_id 不更新 | 長駐 process 持有舊 code → 關掉再打開 MCP。 |
| `chronos: unavailable` | 模型未下載 → 跑 `download_models.py --download`。 |
| 第一次呼叫很慢 | 模型首次載入；後續同 process 通常會快很多。 |
| GPU OOM | 關閉其他佔用 GPU 的程式，或使用 CPU。 |

更多：[`TROUBLESHOOTING.md`](TROUBLESHOOTING.md)
