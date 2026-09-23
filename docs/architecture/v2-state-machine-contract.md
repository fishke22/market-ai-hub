# V2 Dynamic State Machine Contract

- **Schema**: `V2_STATE_MACHINE_SCHEMA_VERSION = "2D.1"` (module `src/market_ai_hub/research/v2/state_machine.py`)
- Independent from `2A.1` / `2B.1` / `2C.2` / `3A.2.3`.

## Five state domains (layer value ≠ evaluation status)

| layer | values |
|---|---|
| DIRECTIONAL | STRONG_BULL / BULLISH / NEUTRAL / BEARISH / STRONG_BEAR |
| EXTENSION | NORMAL / EXTENDED / EXTREME (V2-E evaluator NOT built) |
| STRUCTURAL | BREAKOUT_ATTEMPT / ACCEPTANCE_CONFIRMED / ACCEPTANCE_FAILED / REJECTION / BREAKDOWN_ATTEMPT / RECLAIM |
| RISK | NORMAL / EXHAUSTION_WARNING / REVERSAL_RISK / MODEL_FAILURE |
| CHASE_RISK | ALLOW / CAUTION / STOP (independent of Direction) |

Evaluation status (`LayerState.status`): `NOT_EVALUATED / EVALUATED / UNVERIFIED / CONFLICT / BLOCKED`.
`value` is a separate field — `value=None + status=NOT_EVALUATED` ≠ `value=NEUTRAL + status=EVALUATED`.

## No default state

No evidence → all five layers `value=None, status=NOT_EVALUATED`. Never default `NEUTRAL` /
`NORMAL` / `ALLOW`.

## Evidence provenance & point-in-time

`StateEvidence` requires identity + timestamps + provenance. Eligibility:
`available_at <= feature_cutoff_timestamp <= state_origin` and `event_timestamp <= cutoff`.
`provenance_status ∈ {AUTHORITATIVE, VERIFIED_INPUT}` → can yield `EVALUATED`;
`UNKNOWN` → `UNVERIFIED` (value None, never published).

## V2-C outcome anti-leakage

V2-C Touch/Break/Acceptance are **forecast-outcome** labels, NOT forecast-time features. An
`Accceptance=True` settled at D2 MUST NOT set `ACCEPTANCE_CONFIRMED` in a D0 snapshot.
`source_type=V2C_OUTCOME` requires `settled_at <= cutoff` and full outcome provenance, else
`BLOCKED_FUTURE_OUTCOME_EVIDENCE`. No automatic Touch→Breakout / Acceptance→AcceptanceConfirmed
mapping exists.

## Conflict handling

Same-layer same-value trusted evidence → `EVALUATED`. Same-layer conflicting values → `CONFLICT`
(value None), no majority/recency/confidence/LLM resolution. Cross-layer independence: a
Direction conflict does not erase a valid Structural layer.

## Identity & multi-horizon isolation

Evidence must match context on instrument / target_family / instrument_role / calendar_id /
frequency / horizon; mismatch → `BLOCKED_IDENTITY_MISMATCH`. Each horizon is an independent state
stream; transitions may not cross identity or horizon.

## Transition

`transition(previous, current)` produces a deterministic `StateTransitionRecord`:
`changed_layers` (pure diff), monotonic time (backward → rejected), cross-identity → rejected,
`probability_before/after = None`, `probability_status = NOT_AVAILABLE`. No trade fields.

## Limits (explicit)

- No extension/exhaustion evaluator (V2-E).
- No sequential updating / change-point (V2-G).
- No persistence DB (V2-H); tests use in-memory lists only.
- No probabilities / calibration / trading semantics / LLM state selection.
- `StatePersistencePolicy` default `NOT_CONFIGURED` / `HYPOTHESIS_ONLY` (no hidden hysteresis).
- Legacy `ResearchState` (BULLISH_EVIDENCE/…) and `MARKET_STATES` (BUY_ZONE/…) coexist unchanged;
  no automatic mapping into V2-D domains.
