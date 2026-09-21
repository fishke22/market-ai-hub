# PHASE 3A.2.2 — Distribution Evidence Closure Report

- **Schema version**: `3A.2.2` (`PRICE_PROBABILITY_MAP_VERSION`)
- **Baseline main**: `8dc0c47f3b15c25b9573e005d67559b236632e27`
- **Runtime build_id (new)**: `de60666063633e64` (was `46538342bd31e6bb`)
- **Tests**: `940 passed, 20 deselected` (was `914`; +26 new 3A.2.2 adversarial). Note: the 3 build_id snapshot tests are counted in the 940; the interim 937 was the run before those snapshots were bumped.
- **Focused Phase 3A~3A.2.1**: 74 passed; **3A.2.2** file: 26 passed
- **Central artifact**: `src/market_ai_hub/research/price_probability_map.py`

## 1. Did `DistributionRecord` scope previously participate in PUBLIC eligibility?

**YES — it did not.** The 3A.2.1 gate chain validated the `ProbabilityValue` and the
`ProbabilityProvenance`, but never the `DistributionRecord`'s own `target_family` / `instrument` /
`horizon`. The distribution was only consulted for `method` and capability/path metadata.

## 2. Could a TAIWAN map + OSAKA distribution produce a public touch probability?

**YES before the fix.** Reproduced: map `TAIWAN_STOCK/3706.TW/1d`, provenance
`TAIWAN_STOCK/3706.TW/1d`, distribution `OSAKA_MICRO/JNU/5d` with `PATH_SAMPLES` +
`OSE_DERIVATIVES` + `day+night`, all other gates valid → `touch_probability = 0.61`.
After the fix → no public probability; status `NOT_AVAILABLE_SCOPE_MISMATCH`, reasons
`DISTRIBUTION_TARGET_SCOPE_MISMATCH`, `DISTRIBUTION_INSTRUMENT_SCOPE_MISMATCH`,
`DISTRIBUTION_HORIZON_SCOPE_MISMATCH`.

## 3. Could a zero-sample distribution still publish because the PV self-declared sufficient?

**YES before the fix.** Reproduced: distribution `EMPIRICAL/TERMINAL_SAMPLES` with
`sample_count=0, effective=0, min=0, NOT_EVALUATED`, PV `100/100/min50 SUFFICIENT` →
`terminal_probability = 0.61`. After the fix → no public probability, status
`NOT_AVAILABLE_INSUFFICIENT_SAMPLE`, reasons `DISTRIBUTION_INSUFFICIENT_SAMPLE`,
`PROBABILITY_SAMPLE_EXCEEDS_SOURCE`.

## 4. How are MAP / PROVENANCE / DISTRIBUTION now bound?

Three-way canonical scope contract via `validate_distribution_scope()`: the map's
`target_family` / `instrument` / `horizon` must equal both the provenance's and the
distribution record's, using the same `normalize_family` / `normalize_instrument` /
`normalize_horizon`. Additionally `distribution.target_family/instrument/horizon` must equal the
provenance's (§16), and the distribution scope must be non-empty for any non-`NONE`/`QUANTILES_ONLY`
capability (`MISSING_DISTRIBUTION_SCOPE`).

## 5. What is the sampling-distribution numeric gate?

`distribution_sample_ok()` applies to `TERMINAL_SAMPLES` and `PATH_SAMPLES`:
`sample_sufficiency_status == SUFFICIENT` AND `minimum_required_sample > 0` AND
`sample_count >= minimum` AND `effective_sample_count >= minimum`. Failure →
`DISTRIBUTION_INSUFFICIENT_SAMPLE`. Analytic/model capabilities
(`TERMINAL_DISTRIBUTION` / `PATH_DISTRIBUTION`) are exempt (§7) — their calibration evidence still
must be real. On top of that, `probability_sample_within_source()` enforces
`pv.sample_count <= distribution.sample_count` (terminal) or `<= path_count` (path), else
`PROBABILITY_SAMPLE_EXCEEDS_SOURCE`.

## 6. May `TAIWAN_STOCK` use `OSE_DERIVATIVES` path semantics?

**NO.** The central validator maps `(TAIWAN_STOCK, DIRECT) → (XTAI, day)`; `OSE_DERIVATIVES` or
`day+night` yields `MARKET_CALENDAR_MISMATCH` / `SESSION_SEMANTICS_MISMATCH`.

## 7. May Direct Osaka Micro use `XTKS` as its direct path calendar?

**NO.** `(OSAKA_MICRO, DIRECT) → (OSE_DERIVATIVES, day+night)`. `XTKS` →
`MARKET_CALENDAR_MISMATCH`.

## 8. May `^N225` proxy use `XTKS`?

**YES — but it must be `PROXY_MODEL_REFERENCE`.** `(OSAKA_MICRO, PROXY) → (XTKS, day)`, and
`forecast_scope` must be `PROXY_MODEL_REFERENCE`; a `DIRECT_INSTRUMENT` scope on a proxy yields
`FORECAST_SCOPE_MISMATCH`.

## 9. Do PANEL/GLOBAL calibration scope failures still show only `UNCALIBRATED`?

**NO.** Typed reasons are produced by `calibration_scope_eligibility()`:
`CALIBRATION_SCOPE_EVIDENCE_MISSING`, `CALIBRATION_UNIVERSE_MISMATCH`,
`CALIBRATION_GLOBAL_SCOPE_MISMATCH`. `public_view()` also exposes
`calibration_scope_reason_codes` at the map level. `SINGLE_INSTRUMENT` still requires the
provenance scope match (family/instrument/horizon) from the existing layer.

## 10. Are all current PUBLIC probabilities still unavailable?

**YES.** No runtime code path emits a public probability; every probability type on every target
remains `NOT_AVAILABLE`. No percentage appeared as a result of this contract change.

## Extended eligibility checks (§22)

`ProbabilityEligibilityResult.checks` now contains: `capability`, `value`, `probability_sample`,
`distribution_sample`, `provenance`, `provenance_scope`, `distribution_scope`,
`distribution_identity`, `market_semantics`, `calibration`, `calibration_scope`, `path`.

## Preserved invariants (§33)

scope normalization; numeric PV sample gate; derived public status; evaluation enum consistency;
method↔capability consistency; `FULL_DISTRIBUTION` terminal-only; path metadata hard gate;
map+zone calibration; invalid `p` fail closed; `state_is_trade_instruction=false`;
`actionability_status=NOT_VALIDATED`; Taiwan evidence ≠ Osaka evidence. Research truth unchanged;
no fitting/training/strategy/execution.

## Verification commands

```
python -m pytest tests/test_phase3a22.py -q                                    # 26 passed
python -m pytest tests/test_phase3a.py tests/test_phase3a1.py tests/test_phase3a2.py tests/test_phase3a21.py -q  # 74 passed
python -m pytest tests/ -q                                                     # 940 passed, 20 deselected
```

## Manual UAT

Agent does not self-declare UAT. Manual Cherry UAT remains **RETEST_REQUIRED**.
