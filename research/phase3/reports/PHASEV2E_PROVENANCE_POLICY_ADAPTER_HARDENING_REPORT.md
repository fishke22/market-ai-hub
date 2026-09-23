# PHASE V2-E — Provenance / Policy / Adapter Hardening — CORRECTION REPORT

- **Baseline**: main = `c8dca2578755c6eea10e04beb761bf03cb768776`, build_id `fe9b5bf1cfe2f020`.
- **Schema**: `2E.1 → 2E.2` (real contract hardening).
- **Final build_id**: `585433f80d943804`.
- **Final tests**: `1252 passed, 20 deselected, 144 warnings`.

## A. Baseline
```
starting HEAD: c8dca2578755c6eea10e04beb761bf03cb768776
origin/main: same
starting build_id: fe9b5bf1cfe2f020
ending build_id: 585433f80d943804
working tree: clean → clean
Python: 3.12.13
```

## B. Confirmed defects BEFORE fix (reproduced)
```
A roll NOT_APPLICABLE / "BANANA" → EVALUATED (fail-open)
B policy mutation (atr_period=99, thresholds .1/.2, PROVEN/OPTIMIZED) → accepted as 2E.1
C cutoff > origin → EVALUATED (context contract not run)
D legacy context + verified scalars → derived_asof=ASOF_VERIFIED (升格)
E series_semantics "BANANA" → EVALUATED
F empty component source identity + valid 2nd family → WARNING_ESTABLISHED
G Osaka extension + Taiwan context/components → WARNING_ESTABLISHED (cross-target)
H/L adapter retarget (Osaka assessment + Taiwan context) → Taiwan StateEvidence
I exhaustion backdate (07:00 warning → caller 01:00) → accepted
J exhaustion ASOF only components → ASOF_VERIFIED
K no-components vs UNKNOWN-component → same assessment_id
M same component_id in 2 families → 2-family WARNING
N unverified extension source u1 vs u2 → same id / lineage lost
```

## C. Corrected 2E.2 contract
```
policy freeze: canonical policy fields frozen (reject mutation)
scalar identity: full target identity bound to context; cross-target blocks
ATR provenance: atr_period=14 + canonical method required
series/roll: canonical enums; mixed series blocks; futures require NONE
context validation: V2-D contract run (cutoff<=origin etc.)
ASOF: least-verified(context + all scalars / extension + components)
component contract: source identity mandatory; present must be bool; id collision blocks
extension/exhaustion binding: identity + time-stream must match
warning time: derived from required evidence (no caller backdating)
adapter rule: no retarget; timestamps from assessment
lineage: role-preserved on all paths (EVALUATED/UNVERIFIED/CONFLICT/BLOCKED)
semantic IDs: include evidence lineage; order-independent
direct V2C_OUTCOME source: blocked
```

## D. Direct reproductions AFTER fix
A BLOCKED (roll enum reject / NONE-only) · B policy reject (ValueError) · C BLOCKED · D derived=LEGACY · E reject (enum) · F BLOCKED · G BLOCKED_IDENTITY_MISMATCH · H/L adapter raises · I derived warning time · J derived=LEGACY · K different ids · M BLOCKED_COMPONENT_ID_COLLISION · N lineage preserved + distinct ids.

## E. Changed files
- MOD `src/market_ai_hub/research/v2/extension_exhaustion.py` — 2E.2 hardening
- MOD `tests/test_v2e_extension_exhaustion.py` — 64 tests (+18 adversarial)
- MOD `docs/architecture/v2-extension-exhaustion-contract.md`
- MOD `docs/development/project-status.md`
- MOD `tests/test_challengers_2d1.py` / `test_research.py` / `test_tournament.py` (build_id)
- ADD `research/phase3/reports/PHASEV2E_PROVENANCE_POLICY_ADAPTER_HARDENING_REPORT.md`

## F. New adversarial tests (invariants)
roll enum reject / NOT_APPLICABLE block / NONE required · policy reject (atr period/thresholds/PROVEN/OPTIMIZED/family-count) · cross-target scalar block · series enum reject / mixed block · ATR period/method · cutoff>origin block · context-ASOF not promoted · component source type / bool / id-collision / double-family · cross-target extension/adapter · warning time derived / no-backdate · lineage (extension role / unverified / exhaustion union / conflict) · direct V2C block · semantic-id lineage / order.

## G. Synthetic behavior preserved
NORMAL +0.5 · EXTENDED +1.5 · EXTREME +2.5 · WARNING (EXTREME + 2 families, Direction/CHASE unchanged).

## H. Dataset readiness (unchanged)
OSAKA_MICRO NOT_READY · TAIWAN_STOCK FIELD_READY_ONLY · ^N225 ATR NOT_READY · TAIWAN_INDEX NOT_AVAILABLE.

## I. Regression
```
test_v2e: 64 passed (exit 0) · v2a+b+c+d+e: 291 passed · phase3a*: 121 passed · full: 1252 passed, 20 deselected, 144 warnings (exit 0) · V2-E -W error: 64 passed
```

## J. Integration
actual market V2-E NOT_AVAILABLE · V2-D generated evidence validate_state_evidence=[] (synthetic) · MCP NOT_INTEGRATED · V2-F/G/H/I NOT_STARTED.

## K. Safety
model training NO · threshold optimization NO · distribution/calibration fitting NO · public probability NO · trade signal NO · broker/order NO · scheduler NO · persistent DB NO · Phase2 freeze changed NO.

## L. Gate
**PHASEV2E_EXTENSION_EXHAUSTION_PASS** (engine contract hardened; actual target data readiness unchanged).

STOPPED AFTER V2-E PROVENANCE/POLICY/ADAPTER HARDENING. V2-F NOT STARTED.
