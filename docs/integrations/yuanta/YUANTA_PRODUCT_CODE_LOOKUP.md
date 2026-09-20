# Yuanta Product Code Lookup（商品代碼四種分離）

> **元大 SPARK 官方提醒：「下單代碼與訂閱報價商品代碼可能不同」。**

## 四種代碼（禁止互相複製）
| 欄位 | 意義 | 範例 |
|---|---|---|
| `public_product_code` | 官方商品代碼 | JNU（大阪微日經） |
| `spark_quote_code` | SPARK 訂閱報價 StkCode | `JNU2609`（合約月別，VERIFIED） |
| `legacy_com_quote_symbol` | Legacy COM `AddMktReg` symbol | UNVERIFIED |
| `trading_order_code` | 交易下單代碼 | `JNU`（VERIFIED） |

**JNU（public/order）≠ `JNU2609`（SPARK quote StkCode）≠ COM AddMktReg symbol。**
「下單代碼與訂閱報價商品代碼可能不同」在此實證成立。

## 已驗證（2026-09-19，FunctionList.xlsx 股票代碼總表 OSE=207）

| 商品 | public code | SPARK 商品代碼（報價 StkCode） | SPARK 下單代碼 |
|---|---|---|---|
| 大阪日經（OSE Large） | JNI | `182609`/`182612`/`182703`…（數字）＋ PM 變體 `18PM2609`… | `JNI` |
| 大阪小日經（OSE Mini） | JNM | `192609`/`192612`/`192703`… ＋ PM 變體 `19PM2609`… | `JNM` |
| 大阪微日經（OSE Micro） | JNU | **`JNU2609`/`JNU2612`/`JNU2703`… ＋ PM 變體 `JNUPM2609`…** | **`JNU`** |

OSE Micro contract multiplier = **Nikkei 225 × JPY 10**。

> 修正：先前 2Y-F 誤判「OSE 代碼不在 FunctionList」，實為搜尋條件漏掉 OSE=207 列。
> 本棒以 FunctionList 股票代碼總表逐列掃描，實證 OSE 三檔代碼皆在。
> **下單代碼（JNU）≠ 報價商品代碼（JNU2609）**：報價需用合約月別 StkCode。

## 查代碼順序（未來 AI 照做）
A. 元大官方商品/保證金表 → public product code
B. SPARK package FunctionList → Spark quote/order mapping
C. SPARK runtime output → MarketNo/StkCode
D. Yuanta MultiCharts QuoteManager → YuantaFutures 最新 Symbol List
E. Legacy Quote package docs → COM symbol format

**不同來源不得混為一談。** 見 `config/yuanta_product_codes.yaml`。
