# V1_1_FINAL_VALIDATION_REPORT.md

日期：2026-09-19
範圍：`D:\MARKET_AI_HUB`（V1.1 FINAL VALIDATION & RUNTIME CONSISTENCY REMEDIATION）
Gate：**READY_FOR_V1_PROMPT_FREEZE**

---

## 1. Cherry Studio 原本為何仍看到舊 bug（Root Cause，有證據）

**主因：Cherry Studio 的 MCP server 是 long-running process，它持有的是「啟動時」的程式碼。**

證據鏈：
1. `logs\mcp.log` 記錄的 XGBoost crash traceback 指向 **舊版 server.py line 225**（舊版 layout 的 `backtest → m.fit`；新版 line 225 已是 predict_timesfm 的 dict）。xgboost 內部時鐘 `[15:16:08]` 落在 V1 remediation 程式碼寫入（15:52–16:06）**之前**。
2. 現行程式（fix 後）以完全相同啟動命令 fresh spawn 實測：`backtest 3706.TW xgb` 不 crash、2d/5d path 長度不同、ENGINEERING_GATE=PASS。
3. 進程表：Cherry Studio（`C:\Program Files\Cherry Studio\Cherry Studio.exe`）spawn 的 `market-ai-mcp.exe` 於 16:41:02 啟動；本輪 V1.1 程式碼寫入晚於該時間 → **Cherry Studio 目前仍持有 pre-V1.1 process**。
4. Cherry Studio 設定本身正確：`mcp_server` 表 `market-ai` → `D:\MARKET_AI_HUB\.venv\Scripts\market-ai-mcp.exe`、args=[]、is_active=1。只有一個 market-ai 條目。

**次要風險（本輪已修）**：gate 評估每次 new adapter → 反覆載入模型進 VRAM，長期執行會 OOM → status 變 FAIL → ENGINEERING_GATE 掉 PARTIAL。現改為 process-level singleton（`services/model_runtime.py`）。

**使用者需要做的動作**：在 Cherry Studio 把 `market-ai` MCP 開關關掉再打開（或重啟 Cherry Studio），讓它 spawn 新 process；之後可用 `health_check.build.build_id` 驗證。

## 2. Runtime identity（build fingerprint）

新增 `services/build_info.py`。所有重要 response 皆含：

| 欄位 | 值 |
|------|-----|
| market_ai_version | 1.1.0 |
| build_id | **e77d9c9a2f0a015b**（13 個關鍵 source 檔內容 sha256，code 一變 id 就變） |
| git_commit | N/A (not a git repo) |
| source_root | D:\MARKET_AI_HUB |
| python_executable | D:\MARKET_AI_HUB\.venv\Scripts\python.exe |
| server_started_at | server process 啟動時間（ISO UTC） |
| schema_version | 1.1 |

注入位置：`health_check.build`、`get_system_info.build`、`get_research_gates`（經 gate）、`predict_chronos` / `predict_timesfm` / `predict_ensemble`（頂層 build + ForecastOutput 欄位）、`analyze_osaka_nikkei` / `analyze_taiwan_stock`（頂層）。

## 3. 修正後 build id

`e77d9c9a2f0a015b`（寫報告當下）。使用者可在 Cherry Studio 呼叫 health_check，比對 `build.build_id` 是否等於此值，不等 = 仍是舊 process。

## 4. Quantile contract

- `validate_quantiles()`：有值就必須 `p10 <= p50 <= p90`；違反 = invalid（**不排序、不靜默修復**），`quantile_valid=false` + warning，且**不得進入 ensemble price 聚合**。
- 分類器（XGBoost/LightGBM）沒有 predictive quantile → `quantile_type=NOT_AVAILABLE`，`quantiles={"p10": null, "p50": null, "p90": null}`，heuristic spread 改名 `lower_reference` / `upper_reference`。
- Ensemble price 層只聚合 `quantile_type=PREDICTIVE` 且 valid 的 component。

## 5. Model task separation

- `model_task`：chronos/timesfm/fincast = **PRICE_FORECAST**；xgb/lgbm/lr/rf = **DIRECTION_CLASSIFICATION**。
- PRICE_FORECAST 輸出：forecast_path / point_forecast / 真 quantile / MAE/RMSE/MASE（OOS 驗證後）。
- DIRECTION_CLASSIFICATION 輸出：direction、class_probabilities（標記 `class_probabilities_calibrated=false`，tree ensemble 原生 proba 未 calibration，**不宣稱機率已校準**）、accuracy/balanced_accuracy/macro_f1/mcc/baselines（在 backtest 與 model_metadata）。

## 6. Ensemble semantics（price / direction 分層）

- `price_ensemble`：只聚合 PRICE_FORECAST 真 quantile + 逐 step path。
- `direction_ensemble`：只聚合 DIRECTION_CLASSIFICATION 的方向與 class probabilities。
- 分類器 heuristic spread **永不污染價格 quantile**。
- legacy 欄位（`point_forecast`/`quantiles`/`direction` 頂層）保留但標 `legacy_research_only=true`。
- `validation_level=RESEARCH`（所有 component 皆未 VALIDATED 時，不得稱 validated ensemble）。

## 7. Eligible models（component table）

Ensemble 回傳 `component_table`：每 component 有 `component / role / model_task / engineering_status / predictive_validation_status / eligible / raw_weight / effective_weight / excluded_reason`。
排除規則：engineering FAIL 或 predictive REJECTED → excluded（effective_weight=0，weights 對剩餘 renormalize 並寫 warning）。

## 8. Target-calendar handling

- 新增 `services/calendar.py`（pandas-market-calendars XTKS）。^N225 forecast_dates 用 **TSE 交易日**（2026-09-21 敬老之日、9/22 國民休日、9/23 秋分之日 會正確跳過）。
- `analyze_osaka_nikkei` 新增選用參數 `requested_dates`（如 `2026-09-21..2026-09-25`）。窗口含 TSE 休市日 → `calendar_mismatch=true` + `CALENDAR_TARGET_MISMATCH` detail：模型預測的是 ^N225 未來 N 根 TSE 現貨 bars，不是 OSE Holiday Sessions 的逐日預測，**不做日期映射**。
- 輸出：`target_calendar` / `target_trading_dates` / `requested_calendar_window` / `requested_market_sessions` / `calendar_grade`。
- **本輪修正的真 bug**：forecast dates 之前用整數 row index 當日期 → 產生 1970 epoch 日期；已改為 DatetimeIndex。

## 9. OOS validation framework（rolling origins + interval）

`run_ts_validation`（MCP tool）：rolling origins、no look-ahead、每 fold 預測下一 bar；比較 last-price naive / drift / MA baselines（MAE/RMSE/MASE）；interval：nominal p10-p90=80% 的實測 `coverage`、`width_mean_rel`、`calibration_error`。結果持久化（`ts_validation.duckdb`）。

**Promotion rule（寫死在 code：`services/validation.py PROMOTION_RULES`，LLM 不得臨時改）**：
- UNVALIDATED→EXPERIMENTAL：≥3 origins、≥10 OOS、MAE 打敗 last-price naive
- EXPERIMENTAL→VALIDATED：≥8 origins、≥50 OOS、MASE≤1.0、打敗 naive+drift、≥2 windows

實測結果（^N225, chronos-2）：
- 5 folds：MASE 0.82、beats naive → 但 n_oos=5<10 → **UNVALIDATED**（正確拒絕）
- 12 folds：MASE 1.94、未打敗 naive → **UNVALIDATED**（coverage 83.3%、calib_err 0.033）
- 同一模型兩個 window 結論不同 = 單一 window 不可信，正是 promotion rules 防護的狀況。

## 10. 目前每個模型真正 validation status

| Model | engineering | predictive_validation | 依據 |
|-------|-------------|----------------------|------|
| chronos-2 | PASS | **UNVALIDATED**（OOS 未達 EXPERIMENTAL 門檻） | 12-fold run：MASE 1.94 未打敗 naive |
| timesfm-3.0 | PASS | **UNVALIDATED** | 未跑 OOS |
| xgboost | PASS | **DEGRADED**（3706.TW record: bal_acc 0.312 < baseline 0.421） | stored OOS record |
| lightgbm | PASS | UNVALIDATED（無有效新 OOS record） | — |
| fincast | PASS | UNVALIDATED | bridge 未驗證 |
| ensemble | PASS | UNVALIDATED | 隨 component |

## 11. Research Gates（current runtime + freshness）

| Gate | Status | evaluated_at / build_id |
|------|--------|------------------------|
| ENGINEERING_GATE | **PASS** | 每 call 重算（singleton 載入），含 evaluated_at + build_id + 4 models evidence |
| DATA_GATE | **PASS** | yfinance + TWSE ok |
| MODEL_PREDICTIVE_GATE | **UNPROVEN** | 無模型達 EXPERIMENTAL 以上 |
| TRADING_EDGE_GATE | **UNPROVEN** | 無策略/費用/滑價/execution assumptions |

count semantics：`independent_base_model_count=4`、`eligible_direction_vote_count=0`、`eligible_price_reference_count=2`（分開，不再混成一個數字）。
confidence_inputs：data_quality / data_freshness_hours / sample_size / oos_validation_status / baseline_outperformance / interval_calibration / regime_performance=NOT_AVAILABLE / model_disagreement。

## 12. Tests

```
python -m pytest tests -q                → 125 passed（111 unit + 14 integration，65s）
python tests/smoke_mcp.py                → MCP SMOKE: PASS（13 tools）
python tests/acceptance_v1_1.py          → ACCEPTANCE: PASS（8/8 checks）
```

新增/更新測試：runtime identity、build fingerprint、quantile monotonicity、classifier/price-model role、ensemble eligibility + component table、target-calendar mismatch（2026 日本連假）、3706 XGB regression、^N225 holiday-calendar、OOS validation + promotion rules、gate freshness。舊測試全部保留（4 個依 V1.1 語義更新：count semantics 拆分與 singleton 注入，理由見報告）。

## 13. Manual acceptance（Cherry Studio 完全相同啟動方式：`D:\MARKET_AI_HUB\.venv\Scripts\market-ai-mcp.exe`，無 args）

- build fingerprint：PASS（build_id / source_root / python_executable 皆回傳）
- 3706.TW：chronos/timesfm 1d/2d/5d/10d 全 PASS（steps/path/terminal/build_id）；xgb backtest 不 crash
- ^N225：quantile contract 全合法；holiday calendar：requested 2026-09-21..25 → CALENDAR_TARGET_MISMATCH，target_trading_dates 正確跳過 21/22/23
- ensemble：price=[chronos-2, timesfm-3.0]、direction=[xgb, lgbm]、validation_level=RESEARCH、component_table 4 entries
- gates：ENGINEERING_GATE=PASS（evaluated_at + build_id + evidence）

## 14. Unresolved issues（誠實列出）

1. **Cherry Studio 目前持有的 process 仍是 pre-V1.1**。使用者必須在 Cherry Studio 切換 market-ai MCP 開關（或重啟）讓新 process 生效；生效後以 `health_check.build.build_id == e77d9c9a2f0a015b` 驗證。
2. TS 模型（chronos/timesfm）皆 UNVALIDATED；12-fold 實測 chronos 未打敗 naive（MASE 1.94）。要達 EXPERIMENTAL 需更多 data 或更好的資料源（如付費 JPX DataCube，本專案不購買）。
3. TW 股票 forecast_dates 為 WEEKEND_ONLY_APPROX（無免費 TWSE 官方日曆套件）。
4. 分類器 class probabilities 未 calibrated（已明示標記）；如需 calibrated probabilities 需 isotonic/Platt（未實作，超出 V1 範圍）。
5. `interval_coverage` 樣本少（≤12），覆蓋率數字僅供參考，已隨 n_oos 呈現。

## 15. Gate

**READY_FOR_V1_PROMPT_FREEZE**

Runtime 一致（fingerprint 可驗證）、Horizon 正常、3706 XGB 不 crash、Quantile Contract 正常、calendar mismatch 正確處理、model roles 正確。唯一剩餘動作是使用者重啟 Cherry Studio 的 MCP process（系統已提供驗證手段）。
