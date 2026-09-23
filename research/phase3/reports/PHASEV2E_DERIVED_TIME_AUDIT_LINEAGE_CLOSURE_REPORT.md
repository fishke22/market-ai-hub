# PHASE V2-E — Derived-Time / Audit-Lineage Final Closure — CORRECTION REPORT

- **Baseline**: main = `5972ddfb2803d355ccc1cda368857746e76549d2`, build_id `585433f80d943804`.
- **Schema**: `2E.2 → 2E.3` (real contract hardening).
- **Final build_id**: `a7f04f35e9a15d9c`.
- **Final tests**: `1273 passed, 20 deselected, 144 warnings`.

## A. Baseline
```
starting HEAD: 5972ddfb2803d355ccc1cda368857746e76549d2
origin/main: same
starting build_id: 585433f80d943804
ending build_id: a7f04f35e9a15d9c
working tree: clean → clean
Python: 3.12.13
```

## B. Confirmed defects BEFORE fix (reproduced)
```
A late-ATR backdating: extension evidence available_at = current 05:30 (ATR 07:30 ignored) → PIT leak
B cross-time exhaustion: extension cutoff/origin 08 + context 09 → WARNING_ESTABLISHED
C/D cross-time adapters: extension/exhaustion adapter across cutoff/origin → ALLOWED
E late 3rd family: M 06:30 / D 07:15 / O 07:50 → warning 07:50 (should be 07:15)
F same-family late duplicate: M1 06:30 / M2 07:55 / D 07:15 → warning 07:55 (should be 07:15)
G component +08 timestamps not normalized to UTC
H NORMAL exhaustion path lost lineage (source_snapshot_ids=[])
I blocked extension lost offending scalar lineage (same id for bad1 vs bad2)
J trusted-negative / conflict component IDs not preserved
```

## C. Corrected 2E.3 contract
```
derived extension event time: current_close.event_timestamp
derived extension available time: max(current/previous/ATR availability)
state-stream equality: identity + cutoff + origin must match (BLOCKED_STATE_STREAM_MISMATCH / adapter ValueError)
family establishment: earliest present=True evidence per family
required family set: earliest K distinct families (deterministic tie-break)
warning earliest time: max(extension_available_at, K-th family availability)
UTC: component timestamps canonical UTC
extension lineage: full role lineage + role ASOF on all statuses
exhaustion lineage: component ids/asof + negative + conflict + union on all statuses
negative evidence lineage: negative_component_ids preserved
semantic identity: derived time + full evidence lineage (negative/conflict included)
adapter rule: derived timestamps + same state stream only
```

## D. Direct reproductions AFTER fix
A extension_available_at=07:30 / evidence 07:30 · B/C/D BLOCKED_STATE_STREAM_MISMATCH / ValueError · E 07:15 · F 07:15 · G stored UTC +00:00 · H lineage preserved · I distinct ids + lineage retained · J negative/conflict ids preserved.

## E. Changed files
- MOD `src/market_ai_hub/research/v2/extension_exhaustion.py` — 2E.3 hardening
- MOD `tests/test_v2e_extension_exhaustion.py` — 85 tests (+21 adversarial)
- MOD `docs/architecture/v2-extension-exhaustion-contract.md`, `docs/development/project-status.md`
- MOD `tests/test_challengers_2d1.py` / `test_research.py` / `test_tournament.py` (build_id)
- ADD `research/phase3/reports/PHASEV2E_DERIVED_TIME_AUDIT_LINEAGE_CLOSURE_REPORT.md`

## F. New adversarial tests (invariants)
derived extension availability / adapter derived time / no backdate · cross-time exhaustion+adapters (×6) · late 3rd family / late same-family duplicate / required-set deterministic+order · component/warning UTC · NORMAL lineage · negative-id preserved / different-id / not-counted · conflict ids · blocked extension role lineage / distinct offending id / role ASOF.

## G. Synthetic semantics preserved
NORMAL<1 · EXTENDED[1,2) · EXTREME≥2 · WARNING (≥2 distinct families; Direction/CHASE unchanged).

## H. Dataset readiness (unchanged)
OSAKA NOT_READY · TAIWAN FIELD_READY_ONLY · ^N225 ATR NOT_READY · TAIEX NOT_AVAILABLE.

## I. Regression
```
test_v2e: 85 passed (exit 0) · v2a+b+c+d+e: 312 passed · phase3a*: 121 passed · full: 1273 passed, 20 deselected, 144 warnings (exit 0) · V2-E -W error: 85 passed
```

## J. Integration
actual market V2-E NOT_AVAILABLE · V2-D generated evidence validate=[] (synthetic) · MCP NOT_INTEGRATED · V2-F/G/H/I NOT_STARTED.

## K. Safety
model training NO · threshold optimization NO · distribution/calibration fitting NO · public probability NO · trade signal NO · broker/order NO · scheduler NO · persistent DB NO · Phase2 freeze changed NO.

## L. Gate
**PHASEV2E_EXTENSION_EXHAUSTION_PASS** (derived-time/audit-lineage closure complete; actual data readiness unchanged).

STOPPED AFTER V2-E DERIVED-TIME/AUDIT-LINEAGE CLOSURE. V2-F NOT STARTED.
