# Cherry Studio 新手教學

> 讓完全不懂的人，也能把 MARKET_AI_HUB 接到 Cherry Studio，用「問一句話」的方式使用。

---

## 1. Cherry Studio 是什麼？

一個桌面 AI 對話軟體。你可以在裡面選各種 AI 模型，跟它們對話。

MARKET_AI_HUB 是它的「外掛工具」，讓 AI 能查金融資料、跑模型。

## 2. 安裝

1. 先確認 MARKET_AI_HUB 已安裝（見 [INSTALL_WINDOWS.md](INSTALL_WINDOWS.md)）。
2. 下載並安裝 [Cherry Studio](https://cherrystudio.app/)。
3. 開啟 Cherry Studio。

## 3. 連線（設定 MCP）

在 Cherry Studio 的 MCP 設定，加入下面這段 JSON。

> 把 `<ProjectRoot>` 換成你的專案資料夾路徑（例如 `D:\MARKET_AI_HUB`）。
> **不要放任何真實帳號、密碼、token。**

```json
{
  "mcpServers": {
    "market-ai": {
      "command": "<ProjectRoot>\\.venv\\Scripts\\market-ai-mcp.exe",
      "args": []
    }
  }
}
```

- `command`：啟動 MARKET_AI_HUB 的 MCP server 的程式。
- `args`：空的（不用額外參數）。
- working directory：預設即可，通常不需要特別設。

## 4. 測試有沒有連上

連線成功後，在 Cherry Studio 對話裡問：

> 幫我查一下系統健康狀態。

如果看到類似下面的回覆，就是成功了：

- 系統 build_id（一串 16 位英數字）
- MCP 有 21 個工具
- Live trading = PROHIBITED（禁止交易）

## 5. 常見錯誤

| 問題 | 原因 | 解法 |
|------|------|------|
| 找不到 market-ai-mcp.exe | 路徑打錯 | 確認 `<ProjectRoot>` 換成正確資料夾 |
| 顯示「連線失敗」 | Python 環境沒裝好 | 重新跑 setup（見 INSTALL_WINDOWS） |
| 一直轉圈 | MCP server 沒啟動 | 檢查 Cherry Studio 的 MCP 狀態燈 |

## 6. 可以直接複製的問題

| 你想問 | 複製這句 |
|--------|---------|
| 分析大阪日經 | 「幫我分析今天大阪日經。」 |
| 資料新不新 | 「今天資料是不是最新的？」 |
| 哪些模型值得參考 | 「目前哪些模型值得參考？」 |
| 有沒有交易證據 | 「現在有沒有可以交易的證據？」 |
| 模型有沒有失準 | 「模型最近有沒有失準？」 |
| Forward Shadow 進度 | 「Forward Shadow 現在累積多少筆？」 |
| 要不要訓練 | 「今天需不需要訓練？」 |
| 白話解釋 | 「請用完全不懂金融 AI 的方式解釋。」 |

## 7. 不用記工具名稱

一般使用者**不需要記 21 個 MCP tools**。AI 會依你的問題自動呼叫對的工具。

只有技術使用者才需要看 [MCP_TOOL_REFERENCE.md](MCP_TOOL_REFERENCE.md)。

## 8. 進階：System Prompt

一般使用者**不需要自己設定** System Prompt。

技術使用者若想讓 AI 遵守更嚴謹的金融分析規則，推薦用精簡版：
目前 CherryStudio `market-ai` Agent 建議直接貼用 [`prompts/CHERRYSTUDIO_MARKET_AI_AGENT_2026-09-26.md`](../prompts/CHERRYSTUDIO_MARKET_AI_AGENT_2026-09-26.md)。完整通用規則仍可參考 [`prompts/SYSTEM_PROMPT_V4_1_COMPACT.md`](../prompts/SYSTEM_PROMPT_V4_1_COMPACT.md)。

完整政策參考（Advanced）見 [`prompts/SYSTEM_PROMPT_V4_PHASE2_RC1.md`](prompts/SYSTEM_PROMPT_V4_PHASE2_RC1.md)。
