# PHASE V2-D — Dynamic State Machine Scaffold — REPORT

- **Schema**: `V2_STATE_MACHINE_SCHEMA_VERSION = "2D.1"` (`src/market_ai_hub/research/v2/state_machine.py`)
- **Baseline**: main = `cac311de836be2d9e95e05d826eec10f69928bdf`, build_id `d8584c5c14eabb78`.
- **Final build_id**: `1f120a6b22930b5a`.
- **Final tests**: `1141 passed, 20 deselected, 144 warnings`.

## A. Baseline
```
root: D:\MARKET_AI_HUB
branch: main → feat branch
starting HEAD: cac311de836be2d9e95e05d826eec10f69928bdf
origin/main: same
working tree: clean → clean
Python: 3.12.13
starting build_id: d8584c5c14eabb78
ending build_id: 1f120a6b22930b5a
```

## B. Preflight
```
existing ResearchState callers: forecast/contract.py:112 (def) + forecast/synthesis.py:14,44-58 (internal)
legacy MARKET_STATES callers: price_probability_map.py:129 (def) + :1067 (internal validation)
existing state machine implementation: NONE
existing CHASE_RISK implementation: NONE
V2-C runtime callers: NONE (labels.py has no runtime caller)
future-label leakage found: NONE in existing code (V2-C is not wired to state)
```

## C. Contract
```
schema: 2D.1
Directional: STRONG_BULL/BULLISH/NEUTRAL/BEARISH/STRONG_BEAR
Extension: NORMAL/EXTENDED/EXTREME
Structural: BREAKOUT_ATTEMPT/ACCEPTANCE_CONFIRMED/ACCEPTANCE_FAILED/REJECTION/BREAKDOWN_ATTEMPT/RECLAIM
Risk: NORMAL/EXHAUSTION_WARNING/REVERSAL_RISK/MODEL_FAILURE
CHASE: ALLOW/CAUTION/STOP
Layer evaluation statuses: NOT_EVALUATED/EVALUATED/UNVERIFIED/CONFLICT/BLOCKED
snapshot statuses: NO_EVIDENCE/COMPOSED_PARTIAL/COMPOSED_COMPLETE/BLOCKED
supported frequency: DAILY
identity dimensions: instrument/target_family/instrument_role/calendar_id/frequency/horizon
```

## D. Anti-leakage
```
Can V2-C outcome at D2 alter state at D0? NO
machine enforcement: validate_state_evidence returns BLOCKED_FUTURE_OUTCOME_EVIDENCE when
  source_type=V2C_OUTCOME and settled_at > cutoff; V2-C bool labels are NOT Structural values
test evidence: test_future_v2c_outcome_cannot_leak_into_original_forecast_state, test_no_automatic_touch_to_breakout_mapping
```

## E. Default behavior (all None / NOT_EVALUATED)
```
no evidence Direction: None/NOT_EVALUATED
no evidence Extension: None/NOT_EVALUATED
no evidence Structural: None/NOT_EVALUATED
no evidence Risk: None/NOT_EVALUATED
no evidence CHASE: None/NOT_EVALUATED
```

## F. Conflict behavior
```
same-layer same-value: EVALUATED (evidence ids preserved)
same-layer conflict: CONFLICT (value None, conflicting values in reason_codes)
cross-layer evidence: independent (Direction CONFLICT does not erase Structural EVALUATED)
```

## G. Direction vs CHASE
```
BULLISH + STOP: legal
BEARISH + ALLOW: legal
STOP implies SHORT: NO (machine-tested; no short/sell/trade fields in snapshot)
```

## H. Transition
```
transition identity: deterministic sha256(prev_id|new_id)
changed_layers: pure value/status diff across 5 layers
temporal rule: current.state_origin > previous.state_origin (else reject)
probability_before/after: None; probability_status: NOT_AVAILABLE
persistence: none (in-memory only; StatePersistencePolicy default NOT_CONFIGURED)
```

## I. Legacy compatibility
```
ResearchState modified: NO
PPM MARKET_STATES modified: NO
automatic mapping added: NO
```

## J. Changed files
- ADD `src/market_ai_hub/research/v2/state_machine.py`
- ADD `tests/test_v2d_state_machine.py` (45 tests)
- ADD `docs/architecture/v2-state-machine-contract.md`
- ADD `research/phase3/reports/PHASEV2D_DYNAMIC_STATE_MACHINE_SCAFFOLD_REPORT.md`
- MOD `docs/development/project-status.md` (current status)
- MOD `tests/test_challengers_2d1.py` / `test_research.py` / `test_tournament.py` (build_id snapshot)

## K. Tests
```
test_v2d_state_machine.py: 45 passed, exit 0
v2a+v2b+v2c+v2d: 180 passed, exit 0
phase3a*: 121 passed, exit 0
full suite: 1141 passed, 20 deselected, 144 warnings, exit 0
V2-D -W error: 45 passed (no V2-D-origin warnings)
```

## L. Integration status
```
actual market state evaluation: NOT_AVAILABLE (no trusted state evidence wired; scaffold only)
MCP integration: NOT_INTEGRATED_THIS_PHASE
Prediction Audit DB: NOT_STARTED (V2-H)
V2-E started: NO
V2-F started: NO
V2-G started: NO
```

## M. Safety
```
model training: NO  distribution fitting: NO  calibration fitting: NO  public probability: NO
trade signal: NO  broker/order: NO  new scheduler: NO  persistent audit DB: NO
Phase2 freeze changed: NO
```

## N. Gate
**PHASEV2D_DYNAMIC_STATE_MACHINE_SCAFFOLD_PASS** (typed scaffold + evidence/leakage/isolation gates;
actual market state evaluation remains NOT_AVAILABLE until trusted evidence exists).

STOPPED AFTER V2-D. V2-E NOT STARTED.
