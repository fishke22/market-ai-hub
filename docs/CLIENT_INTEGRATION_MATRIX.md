# Client Integration Matrix

| Client | Status | 說明 |
|---|---|---|
| Cherry Studio | **TESTED** | 用 `examples/mcp/cherry-studio.json` + Skills |
| Generic stdio MCP Host | **TESTED** | 用 `examples/mcp/generic-stdio.json` |
| Codex / OpenCode 類 coding agent | **REFERENCE_ONLY** | 以 `docs/AI_RECONSTRUCTION_GUIDE.md` 引導；未實測其 MCP 設定 |
| 其他（Claude Desktop / Cursor / 其他） | **REFERENCE_ONLY** | 只寫已知能力，未假裝跨平台全實測 |

## 狀態語義
- `TESTED`：已實際驗證。
- `REFERENCE_ONLY`：提供範本，未實測。
- `UNSUPPORTED`：明確不支援。

## 通用 MCP 設定
```json
{ "mcpServers": { "market-ai": {
  "command": "python", "args": ["-m", "market_ai_hub.mcp.server"]
} } }
```
