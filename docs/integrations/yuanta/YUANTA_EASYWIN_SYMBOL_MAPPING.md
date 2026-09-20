# Yuanta EasyWin Symbol Mapping（Legacy Quote 商品代碼）

> 本文件為原創摘要，不複製 proprietary 原文件。

## 已驗證語義（2026-09-20，來自官方 `元大行情API.pdf`）
`AddMktReg(Symbol, UpdateMode)` 的 **Symbol 語義**：
- 證券類：**同 EASYWIN 證券報價代碼**
- 期貨類：**同 EASYWIN 期貨報價代碼**

→ Legacy Quote API 的期貨商品代碼 = **EASYWIN 期貨報價代碼**（非 SPARK StkCode、非下單代碼）。

## 尚未找到的
本機 Documents SDK（QuoteAPISDK / API_Yuanta2.1.2.7）**不含實際 EASYWIN 商品對照表**。
官方文件只說「同 EASYWIN 代碼」，未附對照檔。

**EASYWIN 商品對照表：UNRESOLVED**（需 EasyWin 程式匯出檔或向營業員索取）。

## 已知的三套商品代碼 namespace（禁止混用）
| API | 商品代碼來源 | OSE Micro 範例 |
|---|---|---|
| SPARK（證券+期貨） | FunctionList.xlsx 股票代碼總表 | 商品代碼 `JNU2609`，下單代碼 `JNU` |
| Legacy Quote（行情 API） | **EASYWIN 期貨報價代碼** | UNRESOLVED（本機 SDK 無對照表） |
| Legacy Trading（交易 API） | SendOrderF `FutNo`（如 `TXFD9`、`TXO04500E9`） | UNRESOLVED |

## 下一步可取得的證據（不自動執行）
- EasyWin 程式 → 期貨商品代碼匯出。
- 元大 MultiCharts QuoteManager → YuantaFutures Symbol List。
- 向營業員索取「期貨商品代碼對照表」。
