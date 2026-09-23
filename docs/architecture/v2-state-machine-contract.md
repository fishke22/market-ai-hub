# V2 Dynamic State Machine Contract

- **Schema**: `V2_STATE_MACHINE_SCHEMA_VERSION = "2D.4"` (module `src/market_ai_hub/research/v2/state_machine.py`)
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
**Temporal ordering is fully enforced**: `event_timestamp <= available_at <= feature_cutoff_timestamp
<= state_origin`; `available_at < event_timestamp` is an impossible-ordering block
(`BLOCKED_TEMPORAL_EVIDENCE_PROVENANCE`), distinct from future-leakage (`BLOCKED_FUTURE_EVIDENCE`).

## Canonical time & determinism

All stored timestamps are tz-aware **UTC** (inputs normalized in `__post_init__`); naive rejected.
`created_at` is UTC. Set-like outputs (`evidence_ids`, `source_snapshot_ids`, `reason_codes`,
`trigger_evidence_ids`, `evidence_asof_by_id` keys) are canonical-sorted unique — caller order does
not change `snapshot_id` or `semantic_dump()`. **Target identity is canonicalized** at the typed
boundary (`normalize_instrument` / `normalize_family`), so `jnu/osaka_micro` and `JNU/OSAKA_MICRO`
produce the same `snapshot_id` AND the same `semantic_dump()`. Snapshot lineage is role-preserved:
`context_source_snapshot_ids` + `evidence_source_snapshot_ids` + derived union `source_snapshot_ids`.

## Blocked snapshots

A blocked snapshot is a content-consistent `StateSnapshot` with `snapshot_status=BLOCKED`; its
`snapshot_id` is the same canonical semantic fingerprint used for success snapshots (see "Snapshot
identity" below), so context lineage and context `asof_status` participate even when the derived
asof is masked. It preserves `block_reason_codes` / `blocked_evidence_ids` /
`offending_evidence_fingerprint` and full context/evidence source lineage, so two different
malformed evidence produce different blocked ids, and identical malformed inputs produce identical
ids. Blocked snapshots cannot be transitioned (`BLOCKED_INVALID_SNAPSHOT_TRANSITION`).

## V2-C outcome anti-leakage

V2-C Touch/Break/Acceptance are **forecast-outcome** labels, NOT forecast-time features. An
`Acceptance=True` settled at D2 MUST NOT set `ACCEPTANCE_CONFIRMED` in a D0 snapshot.
`source_type=V2C_OUTCOME` requires full provenance (`source_forecast_origin`, `outcome_window_start/
end`, `outcome_first_event_session`, `settled_at`, `label_schema_version` == `2C.2`) plus
`source_forecast_origin <= event_timestamp <= settled_at <= cutoff`; the three window dates must be
**strict ISO `YYYY-MM-DD`** (true Gregorian dates) with `window_start <= first_event <= window_end`.
Otherwise `BLOCKED_FUTURE_OUTCOME_EVIDENCE`. No automatic Touch→Breakout / Acceptance→AcceptanceConfirmed
mapping exists.

## Conflict handling

Same-layer same-value trusted evidence → `EVALUATED`. Same-layer conflicting values → `CONFLICT`
(value None), no majority/recency/confidence/LLM resolution. Cross-layer independence: a
Direction conflict does not erase a valid Structural layer.

## Identity & multi-horizon isolation

Evidence must match context on instrument / target_family / instrument_role / calendar_id /
frequency / horizon; mismatch or empty → `BLOCKED_IDENTITY_MISMATCH`. Each horizon is an
independent state stream; transitions may not cross identity or horizon.

## Snapshot identity (2D.4 content-consistency)

`snapshot_id` is content-addressed: it is `sha256(canonical_json(semantic payload))[:16]` where the
payload covers **every** semantic `StateSnapshot` field except `snapshot_id` and `created_at`.
Included: target identity, `feature_cutoff_timestamp`/`state_origin`, all five `LayerState` full
semantics (`value`, `status`, `evidence_ids`, `source_snapshot_ids`, `reason_codes`),
`snapshot_status`, `evidence_ids`, `context_source_snapshot_ids`/`evidence_source_snapshot_ids`/
`source_snapshot_ids`, `block_reason_codes`, `blocked_evidence_ids`,
`offending_evidence_fingerprint`, `context_asof_status`, `evidence_asof_statuses`/
`evidence_asof_by_id`, `derived_asof_status`, and `state_schema_version`. Canonicalization: set-like
lists sorted-unique, dict keys sorted, timestamps canonical UTC ISO, `json.dumps(sort_keys=True,
separators=(",", ":"))`. Invariant: **same `snapshot_id` ⇒ same semantic snapshot artifact**, and
input order (evidence / source ids / dict insertion) never changes the id, while `created_at`
(wall-clock) is excluded from identity. Blocked snapshots use this same content-consistent rule.

## Transition

`transition(previous, current)` produces a deterministic `StateTransitionRecord` whose
`transition_id` fingerprints previous/new snapshot ids + canonical `trigger_evidence_ids` (+ schema),
so trigger attribution changes the id while trigger reorder does not. Blocked snapshots are rejected
(`BLOCKED_INVALID_SNAPSHOT_TRANSITION`). `trigger_evidence_ids` must be a subset of
`current.evidence_ids`. Monotonic time (backward rejected). `source_snapshot_ids` = union(previous,
current). `changed_layers` = pure diff. `probability_before/after = None`,
`probability_status = NOT_AVAILABLE`. No trade fields.

**Transition isolation (2D.4):** every `previous_*_state` / `new_*_state` is a deep copy of the
source snapshot's `LayerState` (including `evidence_ids`, `source_snapshot_ids`, `reason_codes`). A
later mutation of the `previous`/`current` snapshot — or of its nested layer lists — cannot rewrite
an already-produced `StateTransitionRecord`; `semantic_dump()` and `transition_id` stay fixed.

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
