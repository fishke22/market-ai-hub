# TEMPORAL / AS-OF AUDIT (V2)

## Current timestamp handling (verified)

- `data/timezones.py`: storage = UTC; naive datetime **rejected** (`ensure_utc` raises); display
  zones Taipei/Tokyo/New_York via `pytz`.
- Feature store columns: `event_time`, `available_at` (scaffold), plus `feature_version`.
- `services/market_session.py`: `quote_freshness`, session helpers.
- `services/calendar.py`: `trading_date_of`, `sanitize_daily_exchange_sessions`.

## Gaps

1. **No canonical timestamp taxonomy.** Only a single `timestamp_utc` on bars + `event_time`/
   `available_at` on the feature store. The following are **not** distinguished:
   `event_timestamp, observed_at, source_timestamp, ingested_at, feature_cutoff_timestamp,
   forecast_origin`.
2. **No as-of loader.** There is no point-in-time join that replays the feature store at an
   arbitrary historical timestamp.
3. **No revision-aware macro data.** FRED/macro revisions are not versioned.
4. **Overnight / holiday date attribution** is handled only for the daily bar (trading_date),
   not generalized to intraday session dates.

## Canonical recommendation (design)

| Field | Meaning |
|---|---|
| `event_timestamp` | the market event time (exchange-local, tz-aware) |
| `observed_at` | when the system first saw it |
| `source_timestamp` | the source's own timestamp |
| `ingested_at` | when it entered the lake |
| `feature_cutoff_timestamp` | the as-of bound for all features feeding a forecast |
| `forecast_origin` | the timestamp the forecast is anchored to |

## Data staleness contract (per external factor)

| Factor | Frequency | Update lag | Market-open overlap | Stale risk |
|---|---|---|---|---|
| SOX | daily close | ~1 day | US close (post-Asia) | HIGH — "yesterday SOX close ≠ live SOX signal" |
| VIX | daily | ~1 day | US | HIGH |
| US yields | daily | ~1 day | US | HIGH |
| FRED | periodic | days-weeks | n/a | HIGH (revision-aware needed) |
| WTI/Brent | daily | ~1 day | global | MEDIUM |
| Nasdaq futures | intraday (if sourced) | near-realtime | overlaps Osaka night | depends on source |
| USDJPY | 24×5 | near-realtime | overlaps Osaka | LOW if FX source live |

Rule: never treat a prior-day US close as a current intraday signal; tag `cash_reference_status`.

## Holiday / thin-liquidity (design)

Japan Cash Holiday / US Holiday / Half Day / Low Volume / Thin Liquidity. When TSE cash is closed
but OSE futures are open (holiday trading), set `cash_reference_status=STALE|CLOSED` and
`basis_comparability=DEGRADED|NOT_COMPARABLE`; do not use a normal futures-cash basis.
