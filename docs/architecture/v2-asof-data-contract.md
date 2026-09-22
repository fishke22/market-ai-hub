# V2 As-Of Data Contract

- **Schema**: `V2_ASOF_SCHEMA_VERSION = "2A.1"` (module `market_ai_hub/research/v2/asof.py`)
- Independent from Price/Probability Map `3A.2.x` (both versioned separately).

## Core invariant (machine-enforced)

```
feature_information_time <= feature_cutoff_timestamp <= forecast_origin
```

Point-in-time truth is **information availability** (`observed_at`), not market event time alone.

## Timestamp semantics (never mixed)

| field | meaning |
|---|---|
| `event_timestamp` | actual market event time |
| `source_timestamp` | time the source claims |
| `observed_at` | when the system first observed it |
| `ingested_at` | when it entered MARKET_AI_HUB |
| `feature_cutoff_timestamp` | the latest time a feature may use data |
| `forecast_origin` | the model's formal forecast time |

## Timezone policy

- Canonical internal timestamp = **timezone-aware UTC**.
- Exchange-local timestamps + exchange timezone are preserved.
- Naive datetime → rejected (`TemporalContext.__post_init__` raises). A legacy adapter may carry
  `LEGACY_NAIVE_TIMESTAMP` but never pretends to be fully normalized.
- Supported calendars: `XTAI`(Asia/Taipei), `OSE_DERIVATIVES`(Asia/Tokyo), `XTKS`(Asia/Tokyo),
  `XNYS`(America/New_York), `CME`(America/Chicago).

## As-of rules

- `get_asof(observations, instrument, fields, cutoff)` returns only observations with
  `observed_at <= cutoff` and no future-data rejection.
- `reject_future_information()` blocks `OBSERVED_AFTER_CUTOFF`, `FUTURE_EVENT`, `RELEASE_AFTER_CUTOFF`.
- `point_in_time_join()` matches each forecast/feature cutoff to the latest observation available
  at or before the cutoff; `max_age` cap; forward fill only when allowed and never across an illegal
  boundary.

## Staleness / latency

- `StalenessStatus`: `FRESH / DELAYED / STALE / CLOSED_MARKET_REFERENCE / UNKNOWN / NOT_AVAILABLE`.
- `context_role`: `LIVE / PREVIOUS_SESSION_REFERENCE / DELAYED_REFERENCE / STATIC_MACRO_CONTEXT / UNAVAILABLE`.
- Policy from `config/data/staleness_policy.yaml` (source/frequency cadence + soft/hard thresholds).
- Stale data is never auto-promoted to fresh. A prior-session US close in an Asian session is
  `PREVIOUS_SESSION_REFERENCE`, not `LIVE`.

## Session / trading date

- `MarketSessionContext` captures calendar, session type, cash/derivatives/US market open,
  holiday-trading, overnight flag.
- TSE-cash-closed + OSE-derivatives-open holiday trading is machine-representable
  (`cash_market_open=False, derivatives_market_open=True, is_holiday_trading=True`).
- Direct `OSAKA_MICRO` stays `OSE_DERIVATIVES`; `^N225` proxy stays `XTKS`.

## Snapshot identity

- `DataSnapshot` carries `snapshot_id`, provider, instrument, retrieved/source/observed ranges,
  row count, schema version, content hash, path, license class, local-only, immutability.
- Default `immutability = MUTABLE_CACHE` (honest); only set `IMMUTABLE` when verified.
- Stable identity from canonical metadata + content hash.

## Release time / macro safety

- `ReleaseTimeContext` carries `release_timestamp, release_status, revision_status, vintage_status`.
- A macro value whose release is after the cutoff is unusable.
- Without ALFRED/vintage, historical macro point-in-time is `REVISION_RISK_PRESENT` (never
  treated as if the latest value equals what was visible then).

## Future leakage guard

- `TemporalLeakageCheckResult`: `PASS / FAIL_FUTURE_EVENT / FAIL_OBSERVED_AFTER_CUTOFF /
  FAIL_RELEASE_AFTER_CUTOFF / FAIL_TIMEZONE / FAIL_SESSION_MAPPING / FAIL_STALE_POLICY / UNKNOWN`.
- Dev/test research raises on `FAIL_*`; public runtime marks unavailable rather than crashing.

## Capability registry (truthful)

- `supports_capability(target, capability)` returns `(bool, reason)`.
- Audit truth: `OSAKA_MICRO` 1m = NO, `TAIWAN` 1m = NO, tick = NO, L1 = NO, L2 = NO.
- Missing capability → `MISSING_DATA_CAPABILITY` (fail closed; no auto down/up-sample).

## Migration policy

Legacy → Temporal-Metadata-Enriched → `ASOF_VERIFIED`. A legacy dataset is **never** auto-marked
`ASOF_VERIFIED`; the DuckDB feature-store bridge tags rows `LEGACY_TEMPORAL_UNVERIFIED`.