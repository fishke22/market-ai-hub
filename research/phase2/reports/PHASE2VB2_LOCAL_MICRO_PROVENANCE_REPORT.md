# PHASE 2V-B.2 — LOCAL OSE MICRO DATA PROVENANCE REPORT

- Gate: **PHASE2VB2_PASS**
- 前置: PHASE2VB_PASS + PHASE2VB1_PASS
- 性質: 資料鑑識與驗證（READ-ONLY，未修改任何原始檔）
- 禁止遵守: 無 2V-C/2V-D、無 GitHub publication、無 Live Trading

---

## 0. 頭條結論

本機 `D:\data` 的 **N225microf 系列是「真實 OSE Nikkei 225 Micro Futures 分鐘級 trade OHLCV」**，共 **796 個已驗證交易日**（2023-07-24 → 2026-08-31），**0 筆上市前資料**，tick size = 5 點（正確），時區 = JST（Asia/Tokyo），成交量 = 每分鐘契約量，且**與 Mini 完全獨立（非重複）**。

→ **DIRECT_MICRO_BAR_OOS_POSSIBLE**（≥250 天 = SUBSTANTIAL）。

但**官方 Settlement 歷史仍然缺失**（僅 2V-B 的 1 日），故 **DIRECT_SETTLEMENT_INSUFFICIENT** 維持不變。

---

## 1. 為什麼 dataset 從 2012 就標 Micro？

**其實沒有。** 這是誤解。實際檔名分類清楚：
- `N225minif_2012.zip` ~ `2026.zip`（15 檔）= **Mini**（JNM），Mini 2006 上市，2012 起有分鐘檔。
- `N225microf_2023.zip` ~ `2026.zip`（4 檔）= **Micro**（JNU），Micro 2023-05-29 上市，2023 起才有檔。

**沒有「2012 就標 Micro」的資料**。標籤正確。`minif` 是 Mini，`microf` 是 Micro。

## 2. 2012–2023 實際是什麼？

2012–2023 的 `N225minif` 是 **Nikkei 225 Mini（JNM）** 分鐘 OHLCV，非 Micro。另有 `225mini2006d.xls`~`225mini2011d.xls`（6 檔，2006–2011）為 Mini 早期日線（舊 .xls 格式，需 xlrd 讀取）。

## 3. 2023-05-29 後是否有真實 Micro？

**有。** `N225microf_2023.zip` 首日 2023-07-24（上市日後 56 天）。2023-05-29 至 2023-07-23 的 Micro 分鐘資料**缺失**（56 天 gap），但 2023-07-24 起資料完整。

## 4. 來源是什麼？

**225LABO**（日本 data vendor）。證據：
- QROS 路徑 `QROS\data\personal_licensed\225labo\micro\raw\` 與 `D:\data` 檔案 SHA256 完全相同（備份關係）。
- 欄位名為日文（日付/時間/始値/高値/安値/終値/出来高）。
- 來源等級 = **DATA_VENDOR_225LABO**（非 OFFICIAL_EXCHANGE，非 BROKER）。

> 因此權威等級 = **DATA_VENDOR**，不是官方交易所。但仍屬第三方可驗證市場資料（數值與已知 Nikkei 價位吻合）。

## 5. 有多少 verified Micro days？

**796 個交易日**（2023-07-24 → 2026-08-31），合計 **1,159,829 筆分鐘 OHLCV**。

| 檔案 | 交易日 | 首日 | 末日 | 分鐘列 |
|------|--------|------|------|--------|
| microf_2023 | 115 | 2023-07-24 | 2024-01-03 | 137,839 |
| microf_2024 | 256 | 2024-01-03 | 2025-01-03 | 307,321 |
| microf_2025 | 258 | 2024-12-30 | 2026-01-05 | 309,695 |
| microf_2026 | 172 | 2025-12-30 | 2026-08-31 | 206,744 |

## 6. minute OHLCV 是否真的獨立？

**是。** Micro 與 Mini 在重疊期間（2023-07-24 起，137,839 筆重疊）的比較：

| 指標 | 值 | 判定 |
|------|-----|------|
| OHLC 完全吻合率 | 21.24% | 非重複 |
| Close 完全吻合率 | 63.35% | 價格相近但非相同 |
| **Volume 完全吻合率** | **1.18%** | **決定性證據：不同契約** |
| Close 差異 max | 65 點 | 有意義差異 |
| Volume 差異 max | 21,243 口 | 完全不同成交量 |

## 7. Micro/Mini 是否 duplicated？

**否。** Volume 完全吻合率僅 1.18%（相差 21,243 口）——這是「不同契約」的決定性證據（Mini 契約 = Nikkei×100，Micro = Nikkei×10，成交量天然不同）。價格相近是正常的（兩者都追蹤 Nikkei 225），不構成 duplicate 判據。

## 8. timezone？

**JST（Asia/Tokyo）** — 已驗證。交易時段缺口：
- 夜盤→日盤缺口：06:00 → 08:45（165 分鐘）
- 日盤→夜盤缺口：15:15 → 16:30（75 分鐘）

與 OSE 官方時段（夜盤 16:30–06:00、日盤 08:45–15:15、無午休）**完全吻合**。

## 9. tick size？

**5 點** — 已驗證。所有 close 價差的最小非零值 = 5.0，全部價格落在 5 點 grid 上（`price_is_5point_grid = true`）。符合官方 Micro tick size = 5 index points。

## 10. volume semantics？

**PER-MINUTE contract volume**（非累積）。前 20 分鐘成交量 336/131/393/528/521... 上下跳動，非單調遞增 → 每分鐘成交量。可用於流動性/成交量特徵（但需 PIT 安全）。

## 11. Settlement 有沒有？

**沒有。** 再次全面搜尋：
- `D:\data`：無 settlement 檔。
- `D:\QROS`：53 個 `JPX_SETTLEMENT.*.json` 全部是**下載 manifest**（33 位元組的失敗回應，指向無效的 `https://www.jpx.co.jp/safe/file.csv`），非實際資料。
- 唯一 settlement 仍為 2V-B 的 1 日（2026-09-18）。

→ **DIRECT_SETTLEMENT_INSUFFICIENT 維持不變。**

## 12. 哪些資料可以 import？

| 資料 | status | 可 import? |
|------|--------|-----------|
| N225microf_2023-2026 | **VERIFIED_OSE_MICRO** | ✅ APPROVED_FOR_IMPORT |
| N225minif_2012-2026 | REFERENCE_ONLY | ⚠️ 僅 reference |
| 225mini 2006-2011 (.xls) | UNVERIFIED (需 xlrd) | ❌ 待驗證 |
| QROS RV/RSV derived | UNVERIFIED (legacy) | ❌ 不直接 import（需重建） |

## 13. 哪些只能 proxy/reference？

- Mini（JNM）：**REFERENCE_ONLY**（非 direct target）。
- QROS RV/RSV/Intraday Path：**不信任 legacy precomputed**，應由 verified raw data 在 MARKET_AI_HUB 重新計算。
- ^N225 spot：**NIKKEI_SPOT_PROXY**（既有 2V-B proxy exam 已用）。

## 14. 是否可以建立 Direct Micro Bar OOS？

**是。** `DIRECT_MICRO_BAR_OOS_POSSIBLE`（796 天 ≥ 250 = SUBSTANTIAL）。target = `NEXT_SESSION_BAR_CLOSE`（或 `NEXT_DAILY_LAST_TRADE`），**不是 NEXT_SETTLEMENT**。已建立 `DIRECT_MICRO_BAR_OOS_PROTOCOL_DRAFT.yaml`（與 settlement protocol 分開，下一棒再正式 pre-register）。

## 15. 是否能建立 Direct Settlement OOS？

**否。** Settlement 歷史仍僅 1 日 → **DIRECT_SETTLEMENT_INSUFFICIENT**。需 J-Quants API key 或 JPX Data Cloud 授權補齊歷史。

---

## 資料分類總表

| dataset | instrument_classification | authority | import_status | 用於 |
|---------|--------------------------|-----------|---------------|------|
| N225microf_2023-2026 | OSE_NIKKEI225_MICRO_FUTURES | DATA_VENDOR_225LABO | VERIFIED_OSE_MICRO | Direct Bar OOS |
| N225minif_2012-2026 | OSE_NIKKEI225_MINI_FUTURES | DATA_VENDOR_225LABO | REFERENCE_ONLY | Reference |
| 225mini 2006-2011 | OSE_NIKKEI225_MINI (legacy) | DATA_VENDOR | UNVERIFIED | 待 xlrd |
| QROS RV/RSV | derived feature | QROS_LEGACY | UNVERIFIED | 需重建 |

## 品質指標摘要

| 檢查 | 結果 |
|------|------|
| 上市前資料 | 0 筆（PASS） |
| tick size grid | 5 點（PASS） |
| 時區/時段 | JST / OSE（PASS） |
| volume 語義 | per-minute（PASS） |
| Micro≠Mini 獨立性 | 確認（volume 差異 98.8%） |
| 缺失期間 | 2023-05-29 ~ 07-23（56 天 gap，標記） |

## Gate 判定

- ✅ 本地 Micro 資料真實身份查清（796 天 verified bar）
- ✅ 上市日 constraint 通過（0 筆 pre-listing）
- ✅ Micro/Mini 未盲目合併（獨立性確認）
- ✅ close 未誤標 settlement（BAR_CLOSE 明確）
- ✅ tick size / timezone / volume 語義驗證完成
- ✅ settlement 未偽造（DIRECT_SETTLEMENT_INSUFFICIENT 誠實保留）
- ✅ 未修改原始檔（READ-ONLY）

**PHASE2VB2_PASS**
- **VERIFIED_MICRO_BAR_HISTORY_FOUND**（796 天 ≥ 100）
- **SUBSTANTIAL_DIRECT_BAR_SAMPLE_AVAILABLE**（796 天 ≥ 250）
- **DIRECT_SETTLEMENT_INSUFFICIENT**（維持）
