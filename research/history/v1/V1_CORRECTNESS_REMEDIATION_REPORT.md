# V1_CORRECTNESS_REMEDIATION_REPORT.md

日期：2026-09-19
範圍：`D:\MARKET_AI_HUB`（market-ai MCP V1 正確性修復）
Gate：**READY_FOR_PROMPT_REWRITE**

---

## 1. PRE-FLIGHT

| 檢查 | 結果 |
|------|------|
| git status / branch / uncommitted | **D:\MARKET_AI_HUB 不是 git repo**（建置時即無 .git）。因此無 reset/checkout 風險；施工前已將 `src\` 與 `tests\` 完整備份至 `D:\MARKET_AI_HUB\.remediation_backup_20260919\` |
| Python env | `.venv` = CPython 3.12.13（uv）；`.venv-fincast` 存在（FinCast 隔離） |
| 現有測試 | 施工前 56 passed（pytest，全部） |
| MCP tool 名稱 | 11 個（health_check / get_system_info / get_data_source_status / get_market_data / predict_chronos / predict_timesfm / predict_ensemble / get_model_performance / backtest / analyze_osaka_nikkei / analyze_taiwan_stock） |
| Chronos/TimesFM/XGB/LGBM 模組 | `models/chronos_model.py`、`models/timesfm_model.py`、`models/baseline_ml.py`（XGB/LGBM 同模組） |
| predict_ensemble | `mcp/server.py` + `ensemble/ensemble.py` |
| analyze_osaka_nikkei / analyze_taiwan_stock | `services/analysis.py` |
| get_model_performance / backtest | `mcp/server.py` + `storage/performance.py` + `backtest/walk_forward.py` |

## 2. 找到的真正 Root Cause（全部以原始碼確認）

1. **Horizon bug**（CRITICAL）：`mcp/server.py` 與 `services/analysis.py` 皆為
   `steps = 1 if horizon in ("5m","15m","30m","60m") else 7`。
   → 1d/2d/5d/10d 全部傳 7 給底層；且 `2d`/`5d`/`10d` 根本沒有被數值解析。
   疊加：Chronos adapter `t[0,:,:].mean(axis=1)`、TimesFM adapter `qmat.mean(axis=0)`
   把整個 horizon 的輸出平均成一個數字 → 路徑被丟棄 → 所有 horizon 輸出相同。
   疊加：baseline classifier 完全忽略 horizon（永遠 1-step label + threshold drift）。
2. **XGBoost inf/overflow**：`features/features.py` 的 `log_returns=log(close/close.shift(1))`、
   `pct_change()`、`distance_from_ma20=close/sma_20-1` 在分母 0 / log(0) 時產生 ±inf，
   直接送進 XGBoost DMatrix → `gradient_index.h` crash（3706.TW 實測觸發）。
   全 pipeline 無任何 sanitation。
3. **50% 誤導**：backtest 只給 directional_accuracy，無 uniform（1/3）與 majority-class
   baseline 對照；外部 Agent 容易把 50% 當共同門檻。
4. **角色混淆**：ensemble 與 wrapper 的 direction 都可能被當成額外獨立模型證據，
   無 independent_model_count / model_role 概念。

## 3. Horizon bug 原因（同上第 1 點）

`mcp/server.py:142/154/170` 與 `services/analysis.py:55/153` 的
`1 if horizon in (5m..60m) else 7`；加上兩個 TS adapter 的 horizon 平均化
（`chronos_model.py:75`、`timesfm_model.py:82`）；加上 classifier 只用 1-step label。

## 4. Horizon 修復方式

- 新增 `services/horizon.py`：`parse_horizon("Nd", data_frequency="1d")` →
  `HorizonSpec(requested_horizon, effective_horizon_steps, supported, reason)`。
  **語義定案：`d` = trading bar / trading day**（非 calendar day）；日線資料時
  `1d/2d/5d/10d` → 1/2/5/10 步；日內（5m/15m/30m/60m）→
  `UNSUPPORTED_WITH_CURRENT_DATA`（不假造，不再偷偷回 1 步）。
- Chronos/TimesFM adapter 回傳 **per-step path**（每步 p10/p50/p90），
  horizon 參數真實傳入底層 `prediction_length` / `horizon`。
- `ForecastOutput` 新增（全部 additive）：
  `requested_horizon` / `effective_horizon_steps` / `data_frequency` /
  `horizon_applied` / `forecast_path`（逐 step） / `forecast_dates`（trading-day） /
  `terminal_forecast`。`point_forecast`/`expected_return` 改以 terminal 計算。
- baseline classifier：label 改用 k-bar forward return（`future_return_k`），
  k = requested horizon steps；point estimate 改用訓練窗「實證 class mean return」。
- Ensemble：對有 path 的 component（Chronos/TimesFM）逐 step 加權，產生 ensemble path。
- 不是靠 offset 做出 2d≠5d；路徑長度與 terminal 都由模型真實多步輸出產生。

## 5. XGBoost bug 原因（同上第 2 點）

3706.TW（TWSE 資料含 0 成交 / 極端值）→ feature 矩陣含 ±inf →
XGBoost `gradient_index.h` 崩潰。驗證：修復前對 3706.TW 跑 backtest 直接 crash。

## 6. XGBoost 修復方式

- **feature construction 層**（`features/features.py`）：
  - `_safe_pct()`：分母 0 → NaN 的 pct_change
  - `_safe_log_return()`：close≤0 → NaN 的 log return
  - `distance_from_ma20`：sma_20=0 → NaN
  - `sanitize()`：±inf 統一轉 NaN（tree 模型原生 missing representation）
  - **training 與 inference 共用同一 `build_features`，preprocessing 保證一致**
- 不用任意數字 clipping；`_rsi` 既有 1e-9 epsilon 保留（denominator guard）。
- XGBoost/LightGBM 原生處理 NaN；LR/RF 用 `SimpleImputer(median)`（fit 學習、inference 沿用）。
- 驗證：3706.TW backtest 不崩潰；`balanced_accuracy=0.3308`（見第 17 節）。

## 7. Base Model / Ensemble / Wrapper 實際架構（以原始碼為準）

```
Level A  BASE_MODEL（4 個獨立模型）
  chronos_model.chronos_forecast / timesfm_model.timesfm_forecast /
  baseline_ml.baseline_forecast(xgb) / baseline_ml.baseline_forecast(lgbm)
Level B  ENSEMBLE
  ensemble.ensemble_equal_weight(4 base ForecastOutput) → model_role=ENSEMBLE
Level C  ANALYSIS_WRAPPER
  services.analysis.analyze_osaka_nikkei / analyze_taiwan_stock
  → 內部呼叫 4 個 base forecast + ensemble（wrapper 不重算模型）
```
- predict_ensemble = 4 個 base + 1 個 ensemble（不是 5 個獨立模型）
- analyze_* = wrapper（不是第 6 個獨立模型）；`model_role` 欄位已進所有輸出
- MCP 層 `get_system_info` 回傳各 model 的 role / 雙狀態 / eligibility

## 8. 三分類實際 Flat threshold（由程式碼取得）

- `baseline_ml.FLAT_THRESHOLD = 0.005`（固定 0.5%），作用於 **k-bar 累積報酬**
  （k = horizon steps）。非 ATR / volatility adjusted（未實作，已註明）。
- classes = [-1(up 外? 實際 -1=down), 0=flat, 1=up]，label 規則：
  `future_return_k > +0.005 → 1；< -0.005 → -1；else 0`

## 9. 真實 class distribution（3706.TW, 1y walk-forward train 窗口）

`{'up': 0.4067, 'flat': 0.1726, 'down': 0.4206}`（stored record）。
→ majority baseline = 0.4206；uniform = 0.3333；**50% 不是門檻**。

## 10. 各 baseline

| Baseline | 值 / 來源 |
|----------|-----------|
| uniform_random_baseline_accuracy | 1/3 ≈ 0.3333（三類隨機） |
| majority_class_baseline_accuracy | train 分佈最大類頻率（上例 0.4206） |
| naive majority-class OOS accuracy | 0.4286（3706.TW 實測，見第 17 節） |
| last_price_naive / drift / moving_average（時間序列） | `services/validation.py` |
| MASE | 模型 MAE / last-price naive MAE（TS 驗證框架） |

分類判定門檻 = `max(majority_class_baseline_accuracy, uniform_random_baseline_accuracy)`。

## 11. 各模型 engineering status

| Model | engineering_status | 證據 |
|-------|--------------------|------|
| chronos-2 | **PASS** | CPU/CUDA load + 多步 path quantile 輸出 PASS |
| timesfm-3.0 | **PASS** | CUDA load + univariate path + multivariate + past-only cov PASS |
| xgboost | **PASS** | 3706.TW（原崩潰標的）fit/predict 不再 crash |
| lightgbm | **PASS** | 同上 |
| fincast | **PASS** | 隔離 venv bridge load + forecast OK |
| ensemble | **PASS** | component metadata + 權重和=1 |

## 12. 各模型 predictive_validation_status

| Model | Status | 原因 |
|-------|--------|------|
| chronos-2 | **UNVALIDATED** | 無完整 OOS walk-forward；smoke PASS ≠ VALIDATED |
| timesfm-3.0 | **UNVALIDATED** | 同上 |
| xgboost (3706.TW record) | **DEGRADED** | balanced_acc 0.3308 < baseline_threshold 0.4206 |
| lightgbm | **UNVALIDATED** | 本輪無新 OOS record（v1 legacy record 缺新指標） |
| ensemble | **UNVALIDATED** | 隨 component |

## 13. Research Gate

| Gate | Status | Reason |
|------|--------|--------|
| ENGINEERING_GATE | **PASS** | 必修 base models（chronos/timesfm/xgb/lgbm）工程狀態全 PASS |
| DATA_GATE | **PASS** | yfinance + TWSE 皆 ok（live 驗證） |
| MODEL_PREDICTIVE_GATE | **UNPROVEN** | 無任何模型在完整 OOS 上被證明超越 baseline |
| TRADING_EDGE_GATE | **UNPROVEN** | 無策略規則/費用/滑價/execution assumptions；不因單一 Sharpe 判 FAIL |

可查詢：MCP tool `get_research_gates` + `get_system_info.research_gates`。

## 14. Ensemble 實際權重

- method：**EQUAL_WEIGHT_RESEARCH**（每 component 25%；EXPERIMENTAL 標記）
- 排除規則：engineering FAIL 或 predictive REJECTED 的 component 不進平均，
  weights 對剩餘 component renormalize 並寫入 warnings
- 輸出：`component_models` / `weights` / `weighting_method` / `experimental` /
  `excluded_components` / `path_components` / `model_agreement`
- 未使用 performance weighting（無足夠可靠 OOS 指標；介面保留）

## 15. 新增 / 修改檔案

新增：
- `src/market_ai_hub/services/horizon.py`（horizon 解析 + trading-day 日期）
- `src/market_ai_hub/services/model_catalog.py`（角色/雙狀態/eligibility/gates）
- `src/market_ai_hub/services/validation.py`（naive baselines + OOS 評估框架）
- `tests/test_horizon.py`、`tests/test_horizon_integrity.py`、`tests/test_feature_sanitation.py`、
  `tests/test_model_roles.py`、`tests/test_classification_baselines.py`、
  `tests/acceptance_v1_remediation.py`
- `D:\MARKET_AI_HUB\.remediation_backup_20260919\`（施工前備份）

修改：
- `schemas/market_data.py`（ForecastOutput additive 擴充、ModelRole/雙狀態/GateStatus enum）
- `schemas/backtest.py`（additive：分類指標/baselines/status 欄位，缺值 = None 非 0）
- `models/chronos_model.py`、`models/timesfm_model.py`（per-step path）
- `models/baseline_ml.py`（k-step label、class metadata、實證 mean-return 映射、imputation）
- `features/features.py`（sanitation：±inf→NaN、safe denominator）
- `ensemble/ensemble.py`（component metadata、eligibility 過濾、path 合成、independent_vote_summary）
- `services/analysis.py`（ANALYSIS_WRAPPER 角色、used_* 清單、analysis_direction、.TW 後綴容錯）
- `backtest/walk_forward.py`（classification_metrics + baselines）
- `storage/performance.py`（additive `backtests_v2` 表；v1 表保留；v2 空時 fallback v1_legacy）
- `mcp/server.py`（horizon 傳遞、predict_ensemble 頂層 horizon 欄位、backtest 分類指標、
  get_model_performance 擴充、get_system_info 擴充、新增 get_research_gates / run_ts_validation tools）
- `tests/smoke_chronos.py`、`tests/smoke_timesfm.py`、`tests/test_chronos_smoke.py`、
  `tests/test_timesfm_smoke.py`（**修改原因**：原測試驗證「flat quantile dict」，該行為就是
  horizon 平均化 bug 本身 → 改驗證 per-step path）

## 16. 所有測試指令

```powershell
# 完整（unit + integration，模型用快取）
D:\MARKET_AI_HUB\.venv\Scripts\python.exe -m pytest D:\MARKET_AI_HUB\tests -q
# 只跑 unit（快）
D:\MARKET_AI_HUB\.venv\Scripts\python.exe -m pytest D:\MARKET_AI_HUB\tests -q -m "not integration"
# MCP stdio smoke
D:\MARKET_AI_HUB\.venv\Scripts\python.exe D:\MARKET_AI_HUB\tests\smoke_mcp.py
# Manual acceptance（真實 MCP + live 資料）
D:\MARKET_AI_HUB\.venv\Scripts\python.exe D:\MARKET_AI_HUB\tests\acceptance_v1_remediation.py
```

## 17. 測試結果

- pytest 完整：**93 passed, 0 failed**（79 unit + 14 integration，73s）
- MCP smoke：**PASS**（13 tools：原 11 + get_research_gates + run_ts_validation；tool 名稱未改動）
- Acceptance（真實 MCP stdio + live 資料）：
  - predict_chronos / predict_timesfm / predict_ensemble × {^N225, 3706.TW} × {1d,2d,5d,10d}
    = 24/24 PASS：requested_horizon 正確、effective_steps 正確、path 長度正確、terminal 對齊
  - analyze_osaka_nikkei：role=ANALYSIS_WRAPPER、analysis_direction、independent_model_count=0
    （無模型通過 OOS → 不計假票）、used_* 清單完整
  - analyze_taiwan_stock/3706.TW：role=ANALYSIS_WRAPPER；xgb/lgbm 因「train 只有單一類別」誠實
    回 unavailable（不硬 fit），ensemble 由 chronos/timesfm 完成
  - get_model_performance：baseline_note 存在；缺值欄位 = null
  - gates：ENGINEERING=PASS、DATA=PASS、MODEL_PREDICTIVE=UNPROVEN、TRADING_EDGE=UNPROVEN
- XGBoost 3706.TW live backtest：**不再 crash**；balanced_acc=0.3308 < majority baseline 0.4206
  → beats_baseline=False → eligible_for_direction_vote=False（規則由實際績效支持）

## 18. Manual acceptance test 結果

**ACCEPTANCE: PASS（26/26 checks）**
報告檔：`reports/v1_remediation_acceptance.json`

## 19. 尚未解決問題（誠實列出）

1. Chronos/TimesFM 仍 **UNVALIDATED**：無完整 OOS walk-forward 證據。已提供
   `run_ts_validation`（bounded walk-forward vs naive）框架，但本輪未對兩模型跑完整驗證；
   即使跑過也只能到 EXPERIMENTAL，完整多週期 OOS 才可能 VALIDATED。
2. 分類器（xgb/lgbm）現有 OOS 皆未超越 majority baseline → 不參與 direction vote。
   這是正確結果，不是 bug；未來需更好 features 才可能翻轉。
3. 日內 horizon（5m/15m/30m/60m）在日線資料下現在**明確回 UNSUPPORTED_WITH_CURRENT_DATA**
   （v1 曾偷偷回 1 步）。這是刻意行為變更（正確性修復），非 breaking 相容問題：
   tool 名稱/參數不變，僅結果從假造變成誠實拒絕。
4. performance.duckdb 的 v1 legacy records 缺新指標欄位（balanced_accuracy 等），
   list 時標 `schema_version: "v1_legacy"`、缺欄為 null；不刪舊資料。
5. FinCast bridge 仍無 quantile/path 輸出 → 不進 ensemble（eligibility=false，明示）。

## 20. Gate

**READY_FOR_PROMPT_REWRITE**
