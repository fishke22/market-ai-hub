# V2 Sequential Update Contract

- **Schema**: `V2_SEQUENTIAL_UPDATE_SCHEMA_VERSION = "2G.2"` (module
  `src/market_ai_hub/research/v2/sequential_update.py`)
- Independent from `2A.1` / `2B.1` / `2C.2` / `2D.4` / `2E.3` / `2F.3` / `3A.2.3`.

## CORE vs RESEARCH_CHALLENGER boundary

Sequential updating is **CORE_V2**. Change-point algorithms are **RESEARCH_CHALLENGER** and are NOT
implemented here. Machine-readable capability registry `V2G_CAPABILITIES`:

```
DETERMINISTIC_STATE_REVISION            ENGINE_AVAILABLE
RUN_LENGTH_DWELL_DESCRIPTOR             ENGINE_AVAILABLE
PROBABILITY_VELOCITY                    NOT_AVAILABLE_PENDING_CALIBRATED_PROBABILITY
PROBABILITY_ACCELERATION                NOT_AVAILABLE_PENDING_CALIBRATED_PROBABILITY
CUSUM                                    RESEARCH_CHALLENGER_NOT_IMPLEMENTED
PAGE_HINKLEY                             RESEARCH_CHALLENGER_NOT_IMPLEMENTED
BOCPD                                    RESEARCH_CHALLENGER_NOT_IMPLEMENTED
STATE_TRANSITION_PROBABILITY             RESEARCH_CHALLENGER_NOT_IMPLEMENTED
```

## Upstream artifact (only legal input)

V2-G consumes only V2-D `StateSnapshot` / `StateTransitionRecord` (2D.4). It never consumes legacy
`ResearchState` / `MARKET_STATES`, Phase2 direction strings, raw RSI, raw catalyst, or raw model
forecasts.

## Snapshot integrity gate

Every input snapshot must satisfy, in order:
1. upstream schema: `state_schema_version == "2D.4"` (else `BLOCKED_UNSUPPORTED_UPSTREAM_SCHEMA`);
2. `snapshot_status != BLOCKED` (else `BLOCKED_UPSTREAM_SNAPSHOT`);
3. `snapshot_identity(snapshot) == snapshot.snapshot_id` (else `BLOCKED_SNAPSHOT_INTEGRITY_MISMATCH`).

The integrity check reuses V2-D's `snapshot_identity` verifier — it does not re-hash. A mutated /
stale / forged snapshot fails closed; it is never re-hashed and silently accepted.

## Deep-copy ingestion

Snapshots (and transitions) are deep-copied into the sequence artifact; wall-clock `created_at` is
stripped for determinism. Mutating the caller's original snapshot afterwards never changes the
sequence, its `sequence_id`, or its history.

## Identity / horizon isolation

All snapshots must share exactly the same target identity tuple
`(instrument, target_family, instrument_role, calendar_id, frequency, horizon)` (canonicalized
instrument/family); any mismatch → `BLOCKED_IDENTITY_MISMATCH`. No cross-market / cross-frequency /
cross-horizon sequences.

## Chronology / cutoff monotonicity

The builder validates the whole input set, dedupes exact duplicates (same `snapshot_id`), then sorts
canonically by tz-aware UTC `state_origin`. Invariants:
- `state_origin` strictly increasing (same origin + different snapshot → `BLOCKED_AMBIGUOUS_STATE_ORIGIN`);
- `feature_cutoff_timestamp` non-decreasing (regression → `BLOCKED_CUTOFF_REGRESSION`);
- equal cutoff is allowed; a step records `information_advanced = (cutoff increased)`.

Same semantic snapshot set with different caller input order → same `sequence_id` + same artifact.

## State vs attribution revision

Each `StateSequenceStep` separates two orthogonal revision axes:
- `state_changed_layers`: layer `(value, status)` changed (matches V2-D transition semantics);
- `attribution_changed_layers`: layer `evidence_ids` / `source_snapshot_ids` / `reason_codes` changed
  while `(value, status)` may be unchanged.

`update_kind ∈ {STATE_CHANGE, ATTRIBUTION_ONLY, NO_LAYER_CHANGE}`. Evidence/source deltas are
canonical set differences (`evidence_added/removed_ids`, `source_snapshot_added/removed_ids`).
`removed` is a provenance delta, never an "invalidation" claim.

## Descriptive run / dwell

A `LayerRunDescriptor` per layer describes the current run keyed by `(value, status)`. Attribution
changes do NOT reset the run. `run_length_observations` and `run_elapsed_seconds` are descriptive
counts/durations — NOT confirmation / persistence / minimum-dwell rules. `StatePersistencePolicy`
remains `NOT_CONFIGURED` / `HYPOTHESIS_ONLY`.

## Categorical states — no ordinal arithmetic

`STRONG_BEAR=-2 … STRONG_BULL=+2` and `NORMAL=0 / EXTENDED=1 / EXTREME=2` are forbidden. No numeric
state velocity is computed. `CHASE_RISK STOP` does not produce a directional change.

## Probability / change point

`probability_level/velocity/acceleration` are typed `None` placeholders with
`probability_status = NOT_AVAILABLE_UPSTREAM_UNCALIBRATED` (V2-I not started).
`change_point_status = RESEARCH_CHALLENGER_NOT_IMPLEMENTED`, `change_point_method/score = None`.
A state change is NOT a change point.

## Optional transition verification

`build_state_sequence(snapshots, transitions=None)` optionally accepts V2-D `StateTransitionRecord`s:
- each transition must map to an adjacent snapshot pair (else `BLOCKED_ORPHAN_TRANSITION`);
- exact duplicate transitions dedupe; same transition_id + different payload →
  `BLOCKED_TRANSITION_ID_COLLISION`;
- strong integrity: each transition is rebuilt via V2-D `transition(previous, current,
  trigger_evidence_ids=record.trigger_evidence_ids)` and its `semantic_dump()` compared — any forged
  `changed_layers`, mutated `LayerState`, wrong lineage, fake probability, or wrong timestamp →
  `BLOCKED_TRANSITION_INTEGRITY_MISMATCH`;
- a missing transition for a pair is `transition_status = NOT_PROVIDED` (never fabricated).

## Sequence content addressing

`sequence_id` is content-addressed over target identity, schema/policy, chronological `snapshot_ids`,
recomputed snapshot/transition fingerprints, step semantic payloads, run descriptors, source lineage,
derived ASOF, probability/change-point status, and sequence/block status — excluding wall-clock.
Blocked sequences get a deterministic order-independent `sequence_id` from the canonical input set +
reason + schema.

**Self-verifiable identity (2G.2):** for every non-empty artifact (both `SEQUENCE_AVAILABLE` and
`BLOCKED`), `sequence_identity(artifact) == artifact.sequence_id`. Only the empty `NOT_AVAILABLE`
sequence keeps `sequence_id == ""`. There is no separate private blocked hash computed from external
raw inputs.

## Blocked Artifact Auditability

A blocked artifact does **not** store only a hash + reason. It preserves the full candidate/input
audit lineage (`candidate_snapshot_audits` / `candidate_transition_audits` typed entries), so V2-H can
answer: which snapshot/transition caused the block, the caller-declared id, the recomputed
fingerprint, the source lineage, the target/context and ASOF state.

- **Declared vs recomputed identity** are kept separately per candidate: `declared_snapshot_id`
  (the caller's claim) and `recomputed_snapshot_id` (`snapshot_identity(snapshot)`). An integrity
  failure is exactly `declared != recomputed`.
- **Candidate order is canonical** (snapshot: state_origin → declared id → recomputed id; transition:
  previous → new → declared id); input reorder never changes the blocked `sequence_id` or dump.
- **Candidate source lineage** (`candidate_snapshot_source_snapshot_ids`,
  `candidate_transition_source_snapshot_ids`, `candidate_source_snapshot_ids`) and **state stream**
  (`candidate_state_stream_ids`) and **ASOF** (`candidate_snapshot_asof_by_id`, artifact
  `derived_asof_status = least_verified(candidates)`) are preserved — never blanket-defaulted.
- **Common main identity** is filled only when every candidate agrees; mixed identity keeps the main
  identity fields empty and lists the full set in `candidate_target_identities` (never first-item
  authority).
- **Append failure** preserves the existing sequence declared/recomputed identity
  (`existing_sequence_declared_id`, `existing_sequence_recomputed_id`, `parent_sequence_id`) plus the
  new-snapshot candidate lineage. Appending to an already-`BLOCKED` sequence →
  `BLOCKED_EXISTING_SEQUENCE_NOT_APPENDABLE` (audit context carried forward); appending to a
  corrupted `SEQUENCE_AVAILABLE` sequence → `BLOCKED_SEQUENCE_INTEGRITY_MISMATCH`.

## Append purity

`append_state_update(existing, new_snapshot, transition=None)` is a pure in-memory transformation: it
verifies `sequence_identity(existing) == existing.sequence_id` (else
`BLOCKED_SEQUENCE_INTEGRITY_MISMATCH`), deep-copies the new snapshot, never mutates `existing`, and
returns a freshly content-addressed artifact. `build([S0,S1,S2]) == append(append(build([S0]),S1),S2)`.
On failure it returns a self-verifiable BLOCKED artifact with full audit lineage (never an empty stub).

## Limits (explicit)

- No persistence DB / scheduler / daemon (V2-H).
- No calibration / probability fitting (V2-I).
- No CUSUM / Page-Hinkley / BOCPD / state-transition probability.
- No smoothing / hysteresis / state promotion / confirmation policy.
- No trading fields; no probability values; no new `StateEvidence` / `StateSnapshot` emission.
- Actual market V2-G sequence: `NOT_AVAILABLE` (no managed production state history yet).
