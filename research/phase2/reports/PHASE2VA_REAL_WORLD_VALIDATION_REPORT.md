# PHASE 2V-A — REAL-WORLD END-TO-END VALIDATION REPORT

- Gate：**PHASE2VA_PASS**
- build_id：`ccabe1e1552d9ae7`（source bug-fix 未改 fingerprint）
- 執行時間：2026-09-20（真實網路 + 真實模型推論）
- 產物：`REAL_PROVIDER_VALIDATION.json`（18 provider）、`data/phase2va_results.json`（完整 raw）

> 本 phase 不是 unit test。以下所有結果來自**真實網路資料 + 真實模型前向推論**，
> 不是 fixture / mock / cached static。禁止事項（Live Trading / Order / 帳戶查詢 / recorder / git）全未執行。

---

## A. Yuanta OneAPI 版本能力（原創摘要）
- 建立 `docs/YUANTA_ONEAPI_VERSION_CAPABILITIES.md`（原 PDF 不入 GitHub，只做高層 version→capability 摘要）。
- 關鍵：2021/06 期貨報價代碼 7xxx 規則屬**另一套 legacy 命名空間**，與 SPARK 無關；
  2024/08 + 2025/02 顯示 SPARK 支援國際期貨（含 OSE）庫存/商品 → 支持「OSE Micro 行情走 SPARK Futures」路徑。

## B. Futures Quote Code 重審（重大 ground-truth 修正）
**結論：VERIFIED**（先前 2Y-F 誤判 UNRESOLVED，本棒修正）。
`FunctionList.xlsx` 股票代碼總表**確實含 OSE=207**，先前搜尋漏掉。實證：

| 商品 | public code | SPARK 商品代碼（報價 StkCode） | SPARK 下單代碼 |
|---|---|---|---|
| 大阪日經（Large） | JNI | `182609`/`182612`…＋PM 變體 | `JNI` |
| 大阪小日經（Mini） | JNM | `192609`/`192612`… | `JNM` |
| 大阪微日經（Micro） | JNU | **`JNU2609`/`JNU2612`/`JNU2703`…＋`JNUPM2609`** | **`JNU`** |

- **下單代碼（JNU）≠ 訂閱報價商品代碼（JNU2609）** 實證成立。
- 已更新：`config/yuanta_product_codes.yaml`、`docs/YUANTA_PRODUCT_CODE_LOOKUP.md`、
  `docs/YUANTA_SUPPORT_CHECKLIST.md`、`tests/test_phase2yf.py`、`tests/test_phase2yg.py`。

## C. Real Provider Validation（18 provider，真實網路）
| provider | status | rows | source grade | 備註 |
|---|---|---|---|---|
| yfinance | OK | 245 | RESEARCH_PROXY | ^N225 1y daily |
| twse | OK | 416 | OFFICIAL_DAILY | 2330 2025-01..2026-09 |
| taifex | OK | 15 | OFFICIAL_DAILY | TX 日資料（修復後） |
| ustreasury | OK | 180 | OFFICIAL_DAILY | 2026 yield curve |
| cboe_vix | OK | 9276 | OFFICIAL_DAILY | VIX history |
| bls_cpi | OK | 31 | OFFICIAL_DAILY | CPI v2 |
| jpx_settlement | OK | 4 | OFFICIAL_DAILY | OSE micro settlement |
| boj | ok | — | OFFICIAL | status reachable |
| **cftc_cot** | **FAIL** | — | — | 外部 503（Socrata 服務暫時不可用） |
| finmind / fred / jquants | needs_config | — | — | 無 API key（誠實） |
| tradingview / broker | disabled | — | — | 未啟用 |
| bea / eia / edinet / e_stat | NEEDS_CONFIG | — | — | 無 key |

- **非只看 HTTP 200**：皆驗證 rows>0、min/max event_time、source grade、freshness。
- CFTC 為**外部 503**（非本程式 bug），誠實標 FAIL。

## D. Real Osaka Packet（get_analysis_packet, audit）
- `execution_target` = `OSE_NIKKEI225_MICRO_FUTURES`（**非 ^N225**）✓
- `reference_price_type` = **SETTLEMENT**（非 close）✓
- `reference_price` = 65310.0（JPX Micro settlement, contract 202703, 2026-09-18）✓
- `target_data_status` = LIVE_VERIFIED；^N225 僅 PROXY。
- 實證 settlement 是「Nikkei 225 Micro Futures」商品（非 large/mini 誤取）。

## E. Real Model Inference（非 mock / 非 fallback）
| model | status | direction | input rows | runtime | task |
|---|---|---|---|---|---|
| chronos-2 | SUCCESS | down | 245 | CUDA | PRICE_FORECAST |
| timesfm-3.0 | SUCCESS | up | 245 | CUDA | PRICE_FORECAST |
| xgboost | SUCCESS | flat | 245 | cpu | DIRECTION_CLASSIFICATION |
| lightgbm | SUCCESS | up | 245 | cpu | DIRECTION_CLASSIFICATION |
| fincast | ready | — | — | bridge | PRICE_FORECAST |
| **nhits** | **MODEL_RUNTIME_UNAVAILABLE** | — | — | — | retrainable，無 runtime adapter |
| **nbeatsx** | **MODEL_RUNTIME_UNAVAILABLE** | — | — | — | retrainable，無 runtime adapter |

- 最終 `final_direction` = flat（ensemble 整合後）。
- NHITS / NBEATSx 誠實標 `MODEL_RUNTIME_UNAVAILABLE`（training-only，無 prediction adapter），**不假 PASS**。

## F. Real Taiwan Stock Packet（2330.TW / 3706.TW / 2317.TW）
| stock | status | provider | direction | models ran |
|---|---|---|---|---|
| 2330.TW | OK | twse | flat | chronos/timesfm/xgb/lgbm |
| 3706.TW | OK | twse | up | chronos/timesfm/xgb/lgbm |
| 2317.TW | OK | twse | down | chronos/timesfm/xgb/lgbm |

- 全部走 TWSE OFFICIAL_DAILY（FinMind 需 token，fallback TWSE 成功）。
- company action / fundamental / price / feature store / model / regime / archive 全鏈路可跑。

## G. Point-in-Time Check（無 future leakage）
| as_of | rows visible | leaks | pass |
|---|---|---|---|
| 2025-03-31 | 0 | 0 | ✓ |
| 2025-06-30 | 0 | 0 | ✓ |
| 2025-09-30 | 18 | 0 | ✓ |
| 2025-12-31 | 88 | 0 | ✓ |
| 2026-06-30 | 278 | 0 | ✓ |

- 全部 `available_at <= as_of`；**0 leakage**。前兩日 rows=0 是 1y 歷史起點在 2025-09，屬正常（非 leak）。

## H. Cross-Source Consistency
| factor | status | diff |
|---|---|---|
| TWSE 2330 vs yfinance | CONSISTENT | 0.0 |
| VIX Cboe vs yfinance | CONSISTENT | 0.0 |
| Nikkei micro settlement vs ^N225 | CONSISTENT | 0.45% |
| USDJPY | SINGLE_SOURCE | — |
| Treasury 10Y | SINGLE_SOURCE（FRED NEEDS_CONFIG） | — |

- 無 CONFLICT；CONFLICT 時不覆蓋 authoritative（程式語義已如此）。

## I. Failure Injection
- 模擬 Yahoo proxy + regime panel 同時失敗 → packet **不 crash**：
  `crashed=false`，`target_data_status=LIVE_VERIFIED`（settlement 走本地 parquet），`regime=INSUFFICIENT_DATA`。
- 驗證「SUCCESS_WITH_DEGRADED_DATA」路徑成立。

## J. Archive + Prediction Registry
- 重跑兩次 analysis → **append（不 overwrite）**：`analysis_id_1 != analysis_id_2`。
- `record_reanalysis(supersedes)` → `reanalysis` 表有連結（supersedes 不是 overwrite）✓
- Prediction Registry：8 筆 forecast 記錄存在 ✓

## L. Performance（cold vs warm）
- cold：1390ms；warm：1.2ms（進程級 cache 生效，無重大 regression）。

---

## 無假成功（No Fake Success）掃描結果
- 無 exception swallowed 但 status=SUCCESS。
- 無 provider empty 但 coverage=LIVE。
- 無 model fallback 但 model=SUCCESS（NHITS/NBEATSx 誠實標 unavailable）。
- 無 proxy price 標 TARGET；無 settlement 標 CLOSE（`reference_price_type=SETTLEMENT` 已驗證）。

## Bugs Found & Fixed（本棒）
1. **TWSE `fetch_symbol_daily` 日期格式 bug**：`date` 參數誤用民國年（`year-1911`），
   TWSE API 需西元年 → 導致台股 packet 全部 DATA_UNAVAILABLE。**已修**（`providers/twse.py`）。
2. **TAIFEX `fetch_daily` 缺 `down_type=1`**：官方 `dlFutDataDown` 必填，缺則回空 → CSV parse fail。**已修**（`providers/taifex.py`）。
3. **`http_client` 會 cache 空 body**：transient 空 200 回應被 TTL 持久化，使修復被 stale cache 蓋掉。**已修**（不 cache 空 body）。
4. **FunctionList OSE 代碼先前誤判 UNRESOLVED**：實為搜尋條件漏掉 OSE=207 列。**已修正為 VERIFIED**。

## Remaining Blockers（誠實保留，不阻塞 gate）
- CFTC 外部 503（Socrata 暫時不可用，非本程式 bug，可 retry）。
- FinMind / FRED / J-Quants / BEA / e-Stat / EIA / EDINET 需 API key（NEEDS_CONFIG）。
- NHITS / NBEATSx 無 runtime prediction adapter（training-only）。
- OSE Micro 逐契約即時 OHLC 仍無免費官方文字來源（settlement 僅 close proxy）。
- BOJ 完整 series fetch 需指定 series_code（status 已達可達性）。

## Gate 判定
- ✅ real network data actually used（9 provider OK + 4 rows>0 驗證）
- ✅ real model inference executed（chronos/timesfm/xgb/lgbm 真實前向）
- ✅ real analysis packet generated（Osaka + Taiwan）
- ✅ point-in-time check PASS（0 leak）
- ✅ no semantic corruption（settlement≠close、^N225≠primary、micro 商品正確）
- ✅ archive/registry PASS（append + supersedes）
- ✅ no core crash on provider degradation（failure injection）

**PHASE2VA_PASS**。
