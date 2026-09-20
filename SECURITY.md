# Security

## 明確界線
- **NO LIVE TRADING**：本系統不做即時交易、不下單。
- **NO ORDER MCP**：MCP 不暴露任何下單、改單、撤單、帳戶、倉位工具。
- **NO BROKER CREDENTIAL IN REPO**：不存放 Yuanta 帳號/密碼、憑證、PFX、Windows credential export。

## Secret scan 目標
- API keys（FRED / FinMind / BEA / e-Stat / EIA / EDINET / HF）
- tokens
- Yuanta account / password
- certificate / PFX / PEM / CRT
- Windows credential export

檢查範圍：Git history、working tree、generated docs、test artifacts、logs。

## 不得提交 Git
- 真實市場 licensed data
- model weights / checkpoints
- API keys / tokens / credentials
- local DB（*.duckdb / *.sqlite / *.db）
- mlruns / private logs
- 分析 archive

## Yuanta / TradingView
- Yuanta：`RESERVED_QUOTE_ONLY`，realtime recorder = false。
- TradingView：`OPTIONAL`，不取得 cookie / password / session secret。

## Data provenance
- authoritative（JPX/BLS/Cboe/EDGAR/BOJ）與 proxy（yfinance/^N225）分離。
- settlement ≠ live close；不得把 proxy 冒充官方 Micro 成交價。
