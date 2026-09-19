# LICENSE_MATRIX — 模型與套件授權矩陣

| 元件 | 來源 | 授權 | 可否商業使用 | 標籤 |
|------|------|------|--------------|------|
| chronos-forecasting (套件) | PyPI `chronos-forecasting` | Apache-2.0 | 是 | — |
| amazon/chronos-2 (weights) | Hugging Face `amazon/chronos-2` | Apache-2.0 | 是 | — |
| timesfm (套件 3.0.x) | PyPI `timesfm`，repo `google-research/timesfm` | Apache-2.0 (source code) | code 是 | — |
| **google/timesfm-3.0-pytorch (weights)** | Hugging Face `google/timesfm-3.0-pytorch` | **timesfm-non-commercial-license-v1.0** | **否** | **TIMESFM3_NON_COMMERCIAL_ONLY** |
| scikit-learn / xgboost / lightgbm | PyPI | BSD-3 / Apache-2.0 / MIT | 是 | — |
| FinCast (`Vincent05R/FinCast`) | HF / GitHub `vincent05r/FinCast-fts` | Apache-2.0 (repo)，README 標示 research/education | 研究/教育用途 | OPTIONAL |
| mcp (Python SDK) | PyPI `mcp` | MIT | 是 | — |
| duckdb / pyarrow | PyPI | MIT / Apache-2.0 | 是 | — |

## 重要

- **TimesFM 3.0 pretrained weights 只能用於 non-commercial / non-production / testing / research / evaluation。**
  本專案所有 TimesFM 輸出都帶 `TIMESFM3_NON_COMMERCIAL_ONLY` warning。
  不得把 TimesFM 3 宣稱為可商業部署模型。
- 本系統整體為研究用途；不含交易/下單功能。
