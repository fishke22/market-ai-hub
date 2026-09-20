# MCP JSON 設定範例

## 檔案
- `generic-stdio.json` — 通用 stdio MCP host（只連 market-ai）
- `cherry-studio.json` — Cherry Studio（只連 market-ai）
- `tradingview-optional.json` — **MODE B（Advanced）**：同時連 market-ai + tradingview MCP

## 兩種模式（Cherry Studio）
- **MODE A — Recommended**：只連 `market-ai`。MARKET_AI_HUB backend 自行 optional 呼叫 bridge adapter。
- **MODE B — Advanced**：同時連 `market-ai` + `tradingview`。
  警告：TradingView MCP 有大量 tools，可能增加 context/tool-selection noise。預設推薦 MODE A。

## 改路徑
把 `<PROJECT>` 換成實際專案路徑（如 `D:\\MARKET_AI_HUB`）。

## 用 python -m 替代 exe
```json
{ "mcpServers": { "market-ai": { "command": "python", "args": ["-m", "market_ai_hub.mcp.server"] } } }
```

## 安全
JSON 不含 API token / cookie / password / broker 帳號。TradingView 是 OPTIONAL，market-ai 是核心。
