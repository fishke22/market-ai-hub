# Phase 2Z.1 — Yuanta API Family Final Disambiguation + Leveraged Trading Doc Patch

- Gate: **PHASE2Z1_PASS**
- build_id：`ccabe1e1552d9ae7`（未變，純 documentation/ground-truth patch）
- 測試：**509 passed**（503 + 6 2Z.1；5 live deselected）

## Yuanta four API families（永久）
| Family | account | purpose | status | usage |
|---|---|---|---|---|
| A. SPARK | 證券/期貨帳號（各別開權限） | 行情+下單 | 證券 AUTH_VERIFIED；期貨 0112 | 證券登入 |
| B. Futures Legacy Quote | 期貨帳號（登入ID=身份證） | 行情 | T+1 SERVER_CONFIRMED；T RETEST | x86 sidecar |
| C. Futures Legacy Trading | 期貨帳號（歸戶ID） | 交易 | DOCUMENTED_ONLY | 不接 |
| D. **Leveraged Trading（槓桿全球贏家）Web API** | **槓桿保證金帳號（獨立）** | CFD/FX/金屬/指數CFD | DOCUMENTED_ONLY / OUT_OF_SCOPE | 不接 |

## T/T+1 conclusion
- T / T+1 = futures market **session labels**（日盤/盤後），不是「一般期貨 vs 槓桿」帳號。
- `LEVERAGED_ACCOUNT_NOT_RELATED_TO_T_SESSION_AUTH`。

## Leverage account conclusion
- 槓桿全球贏家 = CFD/槓桿保證金平台，需**獨立槓桿保證金帳號**。
- API 申請頁 `ltm.yuantafutures.com.tw/member/api-apply` 屬於槓桿平台，不是一般 Futures API 申請頁。

## JNU scope
- JNU = **JPX Futures**（OSE Micro），不是 Nikkei CFD；不需要槓桿全球贏家帳戶。

## Proprietary doc exclusion
- 「槓桿全球贏家 Web API Specification」標 proprietary/confidential → 不入 GitHub。
- `PUBLICATION_EXCLUDE_MANIFEST.txt` 已加：proprietary Yuanta specs / PDF / WebView2 CAB / binaries。

## WebView2 classification
- `Microsoft.WebView2.FixedVersionRuntime*.cab` = **UI_RUNTIME_DEPENDENCY**（非 broker API binary）。

## Tests（6 新增）
yuanta_leverage_api_separate_family / t_session_not_leverage_account / jnu_not_cfd /
leveraged_api_not_core / proprietary_leverage_pdf_excluded / webview2_not_broker_api。

## Publication impact
- 新增 `docs/YUANTA_LEVERAGED_TRADING_API.md`（原創 public 摘要）。
- SYSTEM_MANIFEST 新增 `leveraged_trading`（primary_target_source=false）。
- PUBLICATION_FILE_MANIFEST + EXCLUDE 更新。

## 驗證
- `pytest tests/ -q` → 509 passed
- build_id 維持 `ccabe1e1552d9ae7`
- 全程未 push / tag / release / Live Trading / order。
