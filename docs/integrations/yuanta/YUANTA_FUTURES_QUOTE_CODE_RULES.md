# Yuanta Futures Quote Code Rules（期貨報價代碼規則）

> 原創摘要；不複製 proprietary 原文件。

## 1. SPARK 期貨報價代碼（VERIFIED，FunctionList）
來源：`FunctionList.xlsx` 股票代碼總表（SHA256 `39b0f2244981258399b840e9d4c9e9b3cc85d2425fdc14f4058f328bb8fd4ea5`，3.4MB，2026-09-17）。

欄位：`市場別 | 市場代碼 | 商品代碼 | 商品名稱 | 下單代碼`。

| 商品 | 市場代碼 | 商品代碼（報價 StkCode） | 下單代碼 |
|---|---|---|---|
| 大阪日經（Large） | 207 | `182609`/`182612`… | `JNI` |
| 大阪小日經（Mini） | 207 | `192609`/`192612`… | `JNM` |
| 大阪微日經（Micro） | 207 | **`JNU2609`/`JNU2612`/`JNU2703`/`JNUPM2609`…** | **`JNU`** |

**下單代碼（JNU）≠ 訂閱報價商品代碼（JNU2609）**。報價需用合約月別 StkCode。

## 2. Legacy Quote 報價代碼（VERIFIED 語義，UNRESOLVED 實際碼）
`AddMktReg(Symbol, UpdateMode)`：期貨類 Symbol = **EASYWIN 期貨報價代碼**（官方 `元大行情API.pdf`）。
實際 EASYWIN 對照表不在本機 SDK → 見 `docs/YUANTA_EASYWIN_SYMBOL_MAPPING.md`。

## 3. Legacy Trading 商品代碼（FutNo）
`SendOrderF` 的 `FutNo`（下單商品代碼）範例：`TXFD9`、`TXFD9/E9`（期貨）、`TXO04500E9`（選擇權）。
這是**交易 API 的下單代碼 namespace**，與 SPARK / EASYWIN 報價代碼不同。

## 4. 「期貨報價代碼 7xxx 變更規則」（2021/06）
來源：`YuantaOneHis.pdf`（2021/06 變更），**不在本機 Documents/Downloads SDK 檔案內**。
本棒在本機 SDK 搜尋 `7xxx`/`報價代碼變更規則` **無命中**。
屬 legacy OneAPI 歷史命名空間變更，與現行 SPARK StkCode 無關。
（見 `docs/YUANTA_ONEAPI_VERSION_CAPABILITIES.md`。）

## 結論
- SPARK 期貨報價代碼：**VERIFIED**（FunctionList，合約月別 StkCode）。
- Legacy Quote 期貨報價代碼：語義 VERIFIED（=EASYWIN），實際碼 UNRESOLVED。
- 7xxx 規則：僅歷史 PDF，本機 SDK 無，與現行無關。
