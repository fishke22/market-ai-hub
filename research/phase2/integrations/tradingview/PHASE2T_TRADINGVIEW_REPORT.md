# Phase 2T — TradingView Optional Bridge Real-Machine Validation

- Gate: **PHASE2T_PASS**
- build_id：`ccabe1e1552d9ae7`（未變，本棒未改 fingerprinted 檔）
- 測試：**365 passed**（356 + 9 2T；5 live deselected）

## 1. Upstream commit
- repo：`https://github.com/tradesdontlie/tradingview-mcp`
- commit：`c05b8f5755ed8e64ea242de88ddbf46aa24d56a4`
- LICENSE：MIT（Copyright 2026 tradesdontlie）；TradingView data/software 不屬此 MIT。

## 2. Node / npm
- node v24.16.0、npm 11.13.0（要求 18+，PASS）。

## 3. TradingView Desktop version
- 3.4.0.8149（MSIX，`C:\Program Files\WindowsApps\TradingView.Desktop_3.4.0.8149_x64__...`）。

## 4. CDP localhost security
- `tv_launch` 成功開 `--remote-debugging-port=9222`，bind 127.0.0.1（未開 0.0.0.0/LAN，無 public inbound rule）。

## 5. 免費方案 capability matrix（實測）
| 能力 | 狀態 |
|---|---|
| chart state read | **AVAILABLE**（OSE_DLY:NK225MC1!，res 15） |
| symbol metadata | **AVAILABLE**（OSE contract chain） |
| quote / OHLCV summary | **AVAILABLE_DELAYED**（900s） |
| screenshot | **AVAILABLE**（251KB PNG） |
| indicator read | PLAN_LIMITED（未逐項確認） |
| Pine / Strategy Tester | PLAN_LIMITED（免費方案可能受限） |
| Replay | NOT_TESTED |

## 6. Nikkei symbol map（`TRADINGVIEW_SYMBOL_MAP.json`）
- OSE Micro = `OSE:NK225MC1!`（×10）✅ verified
- OSE Mini = `OSE:NK225M1!`（×100）✅ verified
- OSE Large = `OSE:NK2251!`（×1000）✅ verified
- Nikkei Spot / CME / SGX = **NOT_VERIFIED**（不猜 ticker）
- 免費方案 = DELAYED 15 分鐘（delayed_streaming_900），非 realtime。

## 7–16. 能力摘要
- chart read ✅、quote ✅（delayed）、OHLCV ✅（delayed）、screenshot ✅
- indicator / Pine / Strategy Tester / Replay：PLAN_LIMITED / NOT_TESTED（免費方案，未宣稱可用）
- replay_trade / alert / watchlist / broker：**禁止測試**（未碰）

## 16–21. MARKET_AI_HUB bridge / config / scripts
- `config/tradingview.yaml`：`enabled=false`（預設），capabilities whitelist（order_execution=false、arbitrary_ui_eval=false）。
- `config/integrations.yaml`：upstream version pinning（commit SHA + tested date）。
- `integrations/tradingview_bridge.py`：whitelisted `TradingViewResearchBridge`（無 place_order/ui_evaluate）。
- `integrations/cross_check.py`：`TradingViewCrossCheck`（MATCH/MINOR_DIFFERENCE/CONFLICT/UNAVAILABLE，永不覆蓋官方）。
- `scripts/start_tradingview_bridge.ps1` / `check_tradingview_bridge.ps1`（manual opt-in，無開機自動啟動）。
- `examples/mcp/tradingview-optional.json`（MODE B）+ README（MODE A recommended）。

## 18. Tests（9 新增 unit，不需實機）
tradingview_disabled_by_default / tradingview_optional_failure / tradingview_no_core_dependency /
tradingview_source_semantics / tradingview_no_order_methods / tradingview_no_arbitrary_eval /
tradingview_config_validation / tradingview_symbol_map_schema / crosscheck_does_not_override_authoritative。

## 19. Blockers
- 無。TradingView 免費方案為 DELAYED（15 分鐘），非 realtime → 只作 OPTIONAL RESEARCH，不作核心 data source。
- indicator / Pine / Strategy Tester / Replay 未逐項實測（免費方案可能受限），標 PLAN_LIMITED/NOT_TESTED，未假稱可用。

## 20. Final recommendation
- **MODE A（Recommended）**：只連 `market-ai` MCP；TradingView 保持 OPTIONAL。
- TradingView 關閉時 `get_analysis_packet` 正常（`test_tradingview_no_core_dependency`）。
- 免費方案資料為 DELAYED，不得當 realtime quote 或 authoritative training data。

## 驗證
- `pytest tests/ -q` → 365 passed
- 實機：`tv_launch` 成功、`tv_health_check` cdp_connected=true、chart symbol/quote/ohlcv/screenshot 讀取成功
- build_id 維持 `ccabe1e1552d9ae7`
