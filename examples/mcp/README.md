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
template 內的 `<PROJECT>` 只作人類可讀 placeholder。正式重建/搬移請不要手改，改用：
```powershell
python scripts\render_mcp_config.py --client generic --require-command
python scripts\render_mcp_config.py --client cherry --require-command
```
需要檔案時再加 `--output <path>`；產生器不會自動寫入任何第三方 client 設定。

## 用 python -m 替代 exe
```json
{ "mcpServers": { "market-ai": { "command": "python", "args": ["-m", "market_ai_hub.mcp.server"] } } }
```

## 安全
JSON 不含 API token / cookie / password / broker 帳號。TradingView 是 OPTIONAL，market-ai 是核心。
