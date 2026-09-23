# PHASE V2-D.4 — Artifact Identity / Transition Isolation Closure — REPORT

This closure is a V2-G prerequisite audit hardening. No V2-G implementation performed.

- **Schema**: `V2_STATE_MACHINE_SCHEMA_VERSION = "2D.4"` (`src/market_ai_hub/research/v2/state_machine.py`)
- **Baseline**: main = `771087bf3c2eb28d2584d08096b542f521418ae6`, build_id `d12c7a47e221c179`.
- **Final build_id**: `8cea090107bc1293`.
- **Final tests**: `1372 passed, 20 deselected, 144 warnings`.

## A. Baseline
```
starting HEAD: 771087bf3c2eb28d2584d08096b542f521418ae6
ending HEAD:   (see merge commit)
origin/main:   same (at start)
working tree:  clean → clean
Python:        3.12.13
starting build_id: d12c7a47e221c179
ending build_id:   8cea090107bc1293
```

## B. Confirmed BEFORE defects
```
A successful snapshot evidence-ASOF collision:
  input  ctx asof LEGACY; e1 asof ASOF_VERIFIED vs e1 asof TEMPORAL_UNVERIFIED
  old    same snapshot_id (a6a494d56ed58cd7) but semantic_dump != (evidence_asof_by_id differs)
  cause  snapshot_identity only hashed derived_asof + layer value/status, dropped evidence_asof_by_id

B blocked snapshot context-lineage collision:
  input  ctxA source=["ctxA"] vs ctxB source=["ctxB"], same cutoff>origin invalid
  old    same snapshot_id (4c2bb668647e134f) but semantic_dump !=
  cause  blocked_snapshot_identity omitted context source lineage

C blocked snapshot context-ASOF collision:
  input  ctx asof ASOF_VERIFIED vs TEMPORAL_UNVERIFIED, same invalid cutoff/origin
  old    same snapshot_id (4c2bb668647e134f) but semantic_dump !=
  cause  blocked_snapshot_identity omitted context_asof_status

D transition alias mutation:
  input  transition(prev=BULLISH, curr=BEARISH); then curr.directional_state.value = STRONG_BEAR
  old    t.new_directional_state.value became STRONG_BEAR; semantic_dump changed; transition_id unchanged
  cause  transition() stored references to current/previous LayerState (shared mutable aliases)
```

## C. Corrected 2D.4 contract
```
snapshot identity payload: every StateSnapshot semantic field except snapshot_id + created_at
canonical serialization:  json.dumps(payload, sort_keys=True, separators=(",",":"), ensure_ascii=True)
LayerState identity:      value + status + evidence_ids + source_snapshot_ids + reason_codes (full semantics)
blocked identity:         same content-consistent snapshot_identity (context lineage + context_asof + offending fp included)
runtime metadata exclusions: snapshot_id, created_at
transition cloning:       copy.deepcopy() on every previous_*/new_* LayerState
transition identity:      sha256(prev_snapshot_id | new_snapshot_id | canonical triggers | schema)
```

## D. AFTER reproductions
```
A same evidence-asof mapping change → different snapshot_id (1e943312ce9a0823 vs 85cc7045840045af)
B blocked context lineage → different snapshot_id (b57e728262e4b474 vs 490164213e8ea9db)
C blocked context asof   → different snapshot_id (46226ac0849322d4 vs 985e6628f9278720)
D mutate current snapshot after transition → t.new_directional_state.value stays BEARISH,
  semantic_dump unchanged, transition_id unchanged
```

## E. Changed files
- MOD `src/market_ai_hub/research/v2/state_machine.py` (2D.3 → 2D.4)
- MOD `tests/test_v2d_state_machine.py` (92 → 108 tests)
- MOD `docs/architecture/v2-state-machine-contract.md`
- MOD `docs/architecture/v2-extension-exhaustion-contract.md` (2D.4 ref)
- MOD `docs/architecture/v2-catalyst-response-contract.md` (2D.4 ref)
- MOD `docs/development/project-status.md`
- MOD `tests/test_challengers_2d1.py` / `test_research.py` / `test_tournament.py` (build_id)
- ADD `research/phase3/reports/PHASEV2D_ARTIFACT_IDENTITY_TRANSITION_ISOLATION_CLOSURE_REPORT.md`

## F. New adversarial tests
snapshot identity: evidence-asof-mapping-change · context-asof-change-even-if-derived-asof-same ·
context-lineage-change · blocked-context-lineage-change · blocked-context-asof-change ·
same-semantic-deterministic · source-order-stable · created-at-excluded.
layer semantics: evidence-attribution · reason-codes · source-lineage participate in identity.
transition isolation: deep-copy-current · deep-copy-previous · mutate-current-unchanged ·
mutate-previous-unchanged · mutate-nested-layer-lists-unchanged.

## G. Regression
```
test_v2d (focused): 108 passed, exit 0
V2-D/E/F: 276 passed, exit 0
V2-A..F: 411 passed, exit 0
Phase3A: 121 passed, exit 0
test_v2d -W error: 108 passed, exit 0
full suite: 1372 passed, 20 deselected, 144 warnings, exit 0
```

## H. Downstream compatibility
```
V2-E 2E.3: PASS (uses V2-D StateEvidence adapter; no regression)
V2-F 2F.3: PASS (full regression)
V2-G: NOT_STARTED
```

## I. Safety
```
sequential updating: NO · change-point: NO · probability velocity: NO · model training: NO
calibration: NO · trading: NO · broker/order: NO · persistent DB: NO
```

## J. Gate
**PHASEV2D_DYNAMIC_STATE_MACHINE_SCAFFOLD_PASS** + **V2G_UPSTREAM_ARTIFACT_INTEGRITY_READY**
(engine contract; actual market dataset NOT_AVAILABLE — ENGINE PASS != CAUSAL/PREDICTIVE EVIDENCE !=
MARKET DATA READINESS != TRADING EDGE).

STOPPED AFTER V2-D ARTIFACT IDENTITY/TRANSITION ISOLATION CLOSURE. V2-G NOT STARTED.
