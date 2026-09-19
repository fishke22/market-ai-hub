# V1_2_TEMPORAL_SEMANTIC_FINAL_REPORT.md

日期：2026-09-19
範圍：`D:\MARKET_AI_HUB`（V1.2 TEMPORAL & SEMANTIC FINALIZATION）
Gate：**READY_FOR_V1_FREEZE**

---

## 1. Root causes

1. **Forecast target date off-by-one**：forecast 路徑的第一個日期被標成「最後一根已觀察 bar」而非「下一個未來 session」。
   - `tse_trading_dates(last_ts, n)` 用 `schedule.index[:n]` 會**包含** last_ts 本身（^N225 off-by-one）。
   - `forecast_dates_from_series` 用 `bdate_range(start=last_ts)[1:]` 依賴 last_ts 精確等於最後 bar 日期，但 closes 序列一度用「整數 row index」當日期 → 產生 1970 epoch 日期（V1.1 已發現並修正），且對 3706.TW 的 1d 目標仍可能落在 last observed。
2. **trading_date 未正規化**：直接拿 UTC calendar date 當 trading_date 會少一天（TWSE 日 bar 的 UTC 常是前一日 16:00Z = Taipei 當日 00:00）。
3. **TWSE 日曆用 WEEKEND_ONLY_APPROX**：會漏掉台灣中秋節/彈性放假，也不含補班交易日。
4. **Direction ensemble 語義模糊**：`direction` 同時可能來自 vote 或 probability argmax，兩者衝突時無標記。
5. **Classifier probability 未標明 calibration 狀態**：raw tree proba 可能被誤讀為真實機率。

## 2. Date anchor fix

新增 `services/calendar.forecast_anchor(symbol, last_ts, steps)`，產出：
- `forecast_origin`：最後一根已觀察 bar 的 UTC 時間戳（ISO）
- `last_observed_trading_date`：該 bar 在交易所時區的交易日
- `forecast_target_dates`：**嚴格在 last_observed 之後**的未來 N 個 sessions

驗證：3706.TW last_observed=2026-09-18 → 1d target=2026-09-21（非 09-18）；^N225 last_observed=09-18 → 5d targets=[09-24, 09-25, 09-28, 09-29, 09-30]。

## 3. Timezone model

- 每個 symbol 有 `exchange_timezone`：TWSE=Asia/Taipei、TSE/^N225=Asia/Tokyo。
- `trading_date_of(ts_utc, symbol)`：UTC 時間戳 → 交易所當地日期。
- ForecastOutput 新增 `exchange_timezone` / `forecast_origin` / `last_observed_trading_date` / `forecast_target_dates`。
- 回歸測試：`2026-09-17T16:00Z` → TWSE trading_date=2026-09-18（不少一天）；`2026-09-17T15:00Z` → Tokyo=2026-09-18。

## 4. trading_date semantics

- trading_date = bar 的**交易所當地日期**，永遠從 exchange_timezone 推導，禁止用 UTC date。
- forecast_target_dates 只含 last_observed_trading_date 之後的 sessions，永不含已觀察 bar。

## 5. TWSE calendar source

改用 **`exchange_calendars`（QuantConnect）XTAI**，取代 WEEKEND_ONLY_APPROX：
- 含台灣國定假日與彈性放假（實測：2026-09-25 中秋節、09-28 彈性放假正確休市）
- `calendar_name=XTAI`、`calendar_source=exchange_calendars (QuantConnect)`、`calendar_verified=true`、`calendar_last_verified=載入時間`、覆蓋至 2027-09-17
- 若 library 缺失/未覆蓋 → `calendar_grade=CALENDAR_UNVERIFIED`，禁止假裝 exact

## 6. ^N225 calendar handling

- ^N225 用 XTKS（TSE 現貨），2026-09-21 敬老之日 / 09-22 國民休日 / 09-23 秋分之日正確跳過。
- requested window 2026-09-21..25 → `CALENDAR_TARGET_MISMATCH` + `unmapped_sessions=[09-21,09-22,09-23]` + `proxy_target_calendar=XTKS`。
- forecast_target_dates 全是未來 TSE 現貨 bars，OSE Holiday 日期不冒充 ^N225 cash bars。

## 7. Direction ensemble resolution

`ensemble._resolve_direction`（固定規則，寫死在 code）：
- `vote_direction` = 分類器 component direction 的 plurality
- `probability_argmax_direction` = aggregated class probability 的 argmax
- `final_direction` = vote 優先 → probability argmax → price plurality → no_evidence
- `direction_resolution_method` = vote_priority / probability_argmax / price_plurality / no_evidence
- `direction_disagreement` = vote 與 argmax 皆存在且不同 → true（不偷偷 tie-break）

實測（^N225）：vote=flat、argmax=up、final=flat、method=vote_priority、disagreement=true —— 正確呈現衝突，不隱藏。

## 8. Probability calibration status

分類器輸出新增：`probability_available=true`、`probability_calibrated=false`、`calibration_method=none`、`calibration_sample_size=null`、`calibration_metrics={brier_score: null, ece: null}`。
語義：raw tree proba 未校準，外部 Agent 不得把 0.84 讀成「84% 機率」，只能說「原始分類分數主要偏向上漲類別」（warning 已明示）。

## 9. Gates

新增子 gate（DATA_GATE 由子 gate 綜合）：
| Gate | Status | 說明 |
|------|--------|------|
| MARKET_DATA_GATE | PASS | yfinance + TWSE ok |
| CALENDAR_GATE | PASS | XTAI + XTKS 載入且覆蓋未來 |
| TEMPORAL_ALIGNMENT_GATE | PASS | forecast targets future-only 自檢 |
| DATA_GATE | PASS | 三子 gate 全 PASS |
| ENGINEERING_GATE | PASS | current runtime |
| MODEL_PREDICTIVE_GATE | UNPROVEN | 無模型 OOS 超越 baseline |
| TRADING_EDGE_GATE | UNPROVEN | 無策略/費用/滑價 |

所有 gate 皆帶 `evaluated_at` + `build_id` + `evidence`。

## 10. Tests

```
python -m pytest tests -q        → 135 passed（121 unit + 14 integration，68s）
python tests/smoke_mcp.py        → MCP SMOKE: PASS（13 tools）
python tests/acceptance_v1_2.py  → ACCEPTANCE: PASS（12/12）
```

新增/更新（H.1–H.12 全覆蓋）：test_target_calendar.py（future-only、時區、假日、OSE mismatch、stale calendar）、test_direction_and_calibration.py（vote/argmax disagreement、calibration metadata）。既有 125 測試保留，僅依新 gate 集合更新 `test_gates_defaults`。

## 11. Manual acceptance（Cherry Studio 相同啟動命令）

- build_id = **7140be6ab3e6c6e4**（V1.2）
- 3706.TW 1d/2d/5d/10d：last_observed=09-18、targets 全未來、exchange_timezone=Asia/Taipei、calendar_verified=true、無歷史日期
- ^N225 requested 09-21..25：CALENDAR_TARGET_MISMATCH、unmapped=[21/22/23]、targets=[24/25/28/29/30]
- direction ensemble：vote=flat vs argmax=up → disagreement=true、final=vote_priority
- XGB calibration：probability_calibrated=false、method=none
- gates：MARKET_DATA/CALENDAR/TEMPORAL/DATA/ENGINEERING 全 PASS

## 12. Unresolved issues（誠實列出）

1. **Cherry Studio 需重啟 MCP process** 才能載入 V1.2（long-running process 持有舊 code）；以 `health_check.build.build_id == 7140be6ab3e6c6e4` 驗證。
2. TS 模型（chronos/timesfm）仍 UNVALIDATED（OOS 未達門檻）。
3. OSE futures session 日曆仍無免費來源 → Holiday Trading 不映射（維持 CALENDAR_TARGET_MISMATCH）。
4. 分類器 probability 未 calibrate（明確標記，未實作 isotonic/platt）。
5. `calendar_last_verified` 為「載入時間」，非官方日曆版本更新戳（exchange_calendars 無版本戳）。

## Gate

**READY_FOR_V1_FREEZE**

Forecast targets 全未來、Timezone 正確、TWSE（XTAI）與 ^N225（XTKS）日曆正確、Direction 語義唯一（fixed rule + disagreement 標記）、Probability calibration metadata 正確。
