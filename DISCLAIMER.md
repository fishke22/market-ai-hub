# 免責聲明（DISCLAIMER）

## 研究用途

MARKET_AI_HUB 是一套**金融市場研究與預測工具**，用途為研究、教育與個人分析。
它**不是**投資建議、不是交易系統、不是理財顧問。

## 非投資建議

本系統輸出的任何數字、方向、信心、機率或分析，**都不構成投資建議**。
你不應依據本系統的任何輸出做出投資決策。

## 模型可能錯誤

- 所有模型都可能出錯，且**經常會錯**。
- 時間序列基礎模型（Chronos-2 / TimesFM-3.0）在本專案中
  **尚未通過完整 out-of-sample 驗證**（`predictive_validation_status = UNVALIDATED`）。
- 分類器的機率**未經 calibration**（`probability_calibrated = false`），
  不得將「class_1 = 0.84」解讀為「84% 上漲機率」。
- 資料可能有延遲、缺漏、錯誤或來源中斷。

## 過去績效不保證未來

任何回測、歷史統計或績效數字**不代表未來結果**。市場條件會改變，模型可能失效。

## 目前不包含自動下單

本系統**沒有**券商登入、**沒有**下單、**沒有**資金操作、**沒有**即時交易執行能力。
所有輸出僅供研究參考。

## Research Gates 現狀

- `ENGINEERING_GATE`：已通過（工程正確性）。
- `MODEL_PREDICTIVE_GATE`：**UNPROVEN**。
- `TRADING_EDGE_GATE`：**UNPROVEN**。

**V1 Freeze 代表工程與正確性凍結，不代表模型已證明有預測力或交易優勢。**

## 資料來源限制

- 大阪日經目前使用 ^N225 現貨指數**代理**（RESEARCH_PROXY / DELAYED），
  不是 OSE 微型期貨即時行情。
- Yahoo Finance（yfinance）為 unofficial wrapper，非機構級資料 API。
- 使用本系統時，請自行遵守各資料來源（TWSE / FinMind / FRED / Yahoo）之服務條款。
