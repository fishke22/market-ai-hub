# V2 Session / Factor-Representation Routing Contract

- **Schema**: `V2_SESSION_TRUTH_SCHEMA_VERSION = "2A.2"` +
  `V2_FACTOR_ROUTING_SCHEMA_VERSION = "2A.2"` (modules
  `src/market_ai_hub/research/v2/session_truth.py`,
  `src/market_ai_hub/research/v2/factor_representation.py`)
- **V2-A schema**: `V2_ASOF_SCHEMA_VERSION = "2A.2"`.
- Independent from `2B.1` / `2C.2` / `2D.4` / `2E.3` / `2F.3` / `2G.2` / `3A.2.3`.

## Core invariants (machine-enforced)

```
MARKET OPEN != FEED FRESH
CASH != FUTURES
CASH CLOSED != FACTOR UNAVAILABLE
FUTURES OPEN != LIVE DATA AVAILABLE
THEORETICAL SESSION OPEN != LIVE QUOTE
DERIVATIVE PROXY != DIRECT TARGET
PREVIOUS CLOSE != LIVE
DELAYED PROXY != LIVE
TRADING DATE != LOCAL CALENDAR DATE FOR NIGHT SESSIONS
SAME ECONOMIC FACTOR != SAME PRICE SERIES
```

## Venue registry

Explicit venue ids: `XTAI`, `XTKS`, `XNAS`, `XNYS`, `CBOE` (cash); `OSE_DERIVATIVES`,
`TAIFEX_DERIVATIVES`, `CME` (derivatives); `FX_OTC`, `CRYPTO_24_7` (OTC). Unknown venue →
`session_status=UNKNOWN` (fail closed). `calendar.exchange_for_symbol` has **no** "unknown → TWSE"
fallback; unknown/derivatives symbols raise `UnknownVenueError` from `trading_date_of` /
`exchange_timezone` instead of silently using the wrong venue.

## Session statuses

`REGULAR_SESSION / AFTER_HOURS_SESSION / NIGHT_SESSION / PRE_MARKET / POST_MARKET / MAINTENANCE /
CLOSED / HOLIDAY_CLOSED / UNKNOWN`. Only a real intraday session counts as `market_open` /
`tradable_now`. `MARKET OPEN` says nothing about data availability.

## Session rules

| venue | rule | trading-date assignment |
|---|---|---|
| XTAI / XTKS / XNAS / XNYS | verified `exchange_calendars` session open/close/break (no whole-day OPEN) | local cash session date (else next verified session) |
| OSE_DERIVATIVES | day 08:45–15:45 JST (sub-sessions DAY_REGULAR / DAY_CLOSING_AUCTION); night 17:00–06:00 JST | trading day begins with the night session → night belongs to the **next** OSE derivatives session (XTKS sessions + JPX holiday trading); night is not split at midnight |
| TAIFEX_DERIVATIVES | regular 08:45–13:45 Taipei; after-hours 15:00–05:00; expiring contract: regular ends 13:30 and no after-hours | after-hours belongs to the **next verified XTAI session** (Friday night uses the next session, never calendar+1) |
| CME | Globex Sun 17:00 → Fri 16:00 CT; daily maintenance 16:00–17:00 CT | local calendar date (holiday unverified) |
| FX_OTC | weekday UTC | UTC calendar date |
| CRYPTO_24_7 | always open | UTC calendar date |

`holiday_status ∈ {VERIFIED_CALENDAR, PARTIAL_HOLIDAY_TRADING, UNKNOWN}`;
`expiry_exception_status ∈ {NOT_APPLICABLE, APPLIED, UNKNOWN}` — never fabricated.
OSE night/daily bars are checked against `is_ose_derivatives_session` (XTKS cash OR JPX holiday
trading), so **XTKS cash closed ≠ OSE closed**.

## Factor representation contract

Two orthogonal axes, never merged:
- `representation_relation`: `DIRECT / CASH_REFERENCE / DERIVATIVE_PROXY / SPOT_PROXY /
  MACRO_CONTEXT / CONTEXT_ONLY`
- `temporal_role`: `LIVE / PREVIOUS_SESSION_REFERENCE / DELAYED_REFERENCE / STATIC_MACRO_CONTEXT /
  UNAVAILABLE` (reuses V2-A `CONTEXT_ROLE`)

`resolved_role ∈ {DIRECT_LIVE, LIVE_DERIVATIVE_PROXY, LIVE_SPOT_PROXY, PREVIOUS_SESSION_REFERENCE,
DELAYED_REFERENCE, STALE_REFERENCE, UNVERIFIED, NOT_AVAILABLE}` is derived deterministically:

```
LIVE + DIRECT                    -> DIRECT_LIVE
LIVE + DERIVATIVE_PROXY          -> LIVE_DERIVATIVE_PROXY
LIVE + SPOT_PROXY/CASH_REFERENCE -> LIVE_SPOT_PROXY
LIVE + MACRO_CONTEXT/CONTEXT_ONLY-> DELAYED_REFERENCE (context never a live target)
PREVIOUS_SESSION_REFERENCE       -> PREVIOUS_SESSION_REFERENCE
DELAYED_REFERENCE                -> DELAYED_REFERENCE
UNVERIFIED + STALE               -> STALE_REFERENCE
unavailable                      -> NOT_AVAILABLE
```

`timestamp_precision ∈ {TICK_TIMESTAMP, INTRADAY_TIMESTAMP, SESSION_CLOSE_TIMESTAMP,
SESSION_DATE_ONLY, PERIOD_DATE_ONLY, UNKNOWN}` — a `SESSION_DATE_ONLY`/`UNKNOWN` observation can
never be LIVE.

## LIVE eligibility (all required)

`session.tradable_now` · `availability_status=AVAILABLE` · known `event_timestamp` + `available_at`
· `available_at <= asof` · `staleness_status=FRESH` · live-grade timestamp precision
(`TICK_TIMESTAMP`/`INTRADAY_TIMESTAMP`) · live-capable provider/source frequency
(`TICK`/`1M`/`5M`/`15M`/`30M`/`60M`) · `data_grade ∈ {EXCHANGE_REALTIME, BROKER_REALTIME}` ·
sufficient session verification · for a FUTURE: `series_semantics=CONTRACT`, `roll_status=NONE`,
known `contract_code`. Missing any → not LIVE.

Daily yfinance observations (`source_frequency=DAILY`, `data_grade=RESEARCH_PROXY`,
`timestamp_precision=SESSION_DATE_ONLY`) therefore resolve to `PREVIOUS_SESSION_REFERENCE` /
`DELAYED_REFERENCE` even when the venue is open — never LIVE.

## Freshness vs session

Kept separate: an open session may have `staleness_status=STALE`; a closed market with a complete
prior close is `CLOSED_MARKET_REFERENCE` (→ `PREVIOUS_SESSION_REFERENCE`). A runtime fetch receipt
may be recorded as `received_at` with `availability_semantics=RUNTIME_RECEIPT_ONLY` and
`point_in_time_safe=False`; it is never promoted to historical `available_at` truth.

## Cross-representation return guard

`representation_return(previous, current)` returns a descriptive return **only** within the same
`representation_id`. Any representation change (cash close → futures current, futures → cash, cash →
another future) returns `None` + `BLOCKED_CROSS_REPRESENTATION_RETURN`. A continuous futures return
with unknown roll is returned but marked `UNVERIFIED_ROLL` (never a clean economic return).
No basis / cross-representation-gap model exists in 2A.2.

## Target rules

- `OSAKA_MICRO`: a fresh direct OSE Micro observation outranks the `^N225` cash proxy; `^N225` can
  never become the direct target. If no OSE Micro live feed exists, the OSE session may be
  `NIGHT_SESSION` while the OSE observation is `NOT_AVAILABLE`.
- `TAIWAN_INDEX`: `TAIEX_CASH` is a cash reference; `TX/MTX/TMF` are derivative representations. A
  futures price is never written as the TAIEX cash value.
- `TAIWAN_STOCK`: futures are context only, never a target substitution.
- The resolver returns **all** representations independently (no fusion); observations are sorted by
  resolved-role priority.

## Runtime integration

- `services/analysis.py::analyze_osaka_nikkei` `cross_market[symbol]` now carries `economic_factor_id`,
  `representation_id`, `instrument_type`, `representation_relation`, `temporal_role`, `resolved_role`,
  `venue_id`, `calendar_id`, `session_status`, `trading_date`, `event_timestamp`, `available_at`,
  `provider_timestamp`, `received_at`, `timestamp_precision`, `quote_age_seconds`, `staleness_status`,
  `availability_status`, `provider`, `data_grade`, `point_in_time_safe`, contract/roll fields,
  `return_status` — and keeps `last` / `return_1d` for backward compatibility.
- `services/market_session.py` (legacy `session_status` / `quote_freshness`) is backed by
  `session_truth`; `packet.market_session` / `packet.freshness` are populated from typed target
  session/reference truth (no fabricated live status).
- `targets/coverage.py` adds `SOURCE_VERIFIED / REFERENCE_AVAILABLE / LIVE_AVAILABLE`; a dated
  settlement/proxy is never labelled `LIVE_VERIFIED`, and the VIX coverage entry now names the actual
  runtime provider (yfinance ^VIX, PROXY) separately from the official Cboe release source.

## Limits (explicit)

- No new provider, no network fetch, no broker, no scheduler, no persistent DB (V2-H).
- No probability/calibration, no change-point, no trading signal.
- No V2-D `StateEvidence` / `StateSnapshot` / V2-G sequence is created from factor observations.
- Actual live readiness stays truthful: OSE Micro / TX / MTX / TMF / NQ / ES live = NOT_AVAILABLE.

`ROUTER PASS != LIVE FEED` · `SESSION OPEN != DATA AVAILABLE` ·
`FUTURES OPEN != FRESH FUTURES QUOTE` · `PROXY AVAILABLE != DIRECT TARGET AVAILABLE`.
