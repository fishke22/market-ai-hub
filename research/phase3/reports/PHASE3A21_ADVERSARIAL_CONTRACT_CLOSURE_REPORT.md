# PHASE 3A.2.1 — Adversarial Probability Contract Closure Report

- **Schema version**: `3A.2.1` (`PRICE_PROBABILITY_MAP_VERSION`)
- **Baseline main**: `0f2d987ef6c4fa1cdb5b61ef83b0d3c942e9f52b`
- **Runtime build_id (new)**: `46538342bd31e6bb` (was `e8b30b454b3b574b`)
- **Tests**: `914 passed, 20 deselected` (was `891 passed`; +23 adversarial)
- **Focused Phase 3A/A.1/A.2**: 51 passed (unchanged count)
- **Central artifact**: `src/market_ai_hub/research/price_probability_map.py`

## Question 1 — Can an out-of-scope probability surface?

No. `validate_provenance_scope()` compares the probability's `ProbabilityProvenance`
(`target_family` / `instrument` / `horizon`, normalized) against the map. Any mismatch yields
`NOT_AVAILABLE_SCOPE_MISMATCH` with explicit reason codes. Verified:
`test_adversarial_scope_mismatch_blocked` (map `TAIWAN_STOCK/X/1d` vs prov `OTHER/OTHER/5d` →
no `0.61`). Normalization verified: `1D`≡`1d`, `3706`≡`3706.TW`.

## Question 2 — Can a zero-sample record labelled SUFFICIENT surface?

No. `ProbabilityValue.is_sample_sufficient()` is numeric: `minimum_required_sample > 0` AND
`sample_count >= minimum` AND `effective_sample_count >= minimum` AND status `SUFFICIENT`.
Zero-sample fake → `INSUFFICIENT_SAMPLE`. Verified: `test_adversarial_zero_sample_fake_sufficient`.

## Question 3 — Can AVAILABLE + UNCALIBRATED surface as a number?

No. Public status is **derived** from the gate chain, never echoed from the internal record.
Verified: `test_adversarial_available_but_uncalibrated` and `test_public_status_derived_not_echoed`
(internal `AVAILABLE` → public `NOT_AVAILABLE_UNCALIBRATED`).

## Question 4 — Are enums normalized or rejected?

Both, deterministically. `VALID`/`ESTABLISHED` normalize to `EVALUATED` (backward compat);
unknown values raise `ValueError`. `EvaluationEvidence.is_valid()` requires
`method_version` + `data_version` + `evaluated_at` + `source` + `sample_count`. Verified:
`test_adversarial_invalid_evaluation_enum_normalized`,
`test_adversarial_unknown_evaluation_enum_rejected`, `test_evaluation_evidence_completeness`.

## Question 5 — Is method/capability consistency enforced?

Yes. `METHOD_CAPABILITY_RULES` constrains each distribution method to a capability set;
`DistributionRecord.__post_init__` rejects violations (e.g. `QUANTILES_ONLY` claiming
`PATH_SAMPLES`). `GAUSSIAN_BASELINE_DIAGNOSTIC` is limited to `{NONE, QUANTILES_ONLY}`.
Verified: `test_adversarial_method_capability_mismatch_rejected`,
`test_gaussian_not_public_calibrated_source`.

## Question 6 — Can terminal-only capability produce touch/first_passage?

No. `TERMINAL_SAMPLES` / `TERMINAL_DISTRIBUTION` support `terminal` only. `FULL_DISTRIBUTION` is
explicitly terminal-only and never implies path (the 3A.2 matrix was wrong on this point and is
now corrected). Verified: `test_terminal_distribution_cannot_produce_touch`,
`test_full_distribution_not_path_capability`.

## Question 7 — Does touch/first_passage require path metadata?

Yes — a hard gate. A path-capable distribution without `path_count`, `steps_per_path`,
`bar_frequency`, `target_market_calendar`, `session_semantics`, `generation_method` yields
`NOT_AVAILABLE_*` with `PATH_METADATA_MISSING`. Verified:
`test_path_metadata_missing_blocks_touch`, `test_path_metadata_present_allows_touch`.

## Question 8 — Is provenance cross-checked?

Yes. `distribution_method` must match the distribution record (`DISTRIBUTION_METHOD_MISMATCH`);
calibration method/version must be present (`CALIBRATION_PROVENANCE_MISSING`). Verified:
`test_provenance_method_mismatch_blocked`, `test_calibration_provenance_missing_blocked`.

## Question 9 — Is calibration scope enforced?

Yes. `SINGLE_INSTRUMENT` / `PANEL` / `GLOBAL` each require their own scope evidence; a panel
calibration without a matching universe (or with a non-member instrument) grants nothing.
Verified: `test_panel_scope_requires_universe`, `test_panel_scope_member_mismatch_blocked`,
`test_global_scope_requires_definition`.

## Question 10 — Current probability availability

**All current probabilities remain `NOT_AVAILABLE`.** No percentage is emitted for any
probability type on any target. Verified: `test_current_all_probabilities_unavailable`.

## Preserved invariants

- Map+zone dual calibration gate; invalid `p` outside `[0,1]` fails closed; quantiles-only → no
  probability; enum input ≠ evaluated evidence; `state_is_trade_instruction=false`;
  `actionability_status=NOT_VALIDATED`; Taiwan ≠ Osaka evidence.
- Research truth unchanged (`PHASE2_RESEARCH_FREEZE.yaml`); trading = `RESEARCH_ONLY`.
- No distribution fitting, calibration fitting, training, strategy optimization, or execution.

## Verification commands

```
python -m pytest tests/test_phase3a21.py -q            # 23 passed
python -m pytest tests/test_phase3a.py tests/test_phase3a1.py tests/test_phase3a2.py -q  # 51 passed
python -m pytest tests/ -q                             # 914 passed, 20 deselected
python -c "import sys;sys.path.insert(0,'src');from market_ai_hub.services.build_info import build_fingerprint;print(build_fingerprint()['build_id'])"
```

## Manual UAT

Agent does not self-declare UAT. Manual Cherry UAT remains **RETEST_REQUIRED**.
