# PHASE 3A.2.3 — Calibration Evidence Closure Report

- **Schema version**: `3A.2.3` (`PRICE_PROBABILITY_MAP_VERSION`)
- **Baseline main**: `4e4872088327624fccf9a31df60590fb1625726f`
- **Runtime build_id (new)**: `c7417f7c4cbfb388` (was `de60666063633e64`)
- **Tests**: `961 passed, 20 deselected` (was `940`; +21 new 3A.2.3 adversarial)
- **Focused Phase 3A~3A.2.2**: 100 passed; **3A.2.3** file: 21 passed
- **Central artifact**: `src/market_ai_hub/research/price_probability_map.py`

## 1. Did 3A.2.2 still rely mainly on string status + provenance strings for calibration?

**YES.** The `cal_ok` gate compared `map_calibration == "CALIBRATED"` and
`pv.calibration_status == "CALIBRATED"` plus a couple of provenance strings
(`calibration_method` / `calibration_version`). There was no typed object proving a fit/evaluation
actually happened.

## 2. Could the manual case emit 0.61 with no `CalibrationEvidence`?

**YES before the fix.** Reproduced: map `calibration_status=CALIBRATED`, PV
`calibration_status=CALIBRATED`, provenance `calibration_method="just-a-string"` /
`calibration_version="v1"`, all other gates valid → `terminal_probability = 0.61`.
After the fix → no public probability, reason `CALIBRATION_EVIDENCE_MISSING`.

## 3. Could PANEL emit probability while missing `target_families` / `supported_horizons`?

**YES before the fix.** The 3A.2.2 `calibration_scope_eligibility` used `if fams and …` /
`if hzs and …`, so an absent `target_families` / `supported_horizons` was silently skipped. Now they
are **mandatory** — any missing required field yields `CALIBRATION_SCOPE_EVIDENCE_MISSING`.

## 4. What authoritative evidence now derives CALIBRATED?

A typed `CalibrationEvidence` dataclass (status, domain, probability_type, method, versions,
model/distribution identity, target scope, fit/evaluation windows, partition role, numeric sample,
metrics/notes). `evaluate_probability` runs `calibration_evidence_ok()` which requires the evidence
to exist, be `CALIBRATED`, and pass all binding gates. `ProbabilityMap.calibration_status` /
`ProbabilityValue.calibration_status` are compat summaries only.

## 5. Are calibration samples fully separate from distribution/PV samples?

**YES.** Three families are distinct: distribution sample (`DistributionRecord.sample_*`),
probability/event sample (`ProbabilityValue.sample_*`), and calibration evaluation sample
(`CalibrationEvidence.sample_*`). Calibration has its own numeric gate
(`CALIBRATION_INSUFFICIENT_SAMPLE`); neither distribution nor PV samples substitute for it.

## 6. Can Terminal calibration vouch for Touch?

**NO.** `CalibrationEvidence.probability_type` must equal the type being published
(`TERMINAL`/`TOUCH`/`FIRST_PASSAGE`); mismatch → `CALIBRATION_TYPE_MISMATCH`. Verified by
`test_9_terminal_evidence_does_not_vouch_for_touch`.

## 7. May the calibration fit window illegally overlap the evaluation window?

**NO.** `fit_window_*` and `evaluation_window_*` must be disjoint; overlap →
`CALIBRATION_TEMPORAL_LEAKAGE`. Verified by `test_37_calibration_temporal_leakage_blocked`.

## 8. May FINAL_OOS fit calibration?

**NO.** `fit_partition_role ∈ {TRAIN, CALIBRATION, VALIDATION, FORWARD}`; `FINAL_OOS` →
`CALIBRATION_PARTITION_VIOLATION`. Verified by `test_19_final_oos_fit_partition_blocked`.

## 9. Is there any real runtime public probability?

**NO.** No runtime code path emits a public probability; every probability type on every target
(3706, 2330, TAIEX, Osaka) remains `NOT_AVAILABLE`.

## 10. Was any calibration fitting performed?

**NO.** This phase only built the typed contract. No distribution estimation, calibration fitting,
model training, strategy optimization, hyperparameter search, or execution.

## Additional contract points

- **Scope hardening (§3/§4/§15)**: `PANEL` requires `universe_id`, `universe_version`, `members`,
  `target_families`, `supported_horizons`, `calibration_domain`, `scope_version`. `GLOBAL` requires
  `scope_definition`, `scope_version`, `supported_target_families`, `supported_horizons`,
  `calibration_domain`. Family/horizon/instrument membership are all enforced.
- **Binding (§11/§12/§13)**: evidence ↔ distribution identity and evidence ↔ model identity; target/
  horizon exact match for `SINGLE_INSTRUMENT`.
- **Derived map summary (§24/§25)**: `derived_calibration_summary()` →
  `NONE_CALIBRATED` / `PARTIALLY_CALIBRATED` / `CALIBRATED_FOR_TERMINAL_ONLY` /
  `CALIBRATED_FOR_PATH_EVENTS`. Mixed calibration is never shown as a blanket `CALIBRATED`.
- **Extended checks (§26/§27)**: `ProbabilityEligibilityResult.checks` now includes
  `calibration_evidence`, `calibration_type`, `calibration_identity`, `calibration_sample`,
  `calibration_temporal`, `calibration_target_scope` (plus the 3A.2.2 keys).
- **Reason codes (§28)**: `CALIBRATION_EVIDENCE_MISSING`, `CALIBRATION_NOT_CALIBRATED`,
  `CALIBRATION_TYPE_MISMATCH`, `CALIBRATION_MODEL_MISMATCH`, `CALIBRATION_DISTRIBUTION_MISMATCH`,
  `CALIBRATION_TARGET_SCOPE_MISMATCH`, `CALIBRATION_HORIZON_SCOPE_MISMATCH`,
  `CALIBRATION_INSUFFICIENT_SAMPLE`, `CALIBRATION_TEMPORAL_LEAKAGE`,
  `CALIBRATION_PARTITION_VIOLATION`, `CALIBRATION_SCOPE_MISMATCH`.

## Verification commands

```
python -m pytest tests/test_phase3a23.py -q                                    # 21 passed
python -m pytest tests/test_phase3a.py tests/test_phase3a1.py tests/test_phase3a2.py tests/test_phase3a21.py tests/test_phase3a22.py -q  # 100 passed
python -m pytest tests/ -q                                                     # 961 passed, 20 deselected
```

## Manual UAT

Agent does not self-declare UAT. Manual Cherry UAT remains **RETEST_REQUIRED**.
