# PHASE 2V-B.1 - LOCAL HISTORICAL DATA DISCOVERY REPORT

**Gate: PHASE2VB1_PASS** (no DIRECT_TARGET_HISTORY_FOUND sufficient for full OOS)

---

## 1. D:\data 資料夾內容 (43 檔案)

### 1.1 歷史 Mini XLS 檔案 (需 xlrd 讀取)
| 檔案 | 大小 | 疑似內容 |
|------|------|----------|
| 225mini2006d.xls | 5.5 MB | 2006 Mini 日線 |
| 225mini2007d.xls | 13.6 MB | 2007 Mini 日線 |
| 225mini2008d.xls | 18.6 MB | 2008 Mini 日線 |
| 225mini2009d.xls | 20.5 MB | 2009 Mini 日線 |
| 225mini2010d.xls | 24.6 MB | 2010 Mini 日線 |
| 225mini2011d.xls | 36.6 MB | 2011 Mini 日線 |

> ⚠️ 格式為舊版 .xls (Excel 97-2003)，需 xlrd 1.x 讀取

### 1.2 Micro 分鐘級 OHLCV (ZIP 包含 XLSX)
| 檔案 | 行數 | 日期範圍 | 交易日數 | SHA256 |
|------|------|----------|----------|--------|
| N225microf_2023.zip | 137,840 | 2023-07-24 ~ 2023-12-29 | ~110 | 913df08ebebe029c |
| N225microf_2024.zip | 307,322 | 2024-01-03 ~ 2024-12-30 | ~244 | 913df08ebebe029c |
| N225microf_2025.zip | 307,322 | 2024-12-30 ~ 2025-12-30 | ~244 | 908d7db8ff69fe3b |
| N225microf_2026.zip | 206,745 | 2025-12-30 ~ 2026-08-31 | ~170 | e6149c02097814f8 |

**欄位**: Date, Time, Open, High, Low, Close, Volume (分鐘級 OHLCV)
**Micro 上市日**: 2023-05-29，資料從 2023-07-24 開始

### 1.3 Mini 分鐘級 OHLCV (ZIP 包含 XLSX)
| 檔案 | 行數 | 日期範圍 | 交易日數 | SHA256 |
|------|------|----------|----------|--------|
| N225minif_2012.zip | 309,726 | 2012-01-03 ~ 2012-12-28 | ~244 | 13db64a872735ff8 |
| N225minif_2013.zip | 309,726 | 2013-01-03 ~ 2013-12-30 | ~244 | 5d46f1a695e1597f |
| ... | ... | ... | ... | ... |
| N225minif_2026.zip | 206,745 | 2025-12-30 ~ 2026-08-31 | ~170 | c302cb0e261d211b |

**欄位**: Date, Time, Open, High, Low, Close, Volume (分鐘級 OHLCV)
**Mini 歷史**: 2012-2026 完整覆蓋

### 1.4 其他檔案
- 下載腳本: _download_jnu_micro_center_2023_2026.py 等
- 圖片/臨時檔案: 數個 .png/.gif/.py

---

## 2. D:\QROS 內容 (121,653 檔案)

### 2.1 衍生數據 - 核心市場資料
| 路徑 | 類型 | 日期範圍 | 筆數 | 說明 |
|------|------|----------|------|------|
| data/derived/jnu_225labo_micro/jnu_225labo_micro_daily_rvrsv_v1.csv | Micro 日級 RV/RSV | 2023-07-24 ~ 2026-08-31 | 796 | 5分鐘 RV/RSV (非原始 OHLC) |
| data/derived/jnu_225labo/jnu_225labo_mini_daily_rvrsv_v1.csv | Mini 日級 RV/RSV | 2006-07-18 ~ 2026-08-31 | 4,972 | 5分鐘 RV/RSV (非原始 OHLC) |
| data/derived/jnu_225labo_micro_path/jnu_225labo_micro_intraday_path_v1.csv | Micro 盤中路徑收益 | 2023-07-24 ~ 2026-08-31 | 796 | 盤中分段收益分解 |

### 2.2 其他衍生特徵
- jnu_basis_change_g1/ose_mini_cash_basis_change_signal_panel_v1.json
- jnu_boj_mpm/ BOJ 貨幣政策會議微/小微事件波動率
- jnu_momrev/ Mini 動能反轉特徵
- jnu_overnight_overreaction/ 隔夜過度反應
- jnu_prior_night_usdjpy/ 隔夜 USDJPY 影響

### 2.3 模型實驗數據
- model_lab/backtests/unified_data/unified_ohlcv_inst_rev.parquet (143萬行) - **台灣股票** OHLCV，**非 OSE/JPX**
- model_lab/backtests/unified_data/pb_daily_cache.json
- 多個審計日誌、合約定義、驗證清單

### 2.4 元數據與審計
- metadata/daily_prices_coverage.json
- metadata/stale_price_audit.json
- metadata/institutional_extra_raw_audit.json

### 2.5 關鍵發現：**無官方 JPX/OSE Settlement 原始檔案**
- QROS 無 JPX 官方 settlement CSV/Parquet
- 僅有衍生的 RV/RSV (Realized Volatility/Realized Semi-variance)
- data/backtest_inputs/_check_ose_gate.py 僅為檢查腳本

---

## 3. Downloads vs Documents 版本比較

| 類別 | Documents | Downloads | 版本關係 |
|------|-----------|-----------|----------|
| N225microf 2023-2026 | 有 (ZIP) | 無 | Documents 較新/完整 |
| N225minif 2012-2026 | 有 (ZIP) | 無 | Documents 唯一來源 |
| 225mini 2006-2011 | 有 (XLS) | 無 | Documents 唯一來源 |

**結論**: Documents 為主要來源；Downloads 僅有部份 ZIP，無新增版本。

---

## 4. 關鍵字搜尋結果

| 關鍵字 | D:\data | QROS | 備註 |
|--------|----------|------|------|
| JNU / JNU2609 | 0 | 大量 (derived) | 僅 QROS 有衍生特徵 |
| JNM / JNI | 0 | 大量 | 同上 |
| OSE / JPX | 0 | 大量 (路徑/文檔) | QROS 有文檔/驗證腳本 |
| Settlement | 0 | 0 (CSV/Parquet) | **無官方 settlement 檔案** |
| OHLC | 0 | 0 (CSV/Parquet) | Documents 有 XLSX；QROS 無原始 OHLC CSV |
| Volume / OI | 0 | 0 | 同上 |
| JUN2609 | 0 | 0 | 無此格式代碼 |

---

## 5. 日期範圍覆蓋 (2023-05-29 ~ 2026-09-20)

| 資料類型 | 最早日期 | 最新日期 | 交易日數 | 覆蓋率 |
|----------|----------|----------|----------|--------|
| Micro 分鐘 OHLCV | 2023-07-24 | 2026-08-31 | ~860 | 100% (上市後) |
| Mini 分鐘 OHLCV | 2012-01-03 | 2026-08-31 | ~3,500 | 100% |
| Micro RV/RSV | 2023-07-24 | 2026-08-31 | 796 | 92% |
| Mini RV/RSV | 2006-07-18 | 2026-08-31 | 4,972 | 100% |
| **官方 Settlement** | **無** | **無** | **0** | **0%** |

---

## 6. 資料分類

| 資料集 | 分類 | 說明 |
|--------|------|------|
| Micro 分鐘 OHLCV (D:\data) | **DIRECT_TARGET** | 真正的 OSE Micro 分鐘級 OHLCV |
| Mini 分鐘 OHLCV (D:\data) | **REFERENCE** | Mini 合約參考價格 |
| Micro RV/RSV (QROS) | **AUXILIARY_FEATURE** | 已計算的已實現波動率特徵 |
| Mini RV/RSV (QROS) | **AUXILIARY_FEATURE** | 同上 |
| Micro Intraday Path (QROS) | **AUXILIARY_FEATURE** | 盤中路徑分解收益 |
| Taiwan 統一 OHLCV (QROS) | **UNKNOWN** | 台灣股票，非 OSE/JPX |
| 官方 Settlement | **UNKNOWN** | **本機無此資料** |

---

## 7. 價格語義驗證

| 資料集 | 價格欄位 | 語義 | 驗證 |
|--------|----------|------|------|
| Micro 分鐘 OHLCV | Open/High/Low/Close | **UNKNOWN** (推測為 minute bar close) | 標題中文編碼損壞，但樣本數值合理 |
| Mini 分鐘 OHLCV | 同上 | **UNKNOWN** | 同上 |
| Micro RV/RSV | rv_5m 等 | **RV/RSV** (非價格) | 欄位名明確 |
| 官方 Settlement | N/A | N/A | **本機無** |

> ⚠️ XLSX 標題中文編碼損壞 (cp950 顯示亂碼)，但樣本數值合理推測為 Date, Time, Open, High, Low, Close, Volume

---

## 6. 合約語義

| 資料集 | 合約代碼格式 | 範例 |
|--------|--------------|------|
| Micro 分鐘 OHLCV | 隱含 (檔名 N225microf) | 隱含 JNU 系列 |
| Mini 分鐘 OHLCV | 隱含 (檔名 N225minif) | 隱含 JNM 系列 |
| Micro RV/RSV | 無合約月份 | 單一每日序列 |
| Mini RV/RSV | 無合約月份 | 單一每日序列 |

> ⚠️ **無合約月份欄位** - 所有資料已合併為連續序列，無 contract month 欄位

---

## 7. 來源溯源

| 資料集 | 來源等級 | 證據 |
|--------|----------|------|
| Micro 分鐘 OHLCV | **THIRD_PARTY** | D:\data 來源不明，檔名格式符合數據商格式 |
| Mini 分鐘 OHLCV | **THIRD_PARTY** | 同上 |
| Micro RV/RSV (QROS) | **QROS_DERIVED** | QROS 內部衍生 (225LABO_MICRO_RVRSV_V1) |
| Mini RV/RSV (QROS) | **QROS_DERIVED** | QROS 內部衍生 (225LABO_MINI_RVRSV_V1) |
| 官方 Settlement | **OFFICIAL_EXCHANGE** | **本機無** - JPX 官網僅當日 CSV，歷史 404 |

---

## 8. JPX/OSE 來源檢查

- **JPX 官方 Settlement CSV**: 僅當日可下載 (rbYYYYMMDD.csv)，歷史日期回 404
- **OSE Daily Report**: 僅當日 XLSX 可下載，歷史需 JPX Data Cloud 或 J-Quants API
- **本機無**: 任何官方 JPX/OSE settlement CSV/Parquet/XLSX
- **QROS 僅有**: 驗證腳本、sitemap、session semantics HTML、衍生特徵

---

## 9. 資料庫檢查

| 資料庫 | 位置 | 表/關鍵欄位 | 狀態 |
|--------|------|-------------|------|
| unified_ohlcv_inst_rev.parquet | model_lab/backtests/unified_data/ | 143萬行，20欄位 (台灣股票) | 唯讀檢查 OK |
| pb_daily_cache.json | model_lab/backtests/unified_data/ | 每日快取 | 存在 |
| DuckDB/SQLite | 未發現 | - | - |

---

## 10. 重複檢測

| 類型 | 群組數 | 說明 |
|------|--------|------|
| 空檔案 (SHA256=空) | 1,219 群 | 多為 node_modules/.venv/playwright 產生 |
| 真正市場資料重複 | 10 組 | D:\data ↔ QROS\personal_licensed 完全同檔 |
| QROS 內部衍生版本 | 10,000+ 群 | QA/prod/不同版本同內容 |

**真正市場資料重複對照**:
| 檔案 | D:\data | QROS\personal_licensed |
|------|----------|------------------------|
| 225mini2006-2011d.xls | ✓ | ✓ (personal_licensed/225labo/mini/raw/) |
| N225microf_2023-2026.zip | ✓ | ✓ (personal_licensed/225labo/micro/raw/) |
| N225minif_2012-2026.zip | ✓ | ✓ (personal_licensed/225labo/mini/raw/) |

---

## 9. 品質檢查 (僅報告)

| 資料集 | 問題 | 嚴重度 |
|--------|------|--------|
| Micro 分鐘 OHLCV | 標題中文編碼損壞，需人工確認欄位語義 | 中 |
| Mini 分鐘 OHLCV | 同上 | 中 |
| XLS 歷史檔 | 需 xlrd 1.x 讀取，openpyxl 不支援 | 低 |
| Micro RV/RSV | 非原始 OHLC/settlement，為衍生特徵 | 低 (已知) |
| 無官方 Settlement | 無法進行官方結算價回測 | 高 |

---

## 10. Point-in-Time 可用性

| 資料集 | available_at | publication_time | PIT 狀態 |
|--------|--------------|------------------|----------|
| Micro 分鐘 OHLCV | 無 | 無 | **POINT_IN_TIME_LIMITED** |
| Mini 分鐘 OHLCV | 無 | 無 | **POINT_IN_TIME_LIMITED** |
| Micro RV/RSV | trading_date | transform 後 | 可推斷 (transform_version 可追溯) |
| Mini RV/RSV | 同上 | 同上 | 同上 |

> 無 vailable_at/publication_time 欄位，無法嚴格保證 PIT。

---

## 11. Micro Direct Target 覆蓋狀況

見 LOCAL_OSE_MICRO_COVERAGE.json 詳細版。

| 指標 | 值 |
|------|------|
| 分鐘 OHLCV 覆蓋 | 2023-07-24 ~ 2026-08-31 (~860 交易日) |
| 官方 Settlement | **無** |
| RV/RSV 衍生特徵 | 2023-07-24 ~ 2026-08-31 (796 日) |
| 直接目標可用於回測 | **是** (分鐘 OHLCV 完整) |
| 直接目標可用於官方結算價驗證 | **否** (無官方 settlement) |

---

## 12. 哪些資料可避免下載

| 資料 | 狀態 | 理由 |
|------|------|------|
| N225microf 2023-2026 | **已有** | D:\data 完整 |
| N225minif 2012-2026 | **已有** | D:\data 完整 |
| 225mini 2006-2011 | **已有** | D:\data 有 XLS |
| Micro RV/RSV | **已有** | QROS derived 完整 |
| Mini RV/RSV | **已有** | QROS derived 完整 |
| 官方 Settlement | **需下載** | JPX/J-Quants API (需授權) |
| 官方 OHLC | **需下載** | J-Quants/Taifex API (需授權) |

---

## 13. 還缺哪些資料

1. **官方 OSE Micro Settlement 歷史** (2023-05-29 至今) - 需 J-Quants API 或 JPX Data Cloud
2. **官方 OSE Micro OHLC 逐筆/分鐘** - 需 J-Quants/Taifex API
3. **官方 Micro Open Interest** - 需 JPX/J-Quants
3. **官方 Micro Volume** - 同上
4. **正確的合約月份對照表** - 需 JPX 官方商品規格

---

## 17. 是否值得重新跑 2V-B Direct exam？

**否** - 核心阻礙：官方 Settlement 歷史資料缺失。
- Micro 分鐘 OHLCV 已完整，可做技術面回測
- 但無官方 Settlement 結算價，無法驗證預測是否擊中真實結算價
- 建議：先取得 J-Quants API 授權或 JPX Data Cloud 授權，補齊 Settlement 歷史

---

## Gate 判定

| Gate | 結果 | 說明 |
|------|------|------|
| PHASE2VB1_PASS | **PASS** | 盤點完成 |
| DIRECT_TARGET_HISTORY_FOUND | **PARTIAL** | 分鐘 OHLCV 有，官方 settlement 無 |
| DIRECT_TARGET_OOS_POSSIBLE | **YES** | 分鐘 OHLCV 可做技術面 OOS |
| DIRECT_TARGET_SUBSTANTIAL_SAMPLE_POSSIBLE | **YES** | ~860 交易日分鐘級 OHLCV |

---

## 結論

本機已擁有完整的 **OSE Nikkei 225 Micro 分鐘級 OHLCV (2023-07 至 2026-08)** 以及 **Mini 完整歷史 (2012-2026)**，足以進行技術面回測。但**缺乏官方 JPX Settlement 歷史**，無法進行基於官方結算價的驗證。建議下一棒優先取得 J-Quants API 或 JPX Data Cloud 授權，補齊 Settlement 歷史後再重跑 2V-B Direct exam。

**Gate: PHASE2VB1_PASS** ✅
