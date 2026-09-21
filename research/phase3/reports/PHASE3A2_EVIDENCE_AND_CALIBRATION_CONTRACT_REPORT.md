# PHASE 3A.2 — Typed Evidence Contract + Calibration Safety Closure + Distribution Schema Consistency + Evaluation Provenance

- gate：**PHASE3A2_EVIDENCE_CONTRACT_PASS**（0 Critical / 0 High）
- build_id：`e8b30b454b3b574b`
- schema version：**3A.2**
- 版本：`v2.0.0-rc1`（不 tag / release / retag）

## 10 問答（§40）

1. **原本 DISTRIBUTION_METHODS 是否漏掉合法 runtime values？** **是**。原 enum 只有 `EMPIRICAL`/`MODEL_DISTRIBUTION`/`GAUSSIAN_BASELINE_DIAGNOSTIC`，但 runtime 已用 `NOT_ESTABLISHED`/`QUANTILES_ONLY`。已補齊 canonical enum。
2. **是否存在 map calibrated 但 zone uncalibrated 仍公開 probability 的可能？** 原有可能（public_view 只看 map）。已修：**map 與 zone 都需 CALIBRATED**。
3. **terminal/touch/first-passage 是否獨立校準？** 是（`ProbabilityValue` 各自 `calibration_status`）。
4. **AVAILABLE 要滿足哪些 machine gates？** capability 支持 + status=AVAILABLE + value valid(0..1 finite) + map CALIBRATED + zone CALIBRATED + sample SUFFICIENT + provenance complete。
5. **EVALUATED 是否需要 evidence object？** 是（`EvaluationEvidence.is_valid()`）。
6. **只有 enum 字串是否還能標 EVALUATED？** **NO**（→ `UNVERIFIED`）。
7. **QUANTILES_ONLY 能否產生 zone probability？** **NO**（capability matrix: terminal/touch/first_passage 全 false）。
8. **目前有任何公開 probability 嗎？** **NO**（`NOT_AVAILABLE_INSUFFICIENT_DISTRIBUTION` / reason `QUANTILES_ONLY`）。
9. **是否開始 calibration fitting？** **NO**（`calibration_metrics_contract()` = `INTERFACE_ONLY_NOT_FITTED`）。
10. **是否開始 strategy optimization？** **NO**。

## 交付

- `price_probability_map.py` 升 3A.2：
  - canonical `DISTRIBUTION_METHODS`（含 NOT_ESTABLISHED/QUANTILES_ONLY）+ `DISTRIBUTION_CAPABILITIES` + `CAPABILITY_MATRIX`。
  - `ProbabilityValue`（typed：value/status/calibration/sample/reason_codes + `is_public_available` fail-closed）。
  - `ZoneProbability.terminal/touch/first_passage`（typed）+ compat alias properties。
  - `DistributionRecord`（method/capability/is_full_distribution/sample/path/session semantics）。
  - `ProbabilityProvenance`（13 required fields + `is_complete()`）。
  - `EvaluationEvidence`（status/method/method_version/data_version/sample_count/…）。
  - `ProbabilityMap.public_view()` fail-closed（map+zone calibration + capability + sample + provenance）。
  - `six_state_research_view`：enum 無 evidence → `UNVERIFIED`；有 valid evidence → `EVALUATED`。
  - `strategy_candidate_for`：需 regime EVALUATED + valid evidence。
  - `probability_from_quantiles_only` → 全 NOT_AVAILABLE + reason QUANTILES_ONLY。
  - `calibration_metrics_contract()`（interface only）。
- `tests/test_phase3a2.py`（20 tests）+ 更新 3A/3A.1 tests。

## Gate 對照（§41）

schema/runtime enum consistent ✓；typed probability status ✓；type-specific calibration ✓；map+zone calibration checked ✓；probability range validated ✓；sample sufficiency enforced ✓；provenance enforced ✓；target/horizon scope enforced ✓；EVALUATED requires evidence ✓；quantile != probability preserved ✓；terminal data cannot produce touch ✓；path capability required for first passage ✓；current public probability honest ✓；full pytest PASS ✓；0 Critical / 0 High ✓。

## Validation

- **full default pytest：891 passed, 20 deselected**（870 + 21 new）。
- runtime data zero pollution；working tree clean after tests。

## 禁區未動

不 probability estimation / calibration fitting / new model training / strategy optimization / hyperparameter search / live trading / broker execution。
