# V2 Dynamic State Machine Contract

- **Schema**: `V2_STATE_MACHINE_SCHEMA_VERSION = "2D.2"` (module `src/market_ai_hub/research/v2/state_machine.py`)
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

`StateEvidence` must carry non-empty `evidence_id`, a legal non-null `value`, non-empty target
identity (instrument/target_family/instrument_role/calendar_id/frequency/horizon), non-empty
source identity (`source_type`/`source_schema_version`/`source_version`), mandatory
`event_timestamp` + `available_at`, and a known `asof_status`. A malformed trusted evidence
(missing timestamps, empty identity, empty source identity, unknown asof) → `BLOCKED_*`, never
`EVALUATED`. Point-in-time: `event_timestamp <= available_at <= feature_cutoff_timestamp <=
state_origin`. `provenance_status ∈ {AUTHORITATIVE, VERIFIED_INPUT}` → can yield `EVALUATED`;
`UNKNOWN` → `UNVERIFIED` (structurally-valid but unprovenanced, value None).

## Canonical time & determinism

All stored timestamps are tz-aware **UTC** (inputs normalized in `__post_init__`); naive rejected.
`created_at` is UTC. Set-like outputs (`evidence_ids`, `source_snapshot_ids`, `reason_codes`,
`trigger_evidence_ids`, `evidence_asof_by_id` keys) are canonical-sorted unique — caller order does
not change `snapshot_id` or `semantic_dump()`. Snapshot lineage is role-preserved:
`context_source_snapshot_ids` + `evidence_source_snapshot_ids` + derived union `source_snapshot_ids`.

## V2-C outcome anti-leakage

V2-C Touch/Break/Acceptance are **forecast-outcome** labels, NOT forecast-time features. An
`Acceptance=True` settled at D2 MUST NOT set `ACCEPTANCE_CONFIRMED` in a D0 snapshot.
`source_type=V2C_OUTCOME` requires full provenance (`source_forecast_origin`, `outcome_window_start/
end`, `outcome_first_event_session`, `settled_at`, `label_schema_version` == `2C.2`) plus
`source_forecast_origin <= event_timestamp <= settled_at <= cutoff` and
`window_start <= first_event <= window_end`; otherwise `BLOCKED_FUTURE_OUTCOME_EVIDENCE`.
No automatic Touch→Breakout / Acceptance→AcceptanceConfirmed mapping exists.

## Conflict handling

Same-layer same-value trusted evidence → `EVALUATED`. Same-layer conflicting values → `CONFLICT`
(value None), no majority/recency/confidence/LLM resolution. Cross-layer independence: a
Direction conflict does not erase a valid Structural layer.

## Identity & multi-horizon isolation

Evidence must match context on instrument / target_family / instrument_role / calendar_id /
frequency / horizon; mismatch or empty → `BLOCKED_IDENTITY_MISMATCH`. Each horizon is an
independent state stream; transitions may not cross identity or horizon.

## Transition

`transition(previous, current)` produces a deterministic `StateTransitionRecord`. Blocked
snapshots are rejected (`BLOCKED_INVALID_SNAPSHOT_TRANSITION`). `trigger_evidence_ids` must be a
subset of `current.evidence_ids`. Monotonic time (backward rejected). `source_snapshot_ids` =
union(previous, current). `changed_layers` = pure diff. `probability_before/after = None`,
`probability_status = NOT_AVAILABLE`. No trade fields.

## Limits (explicit)

- No extension/exhaustion evaluator (V2-E).
- No sequential updating / change-point (V2-G).
- No persistence DB (V2-H); tests use in-memory lists only. Evidence-id collision detection is
  per-composition call; global uniqueness belongs to V2-H.
- No probabilities / calibration / trading semantics / LLM state selection.
- `StatePersistencePolicy` default `NOT_CONFIGURED` / `HYPOTHESIS_ONLY` (no hidden hysteresis).
- `evaluation_mode` ∈ `{RESEARCH}` only.
- Legacy `ResearchState` (BULLISH_EVIDENCE/…) and `MARKET_STATES` (BUY_ZONE/…) coexist unchanged;
  no automatic mapping into V2-D domains.
