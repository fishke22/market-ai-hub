# V2 Catalyst Response Contract

- **Schema**: `V2_CATALYST_RESPONSE_SCHEMA_VERSION = "2F.3"` (module
  `src/market_ai_hub/research/v2/catalyst_response.py`)
- Independent from `2A.1` / `2B.1` / `2C.2` / `2D.3` / `2E.3` / `3A.2.3`.

## Descriptive, non-causal

Hard invariants: CATALYST ASSOCIATION != CAUSATION; TEMPORAL PRECEDENCE != LEAD-LAG EVIDENCE;
RESPONSE != PREDICTION; RESIDUAL != ALPHA; DECAY DESCRIPTOR != REVERSAL SIGNAL.
`causal_status` is fixed `NOT_ESTABLISHED`. No beta fitting, no Granger, no lag search, no factor
ranking, no threshold optimization.

## Catalyst truth

`CatalystObservation` kinds: `MARKET_MOVE / MACRO_RELEASE / POLICY_EVENT / OBSERVED_EVENT /
SCHEDULE_ONLY`; measurement kinds `RETURN / LEVEL_CHANGE / BPS_CHANGE / SURPRISE / EVENT_ONLY`
(magnitudes are never cross-unit compared). Only `observation_semantics=OBSERVED` +
`availability_status=AVAILABLE` + `event_timestamp <= available_at <= cutoff` + complete source
identity may enter realized response. `SCHEDULE_ONLY` → `BLOCKED_CATALYST_NOT_OBSERVED`;
`SCENARIO/FORECAST/ACTUAL_FUTURE` → `BLOCKED_NON_OBSERVED_CATALYST_SOURCE`. Prior-day US close stays
`PREVIOUS_SESSION_REFERENCE` (association = `REFERENCE_CONTEXT_ONLY`, never live). Macro revision
risk is preserved (`revision_status`), never masqueraded as vintage-safe.

2F.2 structural hardening: `frequency` is constrained to `DAILY/IRREGULAR` (else ValueError);
`factor_name` non-empty; numeric measurements (`RETURN/LEVEL_CHANGE/BPS_CHANGE/SURPRISE`) require a
finite magnitude + unit, `EVENT_ONLY` forces `magnitude=None`. `SCHEDULE_ONLY` blocks regardless of
`observation_semantics`.

2F.3 release-time temporal ordering: any supplied `release_timestamp` must obey
`event_timestamp <= release_timestamp <= available_at <= feature_cutoff_timestamp`, else
`BLOCKED_RELEASE_TIME_PROVENANCE`. `MACRO_RELEASE` additionally requires a non-null
`release_timestamp`; a non-macro catalyst with no release concept may keep `release_timestamp=None`.
Release timestamps are canonicalized to UTC (`+00:00`).

## Response window

`TargetResponseEndpoint` carries full target identity + price + point-in-time + series/roll. 2F.3 is
`POST_CATALYST` only: `catalyst.available_at <= start.event_timestamp < end.event_timestamp`; a
pre-catalyst window → `BLOCKED_PRE_CATALYST_WINDOW`. Return = `(end/start) - 1`.
`response_available_at = max(catalyst, start, end availability)`. `response_delay_seconds =
start - catalyst.available_at >= 0` (a descriptor, not a lead-lag score). Daily-only target
response; futures roll/series fail-closed (UNKNOWN `series_semantics` → `BLOCKED_SERIES_SEMANTICS_MISMATCH`).
`response_delay_seconds` is not a lead-lag coefficient.

`response_id` is derived deterministically from the full catalyst semantic fingerprint + context
identity + endpoint fingerprints + schema version (prefix `v2f_resp_`); the caller `response_label`
is presentation-only and cannot change semantic identity.

## Residual

Only a typed `ExpectedResponseBaselineEvidence` bound to the response target identity (instrument /
family / role / calendar / frequency / horizon) and time-stream may produce
`response_residual = actual - expected` (`DESCRIPTIVE_RESPONSE_RESIDUAL`). 2F.2 requires baseline
timestamps mandatory + ordered (`fit_window_end <= baseline_available_at <= catalyst.available_at`
and `fit_window_end <= catalyst.event_timestamp`); any violation → `BLOCKED_BASELINE_TEMPORAL_LEAKAGE`
or `BLOCKED_BASELINE_TEMPORAL_PROVENANCE`. Cross-target identity → `BLOCKED_BASELINE_IDENTITY_MISMATCH`;
missing source → `BLOCKED_BASELINE_SOURCE_PROVENANCE`. `validation_status` is frozen
`HYPOTHESIS_ONLY`. An `UNKNOWN`-provenance baseline never publishes a verified residual
(`residual_status=UNVERIFIED_BASELINE`, `expected_response=None`, `response_residual=None`); otherwise
`expected_response=None`, `response_residual=None`, `residual_status=NOT_AVAILABLE` (no hidden
expected=0). Residual is never labeled alpha/edge. No baseline fitting in V2-F.

## Response path (descriptive)

`summarize_response_path` returns a `CatalystResponsePath` with `path_status` /
`block_reason_codes` / `assessment_ids` / deterministic `path_id`. It requires same catalyst
(id + fingerprint), same target identity + state stream, same response anchor, eligible
(`DESCRIPTIVE_AVAILABLE`/`REFERENCE_CONTEXT_ONLY`) assessments, and strictly increasing window end
times. All checks are set-based (never relative to `assessments[0]`). Violations →
`BLOCKED_INELIGIBLE_RESPONSE_ASSESSMENT` / `BLOCKED_CATALYST_ID_COLLISION` /
`BLOCKED_IDENTITY_MISMATCH` / `BLOCKED_STATE_STREAM_MISMATCH` / `BLOCKED_RESPONSE_ANCHOR_MISMATCH` /
`BLOCKED_RESPONSE_ID_COLLISION` / `BLOCKED_PATH_HORIZON_ORDER`, in that fixed precedence. Computes
`response_returns_by_horizon`, `absolute_response_by_horizon`, `peak_absolute_response`,
`terminal_to_peak_abs_ratio` (None if peak=0), `time_to_peak_seconds`. No decay-curve fitting, no
arbitrary decay classification threshold.

2F.3 blocked-path determinism: a blocked path's `path_id` is derived from the canonical complete
input assessment set (via the semantic fingerprint `_assessment_semantic_fp`, which excludes
presentation metadata such as `response_label`) + block reason + schema — never from `assessments[0]`.
Reversing input order yields the same blocked `path_id`. Blocked paths preserve audit lineage:
`assessment_ids`, `source_snapshot_ids`, `derived_asof_status`, plus `candidate_catalyst_ids`,
`candidate_catalyst_fingerprints`, `candidate_target_identities`, `candidate_state_stream_ids`,
`candidate_response_anchor_fingerprints`. `response_label` never participates in collision
detection or semantic identity.

## No state mapping

Catalyst response never maps to Directional/Risk/CHASE/Extension. A positive NQ move does not
create `BULLISH`; a VIX jump does not create `BEARISH`/`CHASE_STOP`.

## Capability / readiness

External-factor managed datasets: NQ/ES/USDJPY/SOX/VIX = NOT_AVAILABLE; USTREASURY daily cache but
`point_in_time_safe=false`; FRED configured periodic with revision risk; event DB NOT_PRESENT.
`CATALYST_RESPONSE_ACTUAL_DATASET = NOT_AVAILABLE`. No network/data acquisition in this phase.
ENGINE PASS != CAUSAL/PREDICTIVE EVIDENCE != MARKET DATA READINESS != TRADING EDGE.
