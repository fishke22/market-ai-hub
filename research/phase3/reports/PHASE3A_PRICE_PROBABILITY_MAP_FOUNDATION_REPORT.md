# PHASE 3A — Price Map + Probability Map Research Foundation Report

- gate：**PHASE3A_PRICE_PROBABILITY_MAP_FOUNDATION_PASS**（0 Critical / 0 High）
- build_id：`ab65970bf0f29dfe`
- 版本：`v2.0.0-rc1`（不 tag / release / retag）

## 12 問答

1. **今天官方 sample 與 runtime 是否一致？** 一致（TAIEX / 3706 / 2330 全 match TWSE official）。
2. **TAIEX 47,718.84 是否 official match？** 是。TWSE MI_INDEX（2026-09-21）= 47,718.84（+538.09）= runtime。`fresh_sample_match = PASS`。
3. **3706 official sample 與 runtime 是否一致？** 是。TWSE STOCK_DAY 2026-09-21 close = 79.80 = runtime 79.8（source=twse）。
4. **OSE 9/21-23 Holiday Trading truth 是否一致？** 是（`config/ose_derivatives_calendar.yaml`，JPX official）；OSE derivatives OPEN，XTKS/TSE cash closed。
5. **Taiwan evidence contamination 是否完全消失？** 是。`_fill_research_truth` 改 target-scoped；golden tests 證明 TAIWAN_STOCK/TAIWAN_INDEX 不含 `VAR(1)`/`OSE`/`Micro`/`225LABO`/`NON_EXECUTABLE_FORECAST_EDGE`。
6. **目前哪些 probability 真的 AVAILABLE？** 目前**無**（`calibration_status=UNCALIBRATED`；zone `NOT_AVAILABLE_INSUFFICIENT_DISTRIBUTION`）。
7. **哪些仍 NOT_AVAILABLE？** 全部 terminal / touch / first_passage probability（distribution / calibration 未建立）。
8. **是否有任何 probability 只是從 p10/p50/p90 猜出來？** **NO**（`probability_from_quantiles_only` → 全部 `NOT_AVAILABLE_INSUFFICIENT_DISTRIBUTION`）。
9. **Terminal / Touch / First Passage 是否分開？** 是（`ZoneProbability` 三個獨立欄位）。
10. **Model Failure 如何定義？** `COVERAGE_FAILURE` / `PIT_DRIFT` / `ERROR_REGIME_SHIFT` / `PERSISTENT_DISTRIBUTION_MISS` / `MODEL_FAILURE`（versioned rule），非 price-level stop。
11. **Regime 如何影響 Market State？** regime 影響 state 解讀，但 `state_is_trade_instruction=false`；strategy switching 只給 candidate（非 instruction）。
12. **目前是否具備 validated trading edge？** **NO**（`NO_ECONOMIC_EDGE`；`actionability_status=NOT_VALIDATED`）。新架構**未**自動讓任何 gate 變 PASS。

## 交付

- `src/market_ai_hub/research/price_probability_map.py`（新，versioned）：六 state、regime、`ZoneProbability`（terminal/touch/first-passage 分開）、`ProbabilityMap`（uncalibrated → public 無 %）、`DistributionDiagnostics`、`PriceMap`、`ZonePolicy`、profiles、strategy switching、benchmark registry。
- `config/zone_policy.yaml`（versioned zone policy）。
- `docs/research/price-probability-map.md`（永久設計依據）。
- `tests/test_phase3a.py`（15 tests）。

## Gate 對照（§B34）

schemas versioned ✓；target separation preserved ✓；probability availability honest ✓；no normality assumption ✓（Gaussian 只 BASELINE_DIAGNOSTIC）；terminal/touch/first-passage separated ✓；distribution diagnostics ✓；regime layer ✓；model-failure semantics ✓；no personalized trade action ✓；strategy benchmark framework ✓；walk-forward + multiple-testing documented ✓；full regression PASS ✓；0 Critical / 0 High ✓。

## Validation

- **full default pytest：855 passed, 20 deselected**（840 + 15 new）。
- docs links OK；audit_runtime_evidence PASS；assert_uat_semantics PASS。

## 禁區未動

不 live trading / broker order / auto order / auto retrain / auto promote / 把研究模型包裝成已驗證交易策略 / force push / retag。
