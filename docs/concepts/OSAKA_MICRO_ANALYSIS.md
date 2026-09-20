# Osaka Micro Analysis（大阪微型日經分析說明）

真正交易標的：**OSE Nikkei 225 Micro Futures**（`OSE_NIKKEI225_MICRO_FUTURES`）。

## 目標區分
| 名稱 | 角色 |
|---|---|
| OSE Nikkei 225 Micro Futures | **TARGET** |
| OSE Mini / Large / Nikkei Spot / TOPIX / SGX / CME | REFERENCE |
| ^N225 | PROXY |

## 資料語義（誠實標示）
- Micro 有官方 settlement / volume / OI，但**無官方 intraday OHLC** → `price_type=SETTLEMENT`。
- 不得虛構 Micro OHLC，不得把 ^N225 寫成 Micro 成交價。

## 分析流程（Skill 觸發）
1. `get_analysis_packet(market="osaka", target="OSE_NIKKEI225_MICRO_FUTURES")`。
2. packet 資料不足或需 audit 才呼叫個別 MCP。
3. 輸出白話結論：偏多/偏空/盤整 + 區間 + 支撐壓力 + 失效條件 + 何時重分析。

## 關鍵 MCP
- `get_analysis_packet`（主入口）
- `get_data_coverage`（覆蓋缺口）
- `get_event_calendar`（BOJ/Fed/CPI/NFP 等）
- `get_target_instrument_state`（真正標的狀態）

## 硬限制
- 不依賴 TradingView / Yuanta；兩者關閉時大阪分析仍可運作。
- 不得製造假 probability；ensemble 未 forward-validated 要標 UNVALIDATED_FORWARD。
