# Yuanta API Permissions（申請與權限）

> 元大期貨官方目前要求：**API 行情服務** 與 **API 交易服務** 皆需先申請/核准。

## 三種權限（分開）
| 權限 | 用途 | 狀態 |
|---|---|---|
| SPARK API permission | 證券/期貨 SPARK 行情（含國外期貨） | 證券已開；**期貨帳號需另申請** |
| Futures Legacy Quote API permission | 國內行情 COM quote | 已可登入（T+1 盤成功） |
| Futures Legacy Trading API permission | 交易 | **未申請**（FUTURE_RESEARCH_ONLY） |

## 申請路徑（元大期貨官方）
```
期貨線上服務
→ 線上服務
→ API 行情服務風險預告暨申請使用聲明書   （行情）
→ API 交易服務風險預告暨申請使用聲明書   （交易）
```

⚠️ 官方 UI 路徑可能更新，以 `checked_at` 日期為準（見 `config/yuanta_official_sources.yaml`）。

## SPARK Futures 權限
- 期貨帳號用 SPARK Login 回 `0112`（無此權限使用功能）。
- 需**另行申請**該期貨帳號的 SPARK API 權限。
- 申請後才能用 SPARK 取得國外期貨（含 OSE Micro）StkCode 與行情。

## 海外行情
- 國外期貨行情可能另有訂閱/權限/費用（見 `docs/YUANTA_MARKET_DATA_PERMISSIONS.md`）。

## 憑證
- 見 `docs/YUANTA_CERTIFICATE_WINDOWS11.md`。同一身分證字號只能申請一張有效憑證；
  證券 + 期貨電子戶可用同一張；有效期限目前 1 年。
