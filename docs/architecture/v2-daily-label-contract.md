# V2 Daily Label Contract

- **Schema**: `V2_DAILY_LABEL_SCHEMA_VERSION = "2C.2"` (module `src/market_ai_hub/research/v2/labels.py`)
- **Scope**: `DAILY`, **validation_status**: `HYPOTHESIS_ONLY`, **calibration_status**: `NOT_CALIBRATED`,
  **public_probability_status**: `NOT_PUBLIC_PROBABILITY`.

## Definitions

### DAILY_TOUCH
For an UP/DOWN barrier level L, a bar with `low <= L <= high` in the outcome window means the daily
OHLC range covers L → `touch_value=True`. It does NOT mean exact fill timestamp, first passage,
high/low ordering, or executability.

### DAILY_CLOSE_BREAK
UP: `close > L`; DOWN: `close < L`. `close == L` is NOT a break. First valid close strictly beyond
→ `break_value=True`.

### DAILY_CLOSE_ACCEPTANCE
`N_CONSECUTIVE_DAILY_CLOSES_BEYOND_BARRIER`, default `N=2` (research parameter, NOT an optimized
value). The Nth consecutive close beyond sets `acceptance_value=True` at that session.

## Outcome horizon semantics

`horizon_sessions = H` (int ≥ 1) = the first H complete trading sessions strictly AFTER
`forecast_origin`. The canonical label window is **`window_sessions = expected_sessions[:H]`** — the
first H eligible-elapsed trusted sessions. Any bar at session H+1 or later is `ignored_out_of_window`
and MUST NOT affect Touch/Break/Acceptance, maturity, roll, identity, data-quality, or session
boundary. First outcome session's `session_open_timestamp > forecast_origin`; a bar spanning
`forecast_origin` (mid-session) is excluded.

**Trusted session-window provenance is required for ALL labels (positive and negative).**
`expected_sessions` (the ordered eligible-elapsed session list) MUST be provided AND
`calendar_provenance` MUST be `AUTHORITATIVE`/`VERIFIED_INPUT`. A plain list or `UNKNOWN`
provenance → `BLOCKED_CALENDAR_PROVENANCE` for every label. An empty trusted list → `UNMATURED`
(no eligible session elapsed yet), not a session-boundary block.

**Touch negative additionally requires a trusted pre-window reference.** `previous_close` is NOT a
naked float: it requires `previous_close_available_at <= feature_cutoff_timestamp` and
`previous_close_provenance` trusted. Without it, Touch negative → `BLOCKED_PREWINDOW_REFERENCE_PROVENANCE`
(a gap-cross over the barrier cannot be ruled out). Break/Acceptance do not require previous_close.

**Barrier provenance is mandatory.** `barrier_available_at` must be present and
`<= feature_cutoff_timestamp`; otherwise `BLOCKED_BARRIER_PROVENANCE`.

## Forecast-time vs outcome separation

`feature_cutoff_timestamp <= forecast_origin` is enforced. Outcome data must be observed strictly
after `forecast_origin` and must not be able to rewrite the barrier. Barrier is frozen at
`barrier_available_at <= feature_cutoff_timestamp`; a future-computed barrier fails closed.

## Gap-cross ambiguity

An UP barrier gap (`prev_close < L` and `next open > L` and `next low > L`) proves the market moved
to the other side but NOT that exact level L traded → `touch_value=None`,
`AMBIGUOUS_GAP_CROSS`. If a later bar satisfies `low <= L <= high`, Touch becomes `True` at that
session. Break may be `True` from the same gap (`close > L`).

## Maturity semantics

Positive events establish early. Negative events require the full horizon to mature, with no
missing expected session and no invalid OHLC; otherwise `value=None` + `UNMATURED` /
`UNOBSERVABLE_MISSING_DATA` / `AMBIGUOUS_GAP_CROSS`.

## No path / order fabrication

`DAILY_OBSERVATION_CHAIN_NOT_ASSUMED`. Touch/Break/Acceptance are independent; Break does not
imply Touch; no first-passage timestamp; no intraday ordering; `path_order_status =
UNKNOWN_WITHIN_DAILY_BAR`.

## ASOF / provenance lineage

`asof_status` is a conservative summary, NOT a caller-declared string. `ASOF_VERIFIED` is only
emitted when `forecast_asof_status` AND `outcome_asof_status` (least-verified of in-window bars)
are both `ASOF_VERIFIED`. A legacy in-window bar forces the summary to `LEGACY_TEMPORAL_UNVERIFIED`.
Role-specific snapshot lineage is preserved: `forecast_source_snapshot_ids` /
`barrier_source_snapshot_ids` / `outcome_source_snapshot_ids` (+ derived union `source_snapshot_ids`).

## Roll handling

Futures (OSAKA_MICRO DIRECT): `roll_status` must be `NONE` (proven) — `ROLL_BOUNDARY` or `UNKNOWN`
→ `BLOCKED_ROLL_PROVENANCE`, **regardless of horizon_sessions**. Out-of-window roll defects do not
contaminate in-window labels. Non-futures: `NOT_APPLICABLE`. `UNKNOWN != NONE`.
Mixed in-window `series_semantics` → `BLOCKED_SERIES_SEMANTICS_MISMATCH`.

## Identity / target isolation (machine-enforced)

instrument, target_family, instrument_role, calendar_id must be consistent within a series and
with the request. Mismatch → `BLOCKED_IDENTITY_MISMATCH`. Osaka Direct ≠ ^N225 proxy ≠ Taiwan ≠
TAIEX/TX/MTX/TMF.

## Legacy / asof

Legacy daily input remains `LEGACY_TEMPORAL_UNVERIFIED`; never auto-upgraded to `ASOF_VERIFIED`.

## Data quality

Prices must be finite, non-NaN, non-Inf, > 0. `low <= open <= high`, `low <= close <= high`,
`low <= high`. Invalid → `INVALID_OHLC`, never silent coercion / zero-fill.

## No probability / calibration / trade signal

Labels are outcome labels only. No `P(touch)`, no `CalibrationEvidence`, no long/short/order.
Terminal calibration never vouches for Touch calibration.

## Limitations

- Daily OHLC cannot reconstruct intraday event chain / ordering.
- Gap exact-touch is ambiguous.
- OSE futures roll provenance is absent (multi-session labels block).
- OSE holiday-trading session calendar coverage is limited to config + exchange_calendars.
- Local dataset availability: `^N225` close-only, `TAIWAN_INDEX` no managed OHLC.