# Phase 2G — Joint Scenario Forecast + Dynamic Ensemble + Regime Router

- Gate: **PHASE2G_PASS**
- build_id: `bbf3cb2f9a80d20e`（未變，V1 相容）
- 測試：**279 passed**（154 V1 + 12 2A + 12 2B + 17 2C + 16 2D + 15 2D.1 + 14 2E + 18 2F + 21 2G）

## 交付內容（對照 A–Z）

| 項 | 交付 | 檔案 |
|---|---|---|
| A | 三條獨立研究線（direct/joint/scenario） | `forecast/` + `synthesis.py` |
| B | JointForecastResult contract | `forecast/contract.py` |
| C | Unknown/known future leakage guard | `forecast/leakage.py` |
| D | Joint baselines（VAR/Factor/Kalman） | `forecast/joint_baselines.py` |
| E/F/G | ScenarioEngine + 8 scenario types + weight 語義 | `forecast/scenario.py` |
| H | Direct track 分開計分 | `synthesis.py`（direct 欄位獨立） |
| I/J/M | DynamicEnsembleEngine + weight method v1 | `dynamic_ensemble.py` + `weights.py` |
| K/L | RegimeModelRouter + 樣本安全 | `regime_router.py` |
| N | Model 失敗 skip（MODEL_SKIPPED_RUNTIME） | `dynamic_ensemble.py::run_safe` |
| O/Q/R/S | ForecastSynthesis + research_center + edge + state | `synthesis.py` |
| P | Ensemble quantile 語義 | `dynamic_ensemble.py` |
| T/U | Same-exam backtest + metrics | `backtest.py` |
| V | Forward test registration | `registration.py` |
| W | Auto routing 限制（AUTO_TRADE=false） | `contract.py` |
| X | 測試（21 項） | `tests/test_phase2g.py` |
| Y | 文件（5 份繁中） | `docs/*.md` |
| Z | 本報告 + 交接 | `PHASE2G_JOINT_FORECAST_REPORT.md` + `CURRENT_HANDOFF.md` |

## 1. Joint Forecast models
- 三種可解釋 baseline：`var_baseline`（VAR(1)）、`factor_baseline`（PCA common factor + AR(1)）、
  `kalman_baseline`（State-Space local-level）。
- 皆 Monte Carlo 產生 `future_paths` + `target_distribution` + p10/p25/p50/p75/p90。
- 未把 univariate model 硬包成 joint；未來 Joint Challenger Adapter 才接 multivariate TSFM。

## 2. Joint baseline
- VAR(1)：多變量最小平方法估係數矩陣 + residual cov。
- Factor：SVD 第一主成分當 common factor，AR(1) + idio noise。
- Kalman：per-asset random walk（diagonal cov）。

## 3. Scenario Engine
- `ScenarioEngine.generate(current_state, scenario_types, horizon, seed)` → 8 種 ScenarioPath。
- scenario 由 `SCENARIO_SHOCKS`（deterministic cross-asset rule）產生，非 LLM 編數字。

## 4. Scenario weight semantics
- 預設 `scenario_weight` + `UNVALIDATED_WEIGHT`，不得稱機率/發生率/成功率。
- 僅 OOS calibration 後才 `CALIBRATED_PROBABILITY`。

## 5. Dynamic Ensemble method
- `weight_method_version=v1`：inverse normalized loss + calibration penalty +
  reliability penalty + sample shrinkage；deterministic + versioned。

## 6. Regime Router
- 輸入 target/horizon/current regime/performance store → eligible_models/model_weights/
  fallback_model/evidence_state。

## 7. Best Baseline fallback
- `BEST_BASELINE` 是合法候選；AI 打不贏 → `BASELINE_DOMINANT`（合法）。

## 8. Sample-size protection
- 小樣本（VOL_HIGH 4 obs）→ `REGIME_EVIDENCE_INSUFFICIENT` → 回退 global + shrinkage。

## 9. Ensemble quantile semantics
- component quantile 平均 → `ENSEMBLE_RESEARCH_QUANTILE_SUMMARY` + UNVALIDATED。
- sample-level mixture → `SAMPLE_LEVEL_MIXTURE` + validated。

## 10. Forecast Synthesis
- 分開保留 direct/joint/scenario/ensemble/baseline/edge/regime/event，不混成 final_price。

## 11. Historical Edge integration
- Edge 只作 evidence（`MODEL_BULLISH + EDGE_UNPROVEN`），不修改 forecast。

## 12. Backtest comparison
- `same_exam_comparison`（Best Single / Best Baseline / Equal Weight / Dynamic Ensemble /
  Regime Router）same target/horizon/origins/cutoff；`assert_same_exam` 驗證同長度。

## 13. Tests
`tests/test_phase2g.py`（21 項）：leakage × 3 / contract / var baseline / scenario × 2 /
direct-joint separation / weight deterministic / best-baseline eligible / baseline-dominant /
regime sample fallback / runtime failure skip / quantile semantics × 2 / research-center
reproducible / edge-not-modify / research states × 2 / joint registration / same-exam。

## 14. Blockers
- 無 blocking。
- **誠實揭露**：本 phase 建立「預測層」合約與 deterministic 引擎，**未宣稱 Dynamic Ensemble
  提高預測能力**（需 same-exam OOS evidence 支持，尚未進行 forward paper 累積）。

## 驗證
- `pytest tests/test_phase2g.py -q` → 21 passed
- `pytest tests/ -q` → 279 passed
- `build_id` 維持 `bbf3cb2f9a80d20e`
