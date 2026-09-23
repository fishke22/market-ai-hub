# V2 Catalyst Response Contract

- **Schema**: `V2_CATALYST_RESPONSE_SCHEMA_VERSION = "2F.2"` (module
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
finite magnitude + unit, `EVENT_ONLY` forces `magnitude=None`. `MACRO_RELEASE` additionally requires
`release_timestamp` with `release_timestamp <= available_at`, else
`BLOCKED_RELEASE_TIME_PROVENANCE` (release-time truth is machine-enforced). `SCHEDULE_ONLY` blocks
regardless of `observation_semantics`.

## Response window

`TargetResponseEndpoint` carries full target identity + price + point-in-time + series/roll. 2F.2 is
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
times. Violations → `BLOCKED_INELIGIBLE_RESPONSE_ASSESSMENT` / `BLOCKED_CATALYST_ID_COLLISION` /
`BLOCKED_IDENTITY_MISMATCH` / `BLOCKED_STATE_STREAM_MISMATCH` / `BLOCKED_RESPONSE_ANCHOR_MISMATCH` /
`BLOCKED_RESPONSE_ID_COLLISION` / `BLOCKED_PATH_HORIZON_ORDER`. Computes
`response_returns_by_horizon`, `absolute_response_by_horizon`, `peak_absolute_response`,
`terminal_to_peak_abs_ratio` (None if peak=0), `time_to_peak_seconds`. No decay-curve fitting, no
arbitrary decay classification threshold. Blocked paths keep a deterministic non-empty `path_id`.

## No state mapping

Catalyst response never maps to Directional/Risk/CHASE/Extension. A positive NQ move does not
create `BULLISH`; a VIX jump does not create `BEARISH`/`CHASE_STOP`.

## Capability / readiness

External-factor managed datasets: NQ/ES/USDJPY/SOX/VIX = NOT_AVAILABLE; USTREASURY daily cache but
`point_in_time_safe=false`; FRED configured periodic with revision risk; event DB NOT_PRESENT.
`CATALYST_RESPONSE_ACTUAL_DATASET = NOT_AVAILABLE`. No network/data acquisition in this phase.
ENGINE PASS != CAUSAL/PREDICTIVE EVIDENCE != MARKET DATA READINESS != TRADING EDGE.
