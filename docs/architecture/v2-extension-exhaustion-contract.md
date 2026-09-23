# V2 Extension / Exhaustion Contract

- **Schema**: `V2_EXTENSION_EXHAUSTION_SCHEMA_VERSION = "2E.2"` (module
  `src/market_ai_hub/research/v2/extension_exhaustion.py`)
- Independent from `2A.1` / `2B.1` / `2C.2` / `2D.3` / `3A.2.3`.

## Scope

`DAILY_RESEARCH_PROXY`. Daily OHLC/ATR only. No intraday extension, no VWAP/session-high-low, no
time-at-high/low, no intraday relative volume, no order flow.

## Canonical extension definition

`reference_kind = PREVIOUS_CLOSE` (current completed daily close vs previous completed daily close,
normalized by a PRIOR ATR baseline):

```
signed_extension_units   = (current_close - previous_close) / atr_baseline
absolute_extension_units = abs(signed_extension_units)
extension_side           = UP / DOWN / FLAT
extension_state:
  abs_units <  1.0  -> NORMAL
  1.0 <= abs_units < 2.0 -> EXTENDED
  abs_units >= 2.0  -> EXTREME
```

ATR units are NOT σ / z-score / probability. ATR baseline is pre-move:
`atr_event <= previous_close_event < current_close_event`, and every
`event <= available <= cutoff <= origin`.

## Research thresholds (1 / 2 ATR) — FROZEN

`extended_threshold_atr = 1.0`, `extreme_threshold_atr = 2.0`, `atr_period = 14`,
`atr_method = EXISTING_MARKET_AI_HUB_ATR_EWM`, `validation_status = HYPOTHESIS_ONLY`,
`optimization_status = NOT_OPTIMIZED`. The 2E.2 canonical policy is **frozen** — any caller mutation
of these fields is rejected. No grid search / Optuna / PnL selection / single-day tuning.

## Point-in-time scalar + identity provenance (2E.2)

`PointInTimeScalar` carries full target identity (instrument/target_family/instrument_role/
calendar_id/frequency/horizon), `series_semantics` and `roll_status` (canonical enums), and
(event_timestamp, available_at). All three scalars (current_close, previous_close, atr_baseline)
must match the `StateEvaluationContext` identity; mixed series semantics → `BLOCKED_SERIES_SEMANTICS_MISMATCH`.
The ATR baseline must carry `atr_period=14` + `atr_method` (else `BLOCKED_ATR_POLICY_MISMATCH`).
For futures (OSAKA_MICRO DIRECT) `roll_status` must be `NONE` (UNKNOWN/ROLL_BOUNDARY/NOT_APPLICABLE
→ `BLOCKED_ROLL_PROVENANCE`); unknown roll/series strings are rejected. The V2-D context contract is
validated (`cutoff <= origin`, identity, ASOF enum), and `derived_asof_status` is the least-verified
of context + all scalars.

## Invariants

- `EXTENSION != EXHAUSTION`; `EXTENDED`/`EXTREME` alone never imply exhaustion.
- `extension_side` (UP/DOWN) is NOT Direction/Bullish/Bearish/Long/Short.
- `EXHAUSTION_WARNING != REVERSAL / BEARISH / CHASE_STOP / SHORT / SELL`.
- No probability, no trade semantics.

## Exhaustion Warning rule

Warning established only when: extension ∈ {EXTENDED, EXTREME} **and** >= 2 distinct trusted
positive confirmation families. Families: `MOMENTUM_STALL`, `PRICE_VOLUME_DIVERGENCE`,
`STRUCTURAL_FAILURE`, `OSCILLATOR_EXTREME`. Multiple evidence rows of the SAME family count once.
`present` must be a real `bool`; component source identity is mandatory; a component-id collision
(same id, different payload) → `BLOCKED_COMPONENT_ID_COLLISION` (no double-vote). A family with both
`present=True`/`False` trusted rows → `CONFLICT`. `UNKNOWN`-provenance components are lineage-only.
Direct `V2C_OUTCOME` component sources are blocked (`BLOCKED_DIRECT_FUTURE_OUTCOME_SOURCE`).
Insufficient confirmation → `INSUFFICIENT_CONFIRMATION`, never `RISK=NORMAL`.
The extension assessment must match the exhaustion context identity/time-stream (no cross-target).
Warning timestamps are derived from the extension + required positive evidence
(`warning_available_at` = latest required availability), never caller-supplied.

## State-machine integration (V2-D 2D.3)

- `extension_to_state_evidence` → `layer=EXTENSION`, only when `EVALUATED` and the assessment
  identity matches the context (no cross-market retarget).
- `exhaustion_to_state_evidence` → `layer=RISK`, `value=EXHAUSTION_WARNING`, only when
  `WARNING_ESTABLISHED`; otherwise `None` (never emits `RISK=NORMAL`). Timestamps read from the
  assessment (no caller backdating).
- Generated evidence: `provenance_status=VERIFIED_INPUT`, `validation_status=HYPOTHESIS_ONLY`,
  `source_schema_version=2E.2`, deterministic `evidence_id`, passes `validate_state_evidence`.
- Exhaustion Warning does NOT alter Direction, does NOT set CHASE_RISK, is NOT REVERSAL_RISK.

## Lineage & determinism

Role-preserved lineage (`context_source_snapshot_ids` / scalar-role / component-role + union)
on EVALUATED, UNVERIFIED, CONFLICT and BLOCKED paths. Assessment IDs fingerprint target identity,
time, schema/policy, scalar/component semantic fingerprints, lineage, ASOF, status and blockers —
same semantic inputs → same id; different evidence lineage → different id; caller order → same id.

## Capability matrix

```
DAILY_ATR_EXTENSION:                     ENGINE_AVAILABLE
DAILY_EXHAUSTION_COMPONENT_AGGREGATION:  ENGINE_AVAILABLE
INTRADAY_EXTENSION_FROM_OPEN:            DATA_DEPENDENT
VWAP_EXTENSION:                          DATA_DEPENDENT
SESSION_HIGH_LOW_EXTENSION:              DATA_DEPENDENT
TIME_AT_HIGH_LOW:                        DATA_DEPENDENT
INTRADAY_RELATIVE_VOLUME:                DATA_DEPENDENT
VOLUME_PROFILE:                          DATA_DEPENDENT
ORDER_FLOW_EXHAUSTION:                   DATA_DEPENDENT
```

## Actual data limitations

OSAKA_MICRO: daily OHLCV field-capable but roll/calendar/session provenance incomplete → NOT_READY.
TAIWAN_STOCK: FIELD_READY_ONLY. `^N225`: close-only → ATR requires high/low → DAILY_ATR_EXTENSION
NOT_READY. TAIWAN_INDEX: NOT_AVAILABLE_LOCAL_DATASET. ENGINE PASS != MARKET VALIDATION !=
PREDICTIVE EVIDENCE != TRADING EDGE.
