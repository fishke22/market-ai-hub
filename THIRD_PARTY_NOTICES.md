# Third-Party Notices

Code license 與 Model weights license 分開。

## Code（本 repository 原始碼）
- **Apache-2.0**（見 `LICENSE`）。

## Model weights license（與 code 分開）
| Model | Provider | Weights license | Redistributable | Required |
|---|---|---|---|---|
| chronos-2 | Amazon | Apache-2.0 | yes | true |
| timesfm-3.0 | Google | timesfm-non-commercial-license-v1.0 | no（research only） | true |
| xgboost | — | Apache-2.0（code/lib） | — | true |
| lightgbm | Microsoft | MIT（code/lib） | — | true |
| nhits / nbeatsx | neuralforecast | Apache-2.0（code） | — | true（fit-on-the-fly） |
| FinCast | Vincent05R | Apache-2.0（repo）；README 標 research/education | no | false（optional） |
| Moirai-2 | Salesforce | CC-BY-NC-4.0 | no（non-commercial） | false（未建 adapter） |
| TTM | IBM | Apache-2.0 | — | false（torch 衝突） |

## Optional integrations
- TradingView MCP（`tradesdontlie/tradingview-mcp`）：OPTIONAL，未安裝。
- Yuanta：`RESERVED_QUOTE_ONLY`，未啟用。

## 重要提醒
- TimesFM-3.0 / Moirai-2 / FinCast 的 **weights 不得商業部署或再散布**。
- 本 repository **不含任何 model weights**（見 `.gitignore`）。
