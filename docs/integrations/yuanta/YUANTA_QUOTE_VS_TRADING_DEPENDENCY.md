# Yuanta Quote vs Trading API Dependency（行情 vs 交易相依性）

## 問題
「行情 API 是否需要 Trading API 同時建立/同時登入才能登入？」

## 答案：NO_RUNTIME_DEPENDENCY_FOUND（獨立）

## 證據（static audit，2026-09-19）
| 證據 | 內容 |
|---|---|
| 行情元件 | `YUANTAQUOTE.YuantaQuoteCtrl.1`（OCX），ProgID 獨立 |
| 交易元件 | `YuantaOrderAPI`（獨立 COM），Interop 獨立 DLL |
| Interop assemblies | `Interop.YuantaQuoteLib.dll` vs `Interop.YuantaOrderAPI.dll`（分開） |
| 官方 sample | Quote sample 只 instantiate `YuantaQuoteCtrl.1`，未建立/登入任何 Trading component |
| 登入方法 | Quote：`SetMktLogon`；Trading：獨立（FUTURE_RESEARCH_ONLY） |
| 事件 | Quote：`OnMktStatusChange` 等；Trading：獨立事件 |

## 結論
- 行情 API 登入**不依賴** Trading API。
- Trading API 是獨立產品（version 1.6.1.3），需獨立申請與憑證。
- 本棒未 instantiate trading control（FUTURE_RESEARCH_ONLY）。
