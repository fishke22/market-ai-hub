# PRE-V2H — V2-A.2 Session Truth + Factor Representation Routing Foundation — REPORT

- **Schemas**: `V2_ASOF_SCHEMA_VERSION = "2A.2"`, `V2_SESSION_TRUTH_SCHEMA_VERSION = "2A.2"`,
  `V2_FACTOR_ROUTING_SCHEMA_VERSION = "2A.2"`
- **Baseline**: main = `fdb18dea89d4a562b7af8fa6071c210c6e6e8273`, build_id `68a2f27efc35521a`.
- **Final build_id**: `8e36a4802965ef2d`.
- **Final tests**: `1534 passed, 20 deselected, 144 warnings`.

## A. Baseline
```
starting HEAD: fdb18dea89d4a562b7af8fa6071c210c6e6e8273
ending HEAD:   (see merge commit)
origin/main:   same (at start)
working tree:  clean (except the PRE-V2H audit report, kept and included in this PR)
Python:        3.12.13
starting build_id: 68a2f27efc35521a
ending build_id:   8e36a4802965ef2d
```

## B. Before audit (reference, unchanged)

`research/phase3/reports/PREV2H_SESSION_AWARE_MULTIFACTOR_ROUTING_AUDIT.md` (BEFORE evidence; historical
result not rewritten). Key BEFORE: `CURRENT_SESSION_AWARE_ROUTING=FAIL`,
`CURRENT_FACTOR_FRESHNESS_PROVENANCE=FAIL`, `CURRENT_TRADING_DAY_ASSIGNMENT=FAIL for derivatives`,
NQ=F/^VIX/^SOX/^TWII/TX = session UNKNOWN, cross_market had no timestamp/session/freshness.

## C. 2A.2 Session contract

```
venue registry:      XTAI/XTKS/XNAS/XNYS/CBOE (cash), OSE_DERIVATIVES/TAIFEX_DERIVATIVES/CME
                     (derivatives), FX_OTC/CRYPTO_24_7 (OTC); unknown venue -> UNKNOWN
cash sessions:       verified exchange_calendars open/close/break (NOT whole-day OPEN)
OSE:                 day 08:45-15:45 JST (DAY_REGULAR/DAY_CLOSING_AUCTION); night 17:00-06:00 JST
TAIFEX:              regular 08:45-13:45; after-hours 15:00-05:00; expiring contract regular ends
                     13:30, no after-hours
CME:                 Globex Sun 17:00 -> Fri 16:00 CT; maintenance 16:00-17:00 CT
trading date:        OSE night -> NEXT OSE derivatives session (XTKS + JPX holiday trading);
                     TAIFEX after-hours -> NEXT verified XTAI session; not split at midnight
holiday:             XTAI/XTKS VERIFIED_CALENDAR; OSE PARTIAL_HOLIDAY_TRADING; TAIFEX/CME UNKNOWN
expiry:              expiry_exception_status NOT_APPLICABLE/APPLIED/UNKNOWN (never fabricated)
unknown venue:       session_status=UNKNOWN (fail closed); no unknown->TWSE fallback
```

## D. Factor representation contract

```
economic factor:  JP_EQUITY / TW_INDEX / US_TECH_RISK / US_BROAD_RISK / US_VOLATILITY / JPY_FX /
                  US_RATES / GOLD / WTI_OIL / CRYPTO / USD_BROAD
representation:   NIKKEI225_CASH, OSE_MICRO_FUTURES, TAIEX_CASH, TX/MTX/TMF_FUTURES,
                  NASDAQ100_CASH, NQ/MNQ_FUTURES, TAIFEX_UNF, SOX_PROXY, SP500_CASH, ES_FUTURES,
                  VIX_CASH, USDJPY_SPOT, US10Y, US5Y, GOLD_FUTURES, WTI_FUTURES, BTC_SPOT, DXY_SPOT
relation:         DIRECT / CASH_REFERENCE / DERIVATIVE_PROXY / SPOT_PROXY / MACRO_CONTEXT / CONTEXT_ONLY
temporal role:    LIVE / PREVIOUS_SESSION_REFERENCE / DELAYED_REFERENCE / STATIC_MACRO_CONTEXT / UNAVAILABLE
resolved role:    DIRECT_LIVE / LIVE_DERIVATIVE_PROXY / LIVE_SPOT_PROXY / PREVIOUS_SESSION_REFERENCE /
                  DELAYED_REFERENCE / STALE_REFERENCE / UNVERIFIED / NOT_AVAILABLE
freshness:        session vs staleness separated; daily proxy never LIVE (full live gate)
availability:     AVAILABLE / NOT_AVAILABLE / UNKNOWN; open venue without data = NOT_AVAILABLE
provenance:       provider/source_type/source_frequency/data_grade/point_in_time_safe/revision_status
contract/roll:    contract_code/contract_month/roll_status/series_semantics/days_to_expiry
```

## E. Direct scenarios A–F (actual output)

```
A. Osaka night 2026-09-24 20:00 JST
   XTKS cash = CLOSED / td=2026-09-24
   OSE       = NIGHT_SESSION / td=2026-09-25
   OSE_MICRO_FUTURES observation = NOT_AVAILABLE (venue open, no data)

B. Osaka after midnight 2026-09-25 03:00 JST
   OSE = NIGHT_SESSION / td=2026-09-25   (same trading date as A)

C. Taiwan night 2026-09-24 20:00 Taipei
   XTAI cash = CLOSED / td=2026-09-24
   TAIFEX    = AFTER_HOURS_SESSION / td=2026-09-29 (next verified XTAI session)
   TAIEX_CASH obs = PREVIOUS_SESSION_REFERENCE
   TX/MTX/TMF observations = NOT_AVAILABLE

D. NQ: CME open (2026-09-24 07:00 CT), yfinance daily
   NQ_FUTURES = session REGULAR_SESSION / staleness STALE / PREVIOUS_SESSION_REFERENCE (not LIVE)

E. stale feed on open venue
   market_open=True / staleness=STALE / resolved=STALE_REFERENCE (not LIVE)

F. cross representation
   cash previous -> futures current = (None, BLOCKED_CROSS_REPRESENTATION_RETURN)
```

## F. Runtime cross_market

`analyze_osaka_nikkei().cross_market[symbol]` now carries: `economic_factor_id`, `representation_id`,
`instrument_type`, `representation_relation`, `temporal_role`, `resolved_role`, `venue_id`,
`calendar_id`, `session_status`, `trading_date`, `event_timestamp`, `available_at`,
`provider_timestamp`, `received_at`, `timestamp_precision`, `quote_age_seconds`, `staleness_status`,
`availability_status`, `provider`, `source_frequency`, `data_grade`, `point_in_time_safe`,
`revision_status`, contract/roll fields, `return_status`, `availability_semantics`
(`RUNTIME_RECEIPT_ONLY`, `point_in_time_safe=False`) — plus `last`/`return_1d` unchanged.

Example (offline builder): NQ=F → `representation_id=NQ_FUTURES`, `provider=yfinance`,
`data_grade=RESEARCH_PROXY`, `resolved_role=PREVIOUS_SESSION_REFERENCE` (never LIVE); ^VIX → `VIX_CASH`
PROXY; USDJPY=X → `USDJPY_SPOT`; ^N225 → `NIKKEI225_CASH`. No fake LIVE.

## G. Regime repair

```
risk regime:  BEFORE engine read panel["^VIX"] while builder column is "VIX" -> always insufficient
              AFTER  engine reads "VIX" -> consumes the fetched VIX (OK)
rates regime: BEFORE engine read US10Y/US2Y while panel only provides US10Y/US5Y -> always insufficient
              AFTER  engine reads US10Y/US5Y -> OK; metadata curve="10Y-5Y" (no fabricated US2Y)
```

## H. Actual live readiness (truthful, per actual source)

```
OSE Micro : NOT_AVAILABLE (JPX daily settlement only)   TX : NOT_AVAILABLE
MTX       : NOT_AVAILABLE                                TMF: NOT_AVAILABLE
NQ        : NOT_AVAILABLE (yfinance daily research proxy only)
ES        : NOT_AVAILABLE (yfinance daily research proxy only)
VIX       : NOT_AVAILABLE live (yfinance ^VIX daily PROXY; Cboe official release = SOURCE_VERIFIED)
SOX       : NOT_AVAILABLE live (yfinance daily PROXY)
USDJPY    : NOT_AVAILABLE live (yfinance daily PROXY)
```

## I. Changed files

```
ADD src/market_ai_hub/research/v2/session_truth.py        (venue/session/trading-day truth)
ADD src/market_ai_hub/research/v2/factor_representation.py(typed factor representation + routing)
ADD tests/test_v2a2_session_truth.py                      (28 tests)
ADD tests/test_v2a2_factor_routing.py                     (32 tests)
ADD docs/architecture/v2-session-factor-routing-contract.md
ADD research/phase3/reports/PREV2H_V2A2_SESSION_FACTOR_ROUTING_FOUNDATION_REPORT.md
ADD research/phase3/reports/PREV2H_SESSION_AWARE_MULTIFACTOR_ROUTING_AUDIT.md (BEFORE audit, kept)
MOD src/market_ai_hub/research/v2/asof.py                 (V2_ASOF_SCHEMA_VERSION 2A.1 -> 2A.2)
MOD src/market_ai_hub/services/calendar.py                (explicit venue mapping, no TWSE fallback,
                                                           OSE session helpers, UNVERIFIED anchor branch)
MOD src/market_ai_hub/services/market_session.py          (backed by session_truth)
MOD src/market_ai_hub/services/analysis.py                (cross_market typed entries)
MOD src/market_ai_hub/regime/engine.py                    (VIX column + US10Y/US5Y curve)
MOD src/market_ai_hub/packet/builder.py                   (market_session/freshness truth, coverage labels)
MOD src/market_ai_hub/mcp/server.py                       (get_data_coverage labels/source)
MOD src/market_ai_hub/targets/coverage.py                 (SOURCE_VERIFIED/REFERENCE_AVAILABLE/LIVE_AVAILABLE)
MOD tests/test_market_session.py / test_phase2h.py / test_v2a_asof.py / test_v2b_gap_session.py /
    test_v2c_daily_labels.py                              (corrected expectations)
MOD tests/test_challengers_2d1.py / test_research.py / test_tournament.py (build_id)
MOD docs/architecture/v2-asof-data-contract.md
MOD docs/development/project-status.md
```

## J. Tests (new)

Session truth (28): source mapping/no-TWSE-fallback/unknown venue; OSE day/night/gap/after-close;
OSE night trading-date (20:00 / 03:00 same date, no midnight split); OSE holiday trading != XTKS cash;
TAIFEX regular/after-hours/next-XTAI/friday-night/expiry 13:30/no-after-hours/unknown-expiry;
CME globex/maintenance/weekend/unverified-holiday; XTKS intraday truth; XTAI vs TAIFEX after-hours.
Factor routing (32): open-venue-no-data not live; fresh-on-closed-cash not live; stale-on-open not live;
daily NQ not live; synthetic fresh NQ → LIVE_DERIVATIVE_PROXY; previous close stays reference; cash &
futures independent; Osaka direct outranks cash proxy; TAIFEX futures never overwrite TAIEX;
same/cross/cash-futures/futures-cash returns; continuous unknown-roll UNVERIFIED; cross_market fields
(8); packet session/freshness/stale-settlement/VIX-source; regime VIX + 10Y-5Y repairs.

## K. Regression

```
focused (session_truth + factor_routing): 60 passed, exit 0
V2-A (asof + 2A.2): 88 passed, exit 0
V2-A..G: 573 passed, exit 0
runtime/packet/regime/calendar/session/coverage: 149 passed, 5 deselected, 33 warnings, exit 0
Phase3A: 121 passed, exit 0
warning strict (-W error): 60 passed, exit 0
full suite: 1534 passed, 20 deselected, 144 warnings, exit 0
```

## L. V2-H readiness

```
factor representation schema stable: YES (2A.2)
session fields available:            YES (VenueSessionContext + session_status/trading_date/session_id)
freshness fields available:          YES (event_timestamp/available_at/provider_timestamp/received_at/
                                          timestamp_precision/quote_age_seconds/staleness_status)
roll fields available:               YES (contract_code/contract_month/roll_status/series_semantics/
                                          days_to_expiry)
V2H_UPSTREAM_FACTOR_LINEAGE_READY:   YES
```

## M. Safety

```
new live provider: NO · data download/backfill: NO · broker: NO · order: NO · model training: NO
calibration: NO · probability fitting: NO · trading signal: NO · persistent audit DB: NO
V2-H implementation: NO · network fetch during construction/tests: NO
```

## N. Gate

**PREV2H_V2A2_SESSION_FACTOR_ROUTING_FOUNDATION_PASS** + **V2H_UPSTREAM_FACTOR_LINEAGE_READY**
ROUTER PASS != LIVE FEED · SESSION OPEN != DATA AVAILABLE · FUTURES OPEN != FRESH FUTURES QUOTE ·
PROXY AVAILABLE != DIRECT TARGET AVAILABLE.

STOPPED AFTER V2-A.2 SESSION / FACTOR-REPRESENTATION ROUTING FOUNDATION.
V2-H NOT STARTED.
