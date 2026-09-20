# 通用 MCP Client 設定

MARKET_AI_HUB 是一個 **stdio MCP Server**。只要你的 AI Client / Agent 能啟動本機 stdio MCP process，就可以使用；不限定 Cherry Studio。

> 本文件只說明 MARKET_AI_HUB 這個 MCP Server 需要什麼。不同 Client 的設定畫面與 JSON 格式可能不同，請把相同的 `command / args / working directory` 對應到你的 Client 即可。

---

## 1. 前置條件

先完成：

1. [`INSTALL_WINDOWS.md`](INSTALL_WINDOWS.md)
2. 模型下載
3. 安裝驗證

範例專案路徑：

```text
D:\MARKET_AI_HUB
```

確認 MCP executable 存在：

```powershell
Test-Path "D:\MARKET_AI_HUB\.venv\Scripts\market-ai-mcp.exe"
```

應回：

```text
True
```

---

## 2. 最小設定

你的 MCP Client 需要啟動：

```text
Transport: stdio
Command: D:\MARKET_AI_HUB\.venv\Scripts\market-ai-mcp.exe
Args: []
Working directory: D:\MARKET_AI_HUB
```

`Working directory` 如果 Client 沒有這個欄位，可以不填。

### 典型 JSON 概念

不同 Client 格式會不同，但概念通常類似：

```json
{
  "mcpServers": {
    "market-ai": {
      "command": "D:\\MARKET_AI_HUB\\.venv\\Scripts\\market-ai-mcp.exe",
      "args": []
    }
  }
}
```

請不要照抄到不相容的 Client；以該 Client 的 MCP 設定格式為準。

---

## 3. 不想使用 console script 時

也可以直接透過專案 venv 的 Python 啟動：

```text
Command:
D:\MARKET_AI_HUB\.venv\Scripts\python.exe

Args:
-m
market_ai_hub.mcp.server
```

兩種方式本質相同；建議優先使用：

```text
market-ai-mcp.exe
```

比較簡單。

---

## 4. 啟動後應該看到的 tools

Phase 2（v2.0.0-rc1）暴露 21 個 tools：

```text
health_check
get_system_info
get_research_gates
get_data_source_status
get_market_data
predict_chronos
predict_timesfm
predict_ensemble
get_model_performance
backtest
run_ts_validation
analyze_osaka_nikkei
analyze_taiwan_stock
get_analysis_packet
get_data_coverage
get_event_calendar
get_official_release_snapshot
get_target_instrument_state
get_model_leaderboard
get_forward_test_status
get_analysis_archive_status
```

如果 Client 支援 MCP tool discovery，連線成功後應能看到這些工具。

---

## 5. 第一個建議測試

請在 Client 裡對 AI 說：

```text
請先呼叫 market-ai 的 health_check，不要分析市場。告訴我：
1. service 是否正常
2. build_id
3. Chronos / TimesFM 是否 ready
4. CUDA 是否可用
5. 哪些資料來源需要設定
```

Phase 2（v2.0.0-rc1）的 build_id：

```text
ccabe1e1552d9ae7
```

如果你使用的是更新後 main branch，build_id 可能因正式程式碼改動而不同；這時應以同一次 runtime 回傳的一致 build_id 為準。

---

## 6. MCP 是長駐 process

這點非常重要。

AI Client 通常會啟動一個長駐的：

```text
market-ai-mcp.exe
```

當你更新 MARKET_AI_HUB 程式碼後，舊 process **不會自動重新載入**。

所以更新後必須：

1. 停用 / 關閉 `market-ai` MCP。
2. 再重新啟用。
3. 呼叫 `health_check`。
4. 確認 build_id 是新版本。

否則很容易發生：

> 「明明程式修好了，AI 還是在跑舊行為。」

---

## 7. Token / API key

V1 可選資料來源可能需要：

```text
FINMIND_TOKEN
FRED_API_KEY
HF_TOKEN（只有特定 Hugging Face 情況需要）
```

原則：

- 不要把 token 寫在聊天 Prompt。
- 不要把 token 寫在 MCP command / args。
- 不要提交 GitHub。
- 使用 Client 提供的安全 Environment 設定，或你自己的本機 secret 管理方式。

如果沒有 FinMind / FRED key，MARKET_AI_HUB 不會整套停止，只會將相關 provider 標為 `needs_config`。

---

## 8. Client 需要具備什麼能力？

最低條件：

- 能啟動 local process。
- 支援 MCP stdio transport。
- 能做 MCP tool discovery。
- 能讓 LLM 呼叫 tool 並讀取 JSON 結果。

如果 Client 只能連 remote HTTP MCP，而不能執行本機 stdio server，就不能直接照本文件設定；需要另外加一層 MCP transport bridge。V1 沒有內建這個 bridge。

---

## 9. Cherry Studio

Cherry Studio 是已實測的一個 Client 範例。

設定步驟見：

[`CHERRY_STUDIO_SETUP.md`](CHERRY_STUDIO_SETUP.md)

但 MARKET_AI_HUB 本身不依賴 Cherry Studio。

---

## 10. Agent Prompt

MCP 只提供工具，不會強制你的 AI 用哪種分析流程。

如果希望 AI 遵守比較嚴謹的金融分析規則，可以參考：

- [`prompts/SYSTEM_PROMPT_V4_1_COMPACT.md`](prompts/SYSTEM_PROMPT_V4_1_COMPACT.md)（**推薦**，適合長期常駐）
- [`prompts/QUICK_PROMPTS.md`](prompts/QUICK_PROMPTS.md)
- [`prompts/SYSTEM_PROMPT_V4_PHASE2_RC1.md`](prompts/SYSTEM_PROMPT_V4_PHASE2_RC1.md)（完整政策參考 / FULL REFERENCE）
- [`prompts/SYSTEM_PROMPT_V3_3_REFERENCE.md`](prompts/SYSTEM_PROMPT_V3_3_REFERENCE.md)（歷史 / 相容性參考，已 deprecate）

也可以完全不用這份 System Prompt，直接由你自己的 Agent / workflow 呼叫 MCP tools。

---

## 11. 常見問題

### 工具沒有出現

先手動執行：

```powershell
D:\MARKET_AI_HUB\.venv\Scripts\market-ai-mcp.exe
```

如果立即報錯，先處理 Python / dependency 問題。

### AI 說 tool not found

先確認 Client 的 MCP 連線是否啟用，再確認 tool 真實名稱。

### 模型第一次很慢

Chronos / TimesFM 第一次載入模型需要時間，後續同 process 通常會比較快。

### GPU 不夠

可以使用 CPU；功能仍可執行，只是較慢。

### 回傳資料太舊

先看：

```text
freshness_status
quote_live
usable_for_live_decision
```

不要只看 timestamp 就假設行情是 live。

更多問題：[`TROUBLESHOOTING.md`](TROUBLESHOOTING.md)
