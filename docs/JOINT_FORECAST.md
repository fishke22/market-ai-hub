# Joint Forecast（聯合情境預測）

## 三條獨立研究線（不得 chained error propagation）
禁止「先預測 NQ → 預測 USDJPY → 預測 VIX → 把單點預測塞給 Nikkei」。

1. **DIRECT FORECAST**：Current State → Nikkei Forecast（保留現有 Chronos/TimesFM/NHITS/NBEATSx/statistical）。
2. **JOINT FORECAST**：Cross-Asset Current State → Joint Future State Distribution。
3. **SCENARIO FORECAST**：Possible Cross-Asset Paths → Conditional Nikkei Distribution。

三者由 Forecast Synthesis Layer 統合，**保留 provenance，不能混成一個無法解釋的數字**。

## JointForecastResult 合約（`forecast/contract.py`）
- joint_forecast_id / created_at / information_cutoff / target / horizon / forecast_target_dates
- input_panel_version / feature_version / regime_version
- model_name / model_revision
- future_paths / factor_distributions / target_distribution
- p10 / p25 / p50 / p75 / p90
- sampling_method / sample_count / seed
- calibration_status / data_quality / model_status

## Joint baselines（`forecast/joint_baselines.py`，先建立可解釋模型）
- `var_baseline`：VAR(1)（多變量最小平方法估係數 + residual cov → Monte Carlo）
- `factor_baseline`：Dynamic Factor（PCA 第一主成分 common factor + AR(1) + idio noise）
- `kalman_baseline`：State-Space local-level（random walk，per-asset 波動）

未來若 TSFM（Chronos/TimesFM 等）真正支援 multivariate/covariates，才建 Joint Challenger Adapter；
**不能硬把 univariate model 包成 joint model**。

## Unknown / Known future（`forecast/leakage.py`）
- Unknown future（NQ/USDJPY/VIX/US10Y/SOX tomorrow）禁止用實際未來值；
  只能來自 joint model / scenario / persistence baseline / independent forecast。
- Known future（calendar/weekday/holiday/FOMC/BOJ/CPI/NFP schedule/expiry）可直接用。
- 提供 automated leakage test（`assert_no_future_leak`）。

## Direct vs Joint 分開計分
Direct Forecast 與 Joint Forecast 分開計分；不得因 Joint 出現就刪 Direct model。
