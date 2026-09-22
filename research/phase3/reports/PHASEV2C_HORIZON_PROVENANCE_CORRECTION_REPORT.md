# PHASE V2-C — Horizon & Provenance Hardening Correction Report

- **Baseline**: main = `21a69a719e4680eba01de97a7b34306d66eb8048`, build_id `b4f001dc4725f3b2`.
- **Schema**: `2C.1 → 2C.2` (real contract change: horizon scoping, positive calendar gate,
  previous-close provenance, barrier provenance, ASOF/lineage summaries).
- **Final build_id**: `d8584c5c14eabb78`.
- **Final tests**: `1096 passed, 20 deselected, 144 warnings`.

## A. Baseline
```
starting HEAD: 21a69a719e4680eba01de97a7b34306d66eb8048
ending HEAD: (see git)
branch: main → feat branch
working tree before: clean
working tree after: clean
starting build_id: b4f001dc4725f3b2
ending build_id: d8584c5c14eabb78
Python: 3.12.13
```

## B. Four confirmed defect reproductions BEFORE fix (actual old output)
```
A horizon overflow:      H=1, D1 no event, D2 touch → Touch=True first_session=2026-09-22 (WRONG)
B missing previous-close: previous_close=None, bar entirely above UP barrier → Touch=False/OBSERVED_FALSE (WRONG)
C missing barrier avail: barrier_available_at=None → Break=False/OBSERVED_FALSE (WRONG, should block)
D ASOF mismatch:         request=ASOF_VERIFIED + legacy outcome → result.asof_status=ASOF_VERIFIED (WRONG)
```

## C. Root causes
- A: `build_daily_barrier_labels` did not scope `outcome_bars` to the first H sessions; `_eval_*`
  ran over all outcome bars and `expected_sessions` was not a hard evaluation window.
- B: `_eval_touch` used `request.previous_close` as a naked float; when None it could not detect
  gap-cross and `_finalize` fell through to `OBSERVED_FALSE`.
- C: barrier check treated `barrier_available_at is None` as absent-from-check (only checked
  `is not None and > cutoff`), so missing availability did not block.
- D: `res.asof_status` was set directly to `request.asof_status` (a caller-declared string).

## D. Corrected 2C contract
```
schema: 2C.2
session-window semantics: expected_sessions = eligible-elapsed trusted sessions; window = [:H]
H scoping: window_sessions = expected_sessions[:H]; out-of-window bars ignored (recorded, no effect)
positive calendar rule: trusted session-window provenance REQUIRED (BLOCKED_CALENDAR_PROVENANCE otherwise)
negative maturity rule: mature = (>=H elapsed) and (no missing in-window session)
previous-close provenance: value + available_at<=cutoff + trusted provenance; else BLOCKED_PREWINDOW_REFERENCE_PROVENANCE
barrier provenance: barrier_available_at mandatory; None/after-cutoff → BLOCKED_BARRIER_PROVENANCE
ASOF provenance: conservative summary; ASOF_VERIFIED only if forecast+outcome both verified
snapshot lineage: forecast/barrier/outcome role-specific lists + derived union
roll summary: derived from in-window bars; UNKNOWN/ROLL_BOUNDARY futures → BLOCKED_ROLL_PROVENANCE
series semantics: mixed in-window → BLOCKED_SERIES_SEMANTICS_MISMATCH
```

## E. Tests added/changed
```
test_h1_second_session_touch_does_not_count — horizon hard boundary
test_h1_second_session_break_does_not_count — horizon hard boundary
test_h1_second_session_acceptance_does_not_count — horizon hard boundary
test_out_of_window_roll_unknown_does_not_block — out-of-window isolation
test_out_of_window_invalid_ohlc_does_not_block — out-of-window isolation
test_out_of_window_identity_mismatch_does_not_block — out-of-window isolation
test_positive_label_blocks_without_trusted_session_window — positive calendar gate (renamed from test_positive_label_ok_without_calendar_provenance)
test_positive_label_succeeds_with_trusted_session_window — positive trusted succeeds
test_positive_acceptance_blocks_without_trusted_session_window — positive calendar gate
test_trusted_empty_elapsed_session_list_is_unmatured — empty elapsed → UNMATURED
test_partial_horizon_touch_true_early / test_partial_horizon_no_touch_not_false — partial horizon
test_touch_negative_requires_trusted_previous_close / test_gap_cross_with_missing_previous_close_not_false / test_touch_true_does_not_require_previous_close / test_break_independent_of_previous_close — prev-close provenance
test_missing_barrier_available_at_blocks_labels — barrier provenance
test_verified_request_plus_legacy_outcome_not_asof_verified / test_legacy_outcome_cannot_be_promoted_by_request_string — ASOF
test_result_preserves_forecast_barrier_outcome_snapshot_lineage — snapshot lineage
test_mixed_in_window_series_semantics_blocks — series semantics
```

## F. Direct reproductions AFTER fix (actual new output)
```
A: touch=None (D2 ignored)  ignored_out_of_window_sessions=['2026-09-22']  observed=['2026-09-21']
B: touch=None/BLOCKED_PREWINDOW_REFERENCE_PROVENANCE  break=True (independent)
C: break=None/BLOCKED_BARRIER_PROVENANCE  series_block=BLOCKED_BARRIER_PROVENANCE
D: forecast_asof=ASOF_VERIFIED  outcome_asof=LEGACY_TEMPORAL_UNVERIFIED  asof=LEGACY_TEMPORAL_UNVERIFIED
```

## G. Dataset readiness (unchanged — engine pass ≠ data ready)
```
OSAKA_MICRO:  BLOCKED (roll + calendar + session-boundary provenance absent)
TAIWAN_STOCK: FIELD_READY_ONLY (OHLC; temporal/session/runtime adapter incomplete)
^N225:        close-only (Touch NOT_READY; Break/Acceptance close-capable in principle)
TAIWAN_INDEX: NOT_AVAILABLE_LOCAL_DATASET
```

## H. Regression
```
test_v2c_daily_labels.py: 85 passed, exit 0
v2a+v2b+v2c:              135 passed, exit 0
phase3a*:                 121 passed, exit 0
full suite:               1096 passed, 20 deselected, 144 warnings, exit 0
V2-C -W error:            85 passed (no V2-C-origin warnings)
```

## I. Changed files
- MOD `src/market_ai_hub/research/v2/labels.py` — 2C.2 hardening (H scoping, provenance gates, lineage/asof summaries)
- MOD `tests/test_v2c_daily_labels.py` — helpers + 19 new/updated adversarial tests
- MOD `docs/architecture/v2-daily-label-contract.md` — 2C.2 semantics
- MOD `tests/test_challengers_2d1.py` / `test_research.py` / `test_tournament.py` — build_id snapshot
- ADD `research/phase3/reports/PHASEV2C_HORIZON_PROVENANCE_CORRECTION_REPORT.md`

## J. Safety
```
training: NO  distribution fitting: NO  calibration fitting: NO  public probability: NO
trade signal: NO  broker/order: NO  scheduler: NO  MCP integration: NO
V2-D started: NO  3B.1 started: NO  Phase2 freeze changed: NO
```

## K. Gate
**PHASEV2C_DAILY_MULTI_TARGET_LABEL_PASS** (engine contract; per-dataset readiness separately
BLOCKED / FIELD_READY_ONLY / NOT_AVAILABLE).

STOPPED AFTER V2-C HORIZON/PROVENANCE HARDENING. V2-D NOT STARTED.
