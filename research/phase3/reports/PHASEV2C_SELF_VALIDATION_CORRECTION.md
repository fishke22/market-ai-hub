# PHASE V2-C — Self-Validation / Correction Report

- **Baseline verified**: main = `a84c6d6070ccb4a4b85ba0aa58e9eedf83947900` (clean tree),
  build_id `53d5b83595d8a639`.
- **Correction build_id (new)**: `ba17bafd107ae186` (labels.py + daily_adapter.py changed).
- **Tests (post-correction)**: `1067 passed, 20 deselected, 144 warnings`.

## A. Previous report claims audited

### CLAIM 1 — UNKNOWN roll blocks futures
- **actual evidence**: `labels.py` roll check (unconditional on H) returns `BLOCKED_ROLL_PROVENANCE`
  for `ROLL_BOUNDARY`/`UNKNOWN` on futures.
- **verdict**: **TRUE** (code correct).
- **fix**: none.

### CLAIM 2 — Osaka single-session Touch/Break runnable
- **actual evidence**: H=1 + `roll_status=UNKNOWN` → `series_block=BLOCKED_ROLL_PROVENANCE`,
  touch/break value `None` (verified by direct runtime reproduction).
- **verdict**: **FALSE** (report error). The engine blocks UNKNOWN roll regardless of H; the prior
  report table ("single session Touch/Break only; multi-session blocked") was wrong.
- **fix**: report corrected; adapter readiness now `touch/break/acceptance_ready=False` for OSE.

### CLAIM 3 — OSE horizon calendar truthful
- **actual evidence**: `labels.py` does **not** call any calendar/XTSK fallback. BUT when
  `expected_sessions is None` it derived sessions from bars and allowed negative `OBSERVED_FALSE`
  without calendar provenance.
- **verdict**: **PARTIAL** (defect in maturity/calendar provenance).
- **fix**: negative labels now require `expected_sessions`; absent calendar provenance →
  `BLOCKED_CALENDAR_PROVENANCE` (result carries `calendar_provenance`).

### CLAIM 4 — local_field_readiness overrides coarse registry
- **actual evidence**: `daily_adapter.local_field_readiness()` is separate from
  `asof.supports_capability()`; V2-C engine never calls `supports_capability` for field readiness.
- **verdict**: **TRUE**.
- **fix**: added adversarial regression tests (^N225 close-only, TAIWAN_INDEX none).

### CLAIM 5 — NOT_CHECKED target runnable claims
- **actual evidence**: prior report mixed `NOT_CHECKED` with "runnable" verdicts.
- **verdict**: **FALSE** (report wording error).
- **fix**: see §E below — unverified items marked `NOT_CHECKED_THIS_RUN`.

## B. Roll audit

```
OSE parquet roll fields:     none (columns: trading_date,open,high,low,close,volume,count)
adapter roll status:         UNKNOWN
H=1 Touch result:            BLOCKED_ROLL_PROVENANCE (value None)
H=1 Break result:            BLOCKED_ROLL_PROVENANCE (value None)
H>1 result:                  BLOCKED_ROLL_PROVENANCE (value None)
authoritative roll mapping:  none found
final semantics:             UNKNOWN roll fail closed, independent of H
```

## C. Calendar audit

```
OSE_DERIVATIVES horizon resolver:  none (labels.py has no calendar resolver)
actual calendar/source:            caller must inject expected_sessions
XTKS fallback used:                NO (labels.py does not import gap_session/calendar)
holiday-trading correctness proven: NO
fail-closed status:                BLOCKED_CALENDAR_PROVENANCE when expected_sessions absent
final semantics:                   negative labels require explicit calendar provenance
```

## D. Actual local dataset verification

### OSAKA_MICRO
```
checked:                read-only (parquet loaded, 960 rows)
rows:                   960
range:                  2023-07-24 → 2026-09-01
fields:                 trading_date,open,high,low,close,volume,count
roll provenance:        UNKNOWN (no contract id / roll mapping)
calendar provenance:    UNKNOWN (no OSE derivatives resolver)
session provenance:     UNKNOWN (no session open/close timestamps)
Touch actual-readiness: NOT_READY (blocked)
Break actual-readiness: NOT_READY (blocked)
Acceptance actual-readiness: NOT_READY (blocked)
blockers:               BLOCKED_ROLL_PROVENANCE + BLOCKED_CALENDAR_PROVENANCE + BLOCKED_TEMPORAL_SESSION_BOUNDARY
```

### TAIWAN_STOCK / TWSE
```
checked:                NOT_CHECKED_THIS_RUN (historical handoff: cache json has Opening/Highest/Lowest/ClosingPrice)
files/rows inspected:   NOT_CHECKED_THIS_RUN
symbols checked:        NOT_CHECKED_THIS_RUN
fields:                 (historical) OpeningPrice/HighestPrice/LowestPrice/ClosingPrice
Touch field-readiness:  FIELD_READINESS_VERIFIED (schema-level), ADAPTER_RUNTIME_NOT_INTEGRATED
Break field-readiness:  same
Acceptance field-readiness: same
runtime adapter verified: NO (no TWSE cache loader in V2-C adapter)
limitations:            not actually read this run
```

### ^N225
```
checked:                NOT_CHECKED_THIS_RUN (historical handoff: feature store close-only)
rows:                   NOT_CHECKED_THIS_RUN
fields:                 (historical) close only
Touch:                  NOT_READY (no open/high/low) — local_field_readiness returns open=False
Break field-readiness:  field-capable in principle (close sufficient)
Acceptance field-readiness: field-capable in principle (close sufficient)
coarse registry conflict: YES (supports_capability("^N225","DAILY") may return True; V2-C does not rely on it)
actual local readiness result: Touch unavailable; Break/Acceptance close-capable only
```

### TAIWAN_INDEX
```
checked:                read-only (no managed local OHLC dataset found)
managed local dataset found: NO
paths/query checked:    data/normalized, data/feature_store, data/cache (no TAIEX OHLC)
final readiness:        NOT_AVAILABLE_LOCAL_DATASET
```

## E. Code/doc changes

- MOD `src/market_ai_hub/research/v2/labels.py` — calendar-provenance gate for negative labels
  (`BLOCKED_CALENDAR_PROVENANCE` when `expected_sessions` absent); added `calendar_provenance`
  field to result; removed dead `is_touch` branch.
- MOD `src/market_ai_hub/research/v2/daily_adapter.py` — truthful OSE readiness (touch/break/
  acceptance `NOT_READY`), three blockers recorded (roll + calendar + session).
- MOD `docs/architecture/v2-daily-label-contract.md` — calendar-provenance requirement + roll
  fails closed regardless of H.
- MOD `tests/test_v2c_daily_labels.py` — 5 negative tests now pass explicit `expected_sessions`;
  +7 adversarial tests (roll H=1, calendar provenance, local readiness).
- MOD `tests/test_challengers_2d1.py`, `test_research.py`, `test_tournament.py` — build_id snapshot
  (legitimate source change).

## F. Adversarial contract tests

| test | contract | result |
|---|---|---|
| test_osaka_unknown_roll_blocks_single_session_touch | UNKNOWN roll fail closed (H=1) | PASS |
| test_osaka_unknown_roll_blocks_single_session_break | UNKNOWN roll fail closed (H=1) | PASS |
| test_negative_label_not_false_when_calendar_provenance_unknown | negative requires calendar provenance | PASS |
| test_positive_label_ok_without_calendar_provenance | positive established from observed data | PASS |
| test_n225_close_only_blocks_touch_even_if_coarse_registry_says_daily_ohlcv | local readiness > coarse registry | PASS |
| test_taiwan_index_without_local_dataset_not_touch_ready | no managed OHLC → not ready | PASS |
| test_legacy_input_not_promoted_to_asof_verified | legacy not auto-upgraded | PASS |

## G. Regression

- `pytest tests/test_v2c_daily_labels.py -q -p no:cacheprovider` → exit 0, 56 passed, 0 failed.
- `pytest tests/test_v2a_asof.py tests/test_v2b_gap_session.py tests/test_v2c_daily_labels.py -q -p no:cacheprovider` → exit 0, 106 passed.
- `pytest tests/test_phase3a*.py -q -p no:cacheprovider` → exit 0, 121 passed.
- `pytest tests/ -q -p no:cacheprovider` → exit 0, **1067 passed, 20 deselected, 144 warnings**.

## H. Warnings

- V2-C-origin warnings: none (`-W error::DeprecationWarning` / `FutureWarning` / `UserWarning` on
  the V2-C test file → clean).
- pre-existing/third-party warnings: 144 (from prior phases, unrelated to V2-C).
- new correctness warnings: none.

## I. Research / safety status

```
model training: NO
distribution fitting: NO
calibration fitting: NO
public probability: NO
trade signal: NO
broker/order: NO
new scheduler: NO
MCP integration added: NO
V2-D started: NO
3B.1 started: NO
Phase2 frozen conclusions changed: NO
```

## J. Corrected interpretation

```
V2-C engine contract status:      PASS (touch/break/acceptance + roll + calendar + identity + maturity correct)
OSAKA_MICRO local dataset readiness: BLOCKED (roll + calendar + session provenance absent)
TAIWAN_STOCK local dataset readiness: NOT_CHECKED_THIS_RUN (schema-level OHLC ready; no runtime adapter)
^N225 local dataset readiness:       NOT_CHECKED_THIS_RUN (close-only → Touch not ready; Break/Acceptance close-capable in principle)
TAIWAN_INDEX local dataset readiness: NOT_AVAILABLE_LOCAL_DATASET
```

ENGINE CONTRACT PASS ≠ ALL TARGET DATASET READY.

## K. Gate

**PHASEV2C_DAILY_MULTI_TARGET_LABEL_PASS** (engine contract correct after calendar-provenance fix;
per-dataset readiness documented separately as BLOCKED / NOT_CHECKED / NOT_AVAILABLE).

STOPPED AFTER V2-C SELF-VALIDATION/CORRECTION. V2-D NOT STARTED.
