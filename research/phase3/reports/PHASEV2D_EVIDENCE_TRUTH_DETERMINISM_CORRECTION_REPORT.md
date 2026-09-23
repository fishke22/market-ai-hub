# PHASE V2-D — Evidence Truth & Determinism Hardening — CORRECTION REPORT

- **Baseline**: main = `5b10d9124bb88a380dbc3a9ded1c992e5f79d412`, build_id `1f120a6b22930b5a`.
- **Schema**: `2D.1 → 2D.2` (real contract change).
- **Final build_id**: `de2b0293fa4de2f5`.
- **Final tests**: `1170 passed, 20 deselected, 144 warnings`.

## A. Baseline
```
starting HEAD: 5b10d9124bb88a380dbc3a9ded1c992e5f79d412
origin/main: same
starting build_id: 1f120a6b22930b5a
ending build_id: de2b0293fa4de2f5
working tree: clean → clean
Python: 3.12.13
```

## B. Confirmed defects BEFORE fix (reproduced)
```
A missing timestamps: trusted evidence event/available=None → BULLISH/EVALUATED (WRONG)
B value=None: trusted evidence value=None → None/EVALUATED (WRONG)
C empty evidence_id: → EVALUATED, ids=[''] (WRONG)
D empty identity: context+evidence empty instrument/family/calendar → EVALUATED (WRONG)
E unknown asof: asof_status='MADE_UP' → EVALUATED / silently dropped (WRONG)
F context lineage: context ['ctx1'] + evidence ['ev1'] → result only ['ev1'] (WRONG)
G order determinism: reversed evidence order → same snapshot_id but order-sensitive evidence_ids
H +08 timestamps: stored as +08, created_at local (WRONG — should be UTC)
```

## C. Corrected contract
```
schema: 2D.2
mandatory context fields: instrument/target_family/instrument_role/calendar_id/frequency/horizon/evaluation_mode + cutoff/origin + asof
mandatory evidence fields: evidence_id/layer/value/identity/frequency/horizon/source_type/source_schema_version/source_version + event_timestamp + available_at + asof
temporal rule: event_timestamp <= available_at <= cutoff <= origin; missing timestamps → BLOCKED_TEMPORAL_EVIDENCE_PROVENANCE
ASOF rule: asof_status ∈ {ASOF_VERIFIED, TEMPORAL_UNVERIFIED, LEGACY_TEMPORAL_UNVERIFIED}; unknown → reject
source provenance rule: source_type/schema/version non-empty → else BLOCKED_SOURCE_PROVENANCE
V2-C provenance rule: full window/settled/schema provenance + ordering → else BLOCKED_FUTURE_OUTCOME_EVIDENCE
UTC rule: canonical stored timestamps tz-aware UTC
lineage rule: context + evidence + derived union; evidence_asof_by_id keyed by id
determinism rule: all set-like outputs canonical sorted; semantic_dump excludes created_at
blocked snapshot identity: deterministic non-empty sha256 id (per-layer independent LayerState)
transition validity: blocked snapshots rejected; trigger ⊆ current.evidence_ids; source union(prev,current)
```

## D. Direct reproductions AFTER fix
```
A: BLOCKED (BLOCKED_TEMPORAL_EVIDENCE_PROVENANCE)
B: REJECTED (ValueError: value must be non-null)
C: REJECTED (ValueError: evidence_id must be non-empty)
D: BLOCKED (BLOCKED_CONTEXT_CONTRACT / BLOCKED_IDENTITY_MISMATCH)
E: REJECTED (ValueError: unknown asof_status)
F: context=['ctx1'] + evidence=['ev1'], source_snapshot_ids=union
G: semantic_dump() identical regardless of order; layer evidence_ids canonical
H: stored timestamps +00:00; created_at UTC
```

## E. Changed files
- MOD `src/market_ai_hub/research/v2/state_machine.py` — 2D.2 hardening (mandatory fields, ASOF enum, V2-C full provenance, UTC normalization, deterministic ordering, blocked identity, transition hardening)
- MOD `tests/test_v2d_state_machine.py` — helper (source identity) + 29 new/updated adversarial tests
- MOD `docs/architecture/v2-state-machine-contract.md` — 2D.2 semantics
- MOD `tests/test_challengers_2d1.py` / `test_research.py` / `test_tournament.py` — build_id snapshot
- ADD `research/phase3/reports/PHASEV2D_EVIDENCE_TRUTH_DETERMINISM_CORRECTION_REPORT.md`

## F. Tests (new adversarial)
missing timestamps (×2), value=None, empty/whitespace evidence_id, empty context identity/horizon, source identity (×3), unknown asof (×2), V2-C full provenance/unknown schema/first-event-in-window, context lineage, asof-by-id, reversed-order semantic_dump, canonical layer ids, UTC normalization, created_at UTC, blocked snapshot identity, blocked-layer independence, blocked transition (×2), trigger subset, transition source union, persistence version.

## G. Regression
```
test_v2d_state_machine.py: 74 passed (exit 0)
v2a+v2b+v2c+v2d: 209 passed (exit 0)
phase3a*: 121 passed (exit 0)
full suite: 1170 passed, 20 deselected, 144 warnings (exit 0)
V2-D -W error: 74 passed (no V2-D warnings)
```

## H. Integration
```
actual market state evaluation: NOT_AVAILABLE (scaffold only)
MCP: NOT_INTEGRATED_THIS_PHASE
V2-E/F/G/H: NOT started
```

## I. Safety
```
training NO · distribution fitting NO · calibration fitting NO · public probability NO
trade signal NO · broker/order NO · scheduler NO · persistent DB NO · Phase2 freeze changed NO
```

## J. Gate
**PHASEV2D_DYNAMIC_STATE_MACHINE_SCAFFOLD_PASS** (evidence truth + determinism hardened; per-market state evaluation remains NOT_AVAILABLE).

STOPPED AFTER V2-D EVIDENCE TRUTH/DETERMINISM HARDENING. V2-E NOT STARTED.
