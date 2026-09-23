# PHASE V2-F.3 — Release-Time / Blocked-Path Determinism Closure — REPORT

- **Schema**: `V2_CATALYST_RESPONSE_SCHEMA_VERSION = "2F.3"` (`src/market_ai_hub/research/v2/catalyst_response.py`)
- **Baseline**: main = `f7cb78f2f6816b763c2612ec9a633ae5460aacd3`, build_id `0f3f403069b90dc1`.
- **Final build_id**: `d12c7a47e221c179`.
- **Final tests**: `1356 passed, 20 deselected, 144 warnings`.

## A. Baseline
```
starting HEAD: f7cb78f2f6816b763c2612ec9a633ae5460aacd3
ending HEAD:   (see merge commit)
origin/main:   same (at start)
working tree:  clean → clean
Python:        3.12.13
starting build_id: 0f3f403069b90dc1
ending build_id:   d12c7a47e221c179
```

## B. Confirmed defects BEFORE fix
```
A macro release before event:
  input  MACRO_RELEASE event=17/20:00 release=17/19:00 available=17/20:30
  old    DESCRIPTIVE_AVAILABLE, block_reason_codes=[]
  cause  release-time check only compared release<=available, never event<=release

B nonmacro future release:
  input  POLICY_EVENT event=17/20:00 available=17/20:30 release=19/08:00
  old    DESCRIPTIVE_AVAILABLE
  cause  non-macro release_timestamp was not validated at all

C catalyst-collision path order dependence:
  input  [A(mag +0.02, fp b939), B(mag -0.05, fp c42d)] vs reversed
  old    both BLOCKED_CATALYST_ID_COLLISION but path_id 0756e583... vs c105488a...
  cause  blocked path identity seeded from assessments[0]

D target-mismatch path order dependence:
  input  [OSAKA, TAIWAN] vs [TAIWAN, OSAKA]
  old    both BLOCKED_IDENTITY_MISMATCH but path_id 2c5be494... vs b6aef00b...
  cause  blocked path identity seeded from assessments[0]
```

## C. Corrected 2F.3 contract
```
release temporal rule: event_timestamp <= release_timestamp <= available_at <= feature_cutoff_timestamp
macro release rule:     MACRO_RELEASE requires release_timestamp != None; full ordering enforced
optional nonmacro rule: non-macro may keep release_timestamp=None; if supplied must obey event<=release<=available<=cutoff
blocked path canonical seed: canonical complete input assessment set (sorted semantic fingerprints)
blocked path identity:  hash("BLOCKED" + reason + canonical semantic keys + schema) — order independent
assessment semantic fingerprint: _assessment_semantic_fp(a) == assessment identity (excludes presentation metadata)
presentation metadata exclusions: response_label (and any notes/created_at) excluded from identity/collision
blocker precedence:      1 INELIGIBLE · 2 CATALYST_ID_COLLISION · 3 IDENTITY_MISMATCH · 4 STATE_STREAM_MISMATCH ·
                         5 RESPONSE_ANCHOR_MISMATCH · 6 RESPONSE_ID_COLLISION · 7 PATH_HORIZON_ORDER
```

## D. AFTER reproductions
```
A macro release before event  → BLOCKED, [BLOCKED_RELEASE_TIME_PROVENANCE]
B nonmacro future release     → BLOCKED, [BLOCKED_RELEASE_TIME_PROVENANCE]
C catalyst collision          → same reason, same blocked path_id (cffb68c2ac943ae6), order independent
D target mismatch             → same reason, same blocked path_id (9fa23f3ffc3d19fa), order independent
```

## E. Changed files
- MOD `src/market_ai_hub/research/v2/catalyst_response.py` (2F.2 → 2F.3)
- MOD `tests/test_v2f_catalyst_response.py` (65 → 83 tests)
- MOD `docs/architecture/v2-catalyst-response-contract.md` (2F.3)
- MOD `docs/development/project-status.md` (gate/build_id/schema)
- MOD `tests/test_challengers_2d1.py` / `test_research.py` / `test_tournament.py` (build_id)
- ADD `research/phase3/reports/PHASEV2F_RELEASE_TIME_BLOCKED_PATH_DETERMINISM_CLOSURE_REPORT.md`

## F. New adversarial tests
release ordering: macro-before-event / macro-equal-event / macro-between-event-and-available /
nonmacro-before-event / nonmacro-after-available / nonmacro-none-allowed / release-after-cutoff /
release-normalized-to-utc. blocked-path order independence: catalyst-collision / target-mismatch /
state-stream-mismatch / response-anchor-mismatch / response-id-collision / ineligible-assessment.
semantic duplicate: exact-duplicate-dedupes / label-difference-is-semantic-duplicate /
label-difference-no-path-collision / label-difference-no-valid-path-id-change.

## G. 2F.2 regression invariants (all preserved)
cross-target baseline blocked · missing baseline timestamps blocked · invalid baseline temporal order
blocked · empty baseline source blocked · PROVEN baseline rejected · unknown baseline no residual ·
future macro release blocked · missing macro release blocked · schedule-kind/observed blocked ·
malformed catalyst rejected · unknown futures series blocked · staleness in semantic identity ·
derived response id deterministic · presentation label does not change assessment id ·
blocked/unverified assessments do not enter valid path · same catalyst/target/state/anchor required ·
strict end-time ordering.

## H. Dataset readiness
```
NQ: NOT_AVAILABLE · ES: NOT_AVAILABLE · USDJPY: NOT_AVAILABLE · SOX: NOT_AVAILABLE · VIX: NOT_AVAILABLE
USTREASURY: daily cache, point_in_time_safe=false
FRED: CONFIGURED (periodic, revision risk, no vintage)
EVENT_DB: NOT_PRESENT
```

## I. Regression
```
test_v2f (focused): 83 passed, exit 0
V2-A~F: 395 passed, exit 0
Phase3A: 121 passed, exit 0
test_v2f -W error: 83 passed, exit 0
full suite: 1356 passed, 20 deselected, 144 warnings, exit 0
```

## J. Integration
```
actual market V2-F: NOT_AVAILABLE
V2-D: NO · V2-E: NO · MCP: NOT_INTEGRATED
V2-G: NOT_STARTED · V2-H: NOT_STARTED · V2-I: NOT_STARTED
```

## K. Safety
```
model training: NO · beta fitting: NO · lag optimization: NO · Granger: NO · causal inference: NO
distribution fitting: NO · calibration fitting: NO · public probability: NO · trade signal: NO
broker/order: NO · scheduler: NO · persistent DB: NO · Phase2 freeze changed: NO
```

## L. Gate
**PHASEV2F_CATALYST_RESPONSE_SCAFFOLD_PASS** (reopened for release-time/blocked-path determinism
closure; actual market dataset NOT_AVAILABLE — ENGINE PASS != CAUSAL/PREDICTIVE EVIDENCE != MARKET
DATA READINESS != TRADING EDGE).

STOPPED AFTER V2-F RELEASE-TIME/BLOCKED-PATH DETERMINISM CLOSURE. V2-G NOT STARTED.
