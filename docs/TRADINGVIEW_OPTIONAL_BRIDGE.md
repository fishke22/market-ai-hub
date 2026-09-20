# TradingView Optional Bridge（設計 + 實機驗證）

> **非 TradingView 官方 integration**。本機 TradingView Desktop 為**免費方案**。
> 本文件記錄實機驗證結果與安全界線。

## 定位
`OPTIONAL_RESEARCH_TOOL`。TradingView 未開 → MARKET_AI_HUB 仍正常（不 BLOCK 核心分析）。

## 實機驗證結果（2026-09-19）

| 項目 | 結果 |
|---|---|
| Upstream commit | `c05b8f5755ed8e64ea242de88ddbf46aa24d56a4`（tradesdontlie/tradingview-mcp，MIT） |
| Node / npm | v24.16.0 / 11.13.0（需 18+） |
| TradingView Desktop | 3.4.0.8149（MSIX，`WindowsApps\TradingView.Desktop_3.4.0.8149`） |
| CDP launch | ✅ `--remote-debugging-port=9222`，localhost only |
| CDP security | ✅ bind 127.0.0.1，未開 0.0.0.0/LAN |
| Chart read | ✅ `chart_symbol = OSE_DLY:NK225MC1!`，resolution 15 |
| OSE contract chain | ✅ Micro=`OSE:NK225MC1!`(×10) / Mini=`OSE:NK225M1!`(×100) / Large=`OSE:NK2251!`(×1000) |
| Quote / OHLCV snapshot | ✅ Micro OHLCV（open 65345/high 65660/low 64585/close 64895/vol 358851） |
| Screenshot | ✅ 251KB PNG（chart region） |
| **Delay** | ⚠️ **DELAYED 900s（15 分鐘）**，guest mode，非 realtime |

## 免費方案 capability matrix
| 能力 | 狀態 |
|---|---|
| chart_get_state / chart read | AVAILABLE |
| symbol metadata（OSE Micro/Mini/Large） | AVAILABLE |
| quote / OHLCV summary | AVAILABLE_DELAYED（900s） |
| screenshot | AVAILABLE |
| indicator read | PLAN_LIMITED（未逐項實測，標未確認） |
| Pine / Strategy Tester | PLAN_LIMITED（免費方案可能受限，未實測） |
| Replay | NOT_TESTED |
| replay_trade / alert / watchlist / broker | **禁止測試** |

## 禁止（即使 upstream 提供）
`place_order` / `broker_login` / `replay_trade` / `alert_create` / `watchlist mutation` /
`ui_evaluate` / arbitrary JavaScript。MARKET_AI_HUB 不暴露這些。

## 資料語義
TradingView 取得的 quote/OHLCV/indicator → `source = TRADINGVIEW_OPTIONAL_UI`、
`authority = OPTIONAL_EXTERNAL_UI_SOURCE`。不得自動寫入 authoritative training dataset。

## 安裝 / 啟動
1. `git clone https://github.com/tradesdontlie/tradingview-mcp external/tradingview-mcp`
2. `cd external/tradingview-mcp && npm install`
3. 啟動 TradingView：`tv_launch`（auto-detect MSIX）或手動 `--remote-debugging-port=9222`
4. 啟動 MCP：`node external\tradingview-mcp\src\server.js`

## Cherry Studio 兩種模式
- **MODE A（Recommended）**：只連 `market-ai`。
- **MODE B（Advanced）**：同時連 `market-ai` + `tradingview`（`examples/mcp/tradingview-optional.json`）。
  警告：TradingView MCP tools 多，增加 context noise。

## 故障排除
| 症狀 | 處理 |
|---|---|
| `cdp_connected: false` | 未開 `--remote-debugging-port=9222` |
| `ECONNREFUSED` | TradingView 未跑或 port 被擋 |
| WindowsApps "Access is denied" | 用 `tv_launch`（auto copy-fallback），不要 icacls |

## 版本 pinning
見 `config/integrations.yaml`。upstream 改版 → 重新 smoke test，不自動 pull latest。
