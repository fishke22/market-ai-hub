# THIRD_PARTY_NOTICES

本 repository 公開可讀，但**專案自身授權尚未另行指定**（未附 LICENSE）。
下列第三方元件仍依各自授權條款使用；**模型權重不隨本 repository 散布**。

> ⚠️ 「Repository 公開」≠「第三方模型權重可以重新發布」。
> 嚴禁把任何模型 weights / checkpoint 放入本 repository 或公開發布。

---

## 一、模型（weights 需自行下載）

| 模型 | 上游 repository | revision | 授權 | 可重新散布 weights | 下載方式 |
|------|-----------------|----------|------|-------------------|----------|
| Chronos-2 | https://huggingface.co/amazon/chronos-2 | `29ec3766d36d6f73f0696f85560a422f50e8498c` | Apache-2.0 | 是（本專案仍不散布） | `scripts/download_models.py --download` |
| TimesFM-3.0 | https://huggingface.co/google/timesfm-3.0-pytorch | `43046b85ec22d584a13f8098c2ed39c889e129c2` | **timesfm-non-commercial-license-v1.0** | **否** | 同上 |
| FinCast（可選） | https://huggingface.co/Vincent05R/FinCast | `2d7d90b159db8961d27c2cf165d51195902ef92b` | Apache-2.0（repo）；README 標示 research/education | **否**（本專案不散布） | 同上（另需 git clone `vincent05r/FinCast-fts`） |

### 模型授權重點

- **TimesFM-3.0 weights：非商業授權**，僅限 research / evaluation / non-commercial。
  本專案所有 TimesFM 輸出都帶 `TIMESFM3_NON_COMMERCIAL_ONLY` 標記。**不得商業部署。**
- Chronos-2 weights 為 Apache-2.0，但本專案仍不將 weights 放入 GitHub。
- FinCast 官方 README 標示 research / educational purposes only。

---

## 二、核心 Python 套件

| 套件 | V1 版本 | 用途 | 授權 |
|------|---------|------|------|
| torch | 2.14.0+cu130 | 深度學習推論 | BSD-3-Clause |
| transformers | 5.17.0 | 模型載入 | Apache-2.0 |
| huggingface-hub | 1.32.0 | 模型下載 | Apache-2.0 |
| chronos-forecasting | 2.3.2 | Chronos-2 推論 | Apache-2.0 |
| timesfm | 3.0.2 | TimesFM-3 推論 | Apache-2.0（source）；weights 非商業 |
| scikit-learn | 1.9.1 | 傳統 ML | BSD-3-Clause |
| xgboost | 3.4.1 | 分類器 | Apache-2.0 |
| lightgbm | 4.7.0 | 分類器 | MIT |
| pandas | 3.0.6 | 資料處理 | BSD-3-Clause |
| numpy | 2.5.3 | 數值運算 | BSD-3-Clause |
| duckdb | 1.5.5 | 本地儲存 | MIT |
| pyarrow | 25.0.1 | Parquet | Apache-2.0 |
| exchange-calendars | 4.13.2 | 交易所日曆（XTAI/XTKS） | Apache-2.0 |
| pandas-market-calendars | 5.4.0 | 日曆工具 | Apache-2.0 |
| yfinance | 1.7.0 | Yahoo Finance（unofficial wrapper） | Apache-2.0 |
| mcp | 2.2.0 | MCP server | MIT |
| pydantic | 2.13.5 | schema | MIT |
| FastAPI/Starlette（mcp 相依） | — | 傳輸層 | MIT/BSD |

完整傳遞依賴與精確版本見 `requirements-lock-windows-x64.txt`。

---

## 三、資料來源

| 來源 | 用途 | 條款 |
|------|------|------|
| TWSE OpenAPI（openapi.twse.com.tw） | 台股官方日線 | 台灣證券交易所公開資料 |
| FinMind | 台股資料（需自備 token） | FinMind 服務條款 |
| FRED（St. Louis Fed） | 總經（需自備免費 key） | 美國政府公開資料 |
| Yahoo Finance / yfinance | 全球代理行情 | unofficial wrapper；BEST_EFFORT / 個人研究用 |

**本 repository 不包含任何市場原始資料**（raw parquet / duckdb / cache 皆在 .gitignore）。

---

## 四、若要重新散布

1. 你的**原始碼**：請自行決定是否加上授權（本專案未指定）。
2. **Chronos-2 weights**：依 Apache-2.0 可再散布，但需保留授權聲明。
3. **TimesFM-3.0 / FinCast weights**：**不得再散布**（非商業 / research-only）。
4. **市場資料**：受各來源條款限制，請勿公開散布。
