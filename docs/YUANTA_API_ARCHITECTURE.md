# Yuanta API Architecture（最終版：四條 API family）

> 元大 integration 永久分成四條，禁止混成同一 API。

## 架構圖

```
Yuanta
├─ A. SPARK API（證券+期貨帳號，pythonnet/.NET 8，權限依帳號開通）
├─ B. Futures Legacy Quote API（32-bit ActiveX OCX，行情，SetMktLogon）
├─ C. Futures Legacy Trading API（1.6.1.3，交易，FUTURE_RESEARCH_ONLY）
└─ D. Leveraged Trading「槓桿全球贏家」Web API（CFD/槓桿保證金，DOCUMENTED_ONLY）
```

## 每條 API

| Family | account type | purpose | transport | current status | MARKET_AI_HUB usage |
|---|---|---|---|---|---|
| A. SPARK | 證券/期貨帳號（Securities/Futures account，各別開權限） | 行情+下單 | pythonnet/.NET 8/gRPC | 證券 AUTH_VERIFIED；期貨 0112 CONTRADICTION | 證券登入已驗證 |
| B. Futures Legacy Quote | 期貨帳號（登入ID=身份證） | 行情 | 32-bit ActiveX OCX（YuantaQuote_v2.1.2.9.ocx，Quote COM） | T+1 SERVER_CONFIRMED；T REQUIRES_SESSION_AWARE_RETEST | x86 sidecar |
| C. Futures Legacy Trading | 期貨帳號（歸戶ID） | 交易 | COM | DOCUMENTED_ONLY / NOT_IMPLEMENTED | 不接 runtime |
| D. Leveraged Trading Web API | **槓桿保證金帳號（獨立）** | CFD/FX/金屬/指數CFD | Web API | DOCUMENTED_ONLY / OUT_OF_SCOPE | 不接 runtime |

## Legacy Quote overseas scope
- 官方公開頁命名「國內行情 API」+ 本地 sample 僅 TAIFEX 國內商品 → 疑 DOMESTIC_ONLY，
  但未證實排除海外 → `RUNTIME_OVERSEAS_SUPPORT_UNVERIFIED`（evidence-based）。

## 0112 語義
- `0112` = 無此權限使用功能（不是 Wrong API family）。

## T / T+1（session labels）
- T / T+1 = futures market session（日盤/盤後），**不是「一般期貨 vs 槓桿」帳號**。
- `LEVERAGED_ACCOUNT_NOT_RELATED_TO_T_SESSION_AUTH`（除非未來官方證據推翻）。

## JNU（OSE Micro）
- JNU = JPX Futures，不是 Nikkei CFD；**不需要槓桿全球贏家帳戶**。
