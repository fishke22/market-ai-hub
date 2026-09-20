# Data Source Matrix

| Provider | Dataset | Market | Official | Authority | Frequency | Delay | API key | Point-in-time | Revision risk | Status | Fallback |
|---|---|---|---|---|---|---|---|---|---|---|---|
| JPX settlement | futures settlement | OSE | yes | AUTHORITATIVE | daily | ~1 biz day | no | safe | none | **LIVE_VERIFIED** | — |
| JPX volume | daily volume | OSE | yes | AUTHORITATIVE | daily | ~1 biz day | no | safe | none | **LIVE_VERIFIED** | — |
| JPX open interest | OI | OSE | yes | AUTHORITATIVE | daily | ~1 biz day | no | safe | none | **LIVE_VERIFIED** | — |
| JPX OHLC | per-contract OHLC | OSE | yes | — | daily | — | no | — | — | CONTRACT_ONLY | settlement (close proxy) |
| JPX investor flow | by investor | OSE | yes | — | weekly | — | no | — | — | CONTRACT_ONLY | — |
| TWSE | 台股歷史 | TW | yes | AUTHORITATIVE | daily | — | no | safe | none | HISTORICAL_VERIFIED | — |
| TAIFEX | 期貨 | TW | yes | AUTHORITATIVE | daily | — | no | — | — | CONTRACT_ONLY | — |
| FinMind | 台股 | TW | semi | PROXY | daily | — | token | — | — | AVAILABLE | — |
| BLS | CPI/NFP | US | yes | AUTHORITATIVE | monthly | release | no | release-time | **有** | **LIVE_VERIFIED** | — |
| Cboe | VIX | US | yes | AUTHORITATIVE | daily | — | no | safe | none | **LIVE_VERIFIED** | yfinance |
| SEC EDGAR | filings | US | yes | AUTHORITATIVE | event | — | no | safe | none | **LIVE_VERIFIED** | — |
| BOJ | release/MPM | JP | yes | AUTHORITATIVE | event | — | no | — | — | **LIVE_VERIFIED** | — |
| Fed | FOMC calendar | US | yes | AUTHORITATIVE | event | — | no | — | — | CONTRACT_ONLY | — |
| FRED | macro | US | yes | AUTHORITATIVE | varies | — | key | — | — | AVAILABLE | — |
| CFTC | COT | US | yes | AUTHORITATIVE | weekly | — | no | — | — | CONTRACT_ONLY | — |
| BEA | GDP/PCE | US | yes | AUTHORITATIVE | monthly/qtr | — | key | — | 有 | NEEDS_CONFIG | — |
| e-Stat | JP CPI/labor | JP | yes | AUTHORITATIVE | varies | — | appId | — | — | NEEDS_CONFIG | — |
| EIA | WTI | US | yes | AUTHORITATIVE | weekly | — | key | — | — | NEEDS_CONFIG | — |
| EDINET | JP filings | JP | yes | AUTHORITATIVE | event | — | key | — | — | NEEDS_CONFIG | — |
| MOF | FX intervention | JP | yes | AUTHORITATIVE | event | — | no | — | — | CONTRACT_ONLY | — |
| Cabinet Office | GDP calendar | JP | yes | AUTHORITATIVE | event | — | no | — | — | CONTRACT_ONLY | — |
| J-Quants | JP | JP | semi | PROXY | daily | — | key | — | — | CONTRACT_ONLY | — |
| Yahoo/yfinance | multi | global | no | PROXY | daily | — | no | — | — | **PROXY** | — |

## 狀態語義
- `LIVE_VERIFIED`：已實際連線 + 解析成功。
- `HISTORICAL_VERIFIED`：官方歷史已抓取。
- `CONTRACT_ONLY`：有 provider 介面，未接實網。
- `NEEDS_CONFIG`：需 API key。
- `PROXY`：第三方 proxy（非官方）。
- `MISSING`：無來源。

**不得把 CONTRACT_ONLY 寫成 LIVE。** BLS 有修訂 → revision risk；JPX settlement/volume/OI 為日快照 → 無 revision risk。
