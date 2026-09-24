# PRE-V2H — Session-Aware Multi-Factor / Spot-Futures Routing Audit

**READ-ONLY AUDIT + DESIGN ONLY. No runtime source modified. No schema bump. No build-id change.
No data download. No provider added. No broker. No scheduler. V2-H NOT STARTED.**

- Audit date: 2026-09-24
- Repo: `D:\MARKET_AI_HUB`

## A. Baseline

```
branch:        main
HEAD:          fdb18dea89d4a562b7af8fa6071c210c6e6e8273
origin/main:   fdb18dea89d4a562b7af8fa6071c210c6e6e8273
working tree:  clean (before report file)
Python:        3.12.13
build_id:      68a2f27efc35521a
V2-G schema:   2G.2
```

## B. V2-G 2G.2 verification (read-only rerun)

```
tests/test_v2g_sequential_update.py: 102 passed (exit 0)
full suite: 1474 passed, 20 deselected, 144 warnings (exit 0)
```

## C. Current factor source matrix

Runtime paths that currently form "multi-factor / cross-market / macro":

1. `services/analysis.py::analyze_osaka_nikkei` → `cross_market = {sym: {last, return_1d}}` over **all enabled
   yfinance symbols** (`config/symbols.yaml`). **No timestamp, no session, no freshness in the output.**
2. `packet/builder.py::_regime_panel` → daily closes for `^VIX/^TNX/^FVX/USDJPY=X` + local `^N225` (Osaka) /
   `^TWII` (Taiwan) → `regime` labels (via `regime/engine.py`).
3. `research/v2/asof.py` → machine-readable `_CAPABILITY_REGISTRY` (2A.1) per factor.
4. Feature store (`data/feature_store/features.duckdb`): **only `^N225` close**, 547 rows, 2025-09-17 → 2026-06-30.
5. `targets/coverage.py` + `packet/builder.py` factor-status lists (LIVE_VERIFIED/MISSING/PROXY_ONLY/NOT_IMPLEMENTED).

| economic factor | symbol queried | venue | instrument type | provider | method | managed dataset | runtime fetch | cache | event ts | available_at | provider ts | last observed local ts | quote age | PIT safe | revision | capability status |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Japan equity cash | `^N225` | TSE (XTKS) | CASH_INDEX | yfinance | daily bars `1d`, `auto_adjust=False` | feat.store close-only (to 2026-06-30) | yes | process cache (TTL) | bar date | no | no | 2026-06-30 (store) | day-level | false | VINTAGE_NOT_AVAILABLE | AVAILABLE(daily) / role PROXY |
| OSE Micro direct | `NK225MC` | OSE | FUTURE | JPX settlement parquet | official daily settlement | `data/raw/jpx/settlement/.../rb20260918.parquet` | read parquet | process cache | settlement date | no | no | **2026-09-18** | day-level | false | VINTAGE_NOT_AVAILABLE | settlement only; OHLC missing |
| OSE Micro continuous bar | (225LABO) | OSE | FUTURE (CONTINUOUS) | 225LABO local zip → parquet | daily bar (exchange day) | `data/normalized/ose_micro/ose_micro_daily_bar_v1.parquet` (960 rows, to 2026-09-01) | read parquet | none | trading_date only | no | no | 2026-09-01 | day-level | **false (LEGACY)** | — | LOCAL_ONLY; roll/session provenance UNKNOWN |
| TAIEX cash | `^TWII` | TWSE (XTAI) | CASH_INDEX | yfinance | daily bars | none local managed | yes (packet index proxy) | process cache | bar date | no | no | last fetch | day-level | false | VINTAGE_NOT_AVAILABLE | AVAILABLE(daily); packet PROXY_ONLY |
| TX | `TX` | TAIFEX | FUTURE | `TaifexProvider` | daily / time&sales | none | **NOT used at runtime** | — | date | no | no | n/a | n/a | false | — | registered; packet NOT_IMPLEMENTED |
| MTX | `MTX` | TAIFEX | FUTURE | `TaifexProvider` | same | none | **NOT used** | — | — | — | — | — | n/a | false | — | NOT_IMPLEMENTED |
| TMF | `TMF` | TAIFEX | FUTURE | `TaifexProvider` | same | none | **NOT used** | — | — | — | — | — | n/a | false | — | NOT_IMPLEMENTED |
| Nasdaq-100 cash | — | — | CASH_INDEX | — | — | none | **no representation** | — | — | — | — | — | — | — | — | (absent) |
| NQ | `NQ=F` | CME | FUTURE (proxy) | yfinance | daily bars | none | yes | process cache | bar date | no | no | last fetch | day-level | false | — | **V2 registry: NQ NOT_AVAILABLE** |
| ES | `ES=F` | CME | FUTURE (proxy) | yfinance | daily bars | none | yes | process cache | bar date | no | no | last fetch | day-level | false | — | ES NOT_AVAILABLE |
| SOX | `^SOX` | Nasdaq/NYSE | CASH_INDEX | yfinance | daily bars | none | yes | — | bar date | no | no | last fetch | day-level | false | — | SOX NOT_AVAILABLE |
| VIX | `^VIX` | Cboe | CASH_INDEX (vol) | yfinance | daily bars | none | yes | — | bar date | no | no | last fetch | day-level | false | — | VIX NOT_AVAILABLE (V2) / coverage claims Cboe LIVE_VERIFIED |
| USDJPY | `USDJPY=X` | FX (OTC) | FX | yfinance | daily bars | none | yes | — | bar date | no | no | last fetch | day-level | false | — | USDJPY NOT_AVAILABLE |
| US Treasury yields | `US2Y..US30Y` / `^TNX,^FVX` | US Treasury | YIELD | ustreasury CSV / yfinance | daily CSV / daily bars | daily cache (PIT=false) | yes | process cache | date / bar date | no | no | last fetch | day-level | false | VINTAGE_NOT_AVAILABLE | AVAILABLE(daily), PIT=false |
| FRED macro | series `DGS2/DGS10/FEDFUNDS` | FRED | MACRO | `fred.py` | REST periodic | no vintage | on demand | — | date | no | no | last fetch | n/a | false | **REVISION_RISK_PRESENT** | AVAILABLE(periodic) |

Note: `symbols.yaml` marks every yfinance entry `realtime_grade: DELAYED`, `data_grade: RESEARCH_PROXY`.
"Code supports a symbol" ≠ "factor data available" (V2 registry says NQ/ES/USDJPY/SOX/VIX NOT_AVAILABLE yet
the V1 yfinance path returns daily proxies).

## D. Current session model — `INSUFFICIENT_SESSION_MODEL`

Implemented: **day-level only**.
- `services/market_session.py::session_status` → `OPEN / CLOSED / UNKNOWN` only; `asset_class` maps
  `^N225`→index, `USDJPY=X`/`JPY=X`→fx, `BTC-USD`→crypto, else `proxy`.
- `services/calendar.py` → `exchange_calendars` XTAI / XTKS day-level `is_session`, `trading_date_of`,
  `next_trading_sessions`, `next_ose_derivatives_sessions` (XTKS sessions + JPX holiday-trading dates).
- `research/v2/asof.py::MarketSessionContext` has `session_type ∈ {DAY,NIGHT,OVERNIGHT,HOLIDAY_DAY,
  HOLIDAY_NIGHT,UNKNOWN}`, but only `DAY`/`HOLIDAY_DAY` are ever produced (grep: sole assignment at
  `ose_holiday_session_context`).

Absent: intraday regular/after-hours/night hours, maintenance break, expiry-day exception, per-venue
session registry. Grep for `08:45|13:45|15:00|15:45|17:00|06:00|09:30|16:00|18:00|maintenance|prepost|
night_session|after_hours` in `src/` → **no session-hour constants**.

Live demonstration (read-only, no network; `session_status`):
```
Thu 2026-09-24 11:00 JST (TSE day)      ^N225=OPEN   ^TWII=UNKNOWN  NQ=F=UNKNOWN  TX=UNKNOWN
Thu 2026-09-24 20:00 JST (OSE night)    ^N225=OPEN   ^TWII=UNKNOWN  NQ=F=UNKNOWN  TX=UNKNOWN
Thu 2026-09-24 20:00 Taipei (TAIFEX AH) ^N225=OPEN   ^TWII=UNKNOWN  NQ=F=UNKNOWN  TX=UNKNOWN
Thu 2026-09-24 11:00 NY (US regular)    ^N225=OPEN   ^TWII=UNKNOWN  NQ=F=UNKNOWN  TX=UNKNOWN
```
`^N225` reports OPEN for the whole local calendar day of any XTKS session (no intraday hours); 11/13 other
factors report `UNKNOWN`.

Session-classification audit (per required question):

| factor | venue TZ known | market-open known | regular/night/AH | trading-day attribution | maintenance | holiday | expiry exception |
|---|---|---|---|---|---|---|---|
| `^N225` | YES (Asia/Tokyo) | PARTIAL (day-level) | NO | PARTIAL (day-level cash date) | NO | YES (XTKS) | NO |
| `NK225MC` (settlement) | YES (Asia/Tokyo) | NO (settlement only) | NO | NO (date = settlement date) | NO | PARTIAL | NO |
| 225LABO continuous | YES (manifest) | NO | NO | NO in runtime (upstream manifest rule) | NO | NO | NO |
| `^TWII` | YES (Asia/Taipei) | NO (UNKNOWN) | NO | PARTIAL (XTAI day-level) | NO | YES (XTAI) | NO |
| `TX/MTX/TMF` | NO at runtime | NO (UNKNOWN) | NO | NO | NO | NO | NO |
| `NQ=F`/`ES=F` | NO at runtime (UNKNOWN) | NO | NO | NO | NO | NO | NO |
| `^VIX/^SOX/^TNX/^FVX` | NO at runtime (UNKNOWN) | NO | NO | NO | NO | NO | NO |
| `USDJPY=X` | PARTIAL (UTC) | PARTIAL (weekday only) | NO | NO | NO | NO | NO |
| `BTC-USD` | — | YES (always) | n/a | n/a | n/a | n/a | n/a |
| USTREASURY / FRED | — | n/a (daily/periodic) | n/a | NO | n/a | n/a | n/a |

Latent venue-mapping defect (actual code): `calendar.exchange_for_symbol()` returns `"TWSE"` for every
symbol except `^N225`. So `exchange_for_symbol("NQ=F") == "TWSE"`, `exchange_for_symbol("TX") == "TWSE"`.
Currently not reached for those symbols (asset_class → `proxy` → UNKNOWN), but it is a live landmine.

## E. Current freshness model

- `services/market_session.py::quote_freshness` correctly **separates** `session_status` from
  `freshness_status` (LIVE/RECENT/STALE/HISTORICAL) and computes `quote_age_seconds` / `quote_live` /
  `usable_for_live_decision`. **But it is only used by `models/chronos_model.py` and
  `models/timesfm_model.py`** — NOT by the cross-market/regime path.
- Cross-market output (`analysis.cross_market`) carries **no timestamp at all** → a consumer cannot compute
  quote age or distinguish "market closed" from "feed stale".
- yfinance provider exposes no `provider_timestamp`/`received_at`/delay; `data_grade` is hardcoded
  `RESEARCH_PROXY`.
- Feature store has `event_time`/`available_at` (equal for `^N225`; last 2026-06-30).
- `packet.schema` declares `market_session` and `freshness` fields — **never populated** (dead fields).

## F. Taiwan cash/futures behavior

Actual code: TAIEX is served by **`^TWII` yfinance daily proxy** (`_index_proxy_reference`, `packet.target_price_source="proxy_index"`,
`reference_price_type=PROXY`). `TX/MTX/TMF` have a provider class but **no runtime data path**; the packet
factor list states `{"factor": "TAIFEX TX/MTX/TMF", "status": "NOT_IMPLEMENTED"}`. `primary_targets.yaml`
declares TAIFEX futures as `execution_instrument` with `data_semantics` warnings.

Answer for "TAIEX cash closed, TX/MTX/TMF after-hours open": **A. uses cash last close** — and it has no
futures representation to switch to. There is **no** cash→futures substitution (safe by absence, not by
contract). `packet` keeps TAIEX as `forecast/reference` and lists `execution_instruments: [TX, MTX, TMF]`.

## G. Osaka cash/futures behavior

Direct target `OSE_NIKKEI225_MICRO_FUTURES` is separated from `^N225`:
- packet reference = JPX micro **settlement** (`PRICE_TYPE_SETTLEMENT`, `contract`, `FRONT_NEAREST_LISTED`,
  `available_contracts`) else `^N225` proxy (`PRICE_TYPE_PROXY`).
- `packet.target_semantics` separates `direct_target` / `continuous_research_series` / `proxy_model_target`;
  `direct_next_session` uses `next_ose_derivatives_sessions`.
- 225LABO continuous bars feed V2 research only; `daily_adapter` blocks futures labels
  (`BLOCKED_ROLL_PROVENANCE`, `BLOCKED_CALENDAR_PROVENANCE`, `BLOCKED_TEMPORAL_SESSION_BOUNDARY`).

Answer for "Nikkei cash closed, OSE micro night open": the system uses the **last daily settlement /
`^N225` daily close**; no night-session branch exists, and `session_status("^N225")` would report OPEN for
the whole local day. `^N225` never overwrites the direct target identity (packet keeps them separate).

## H. Nasdaq cash / NQ behavior

NQ factor = `NQ=F` yfinance **daily proxy** (`regime` global). There is **no NASDAQ100 cash
representation**, and V2 capability registry marks `NQ` `NOT_AVAILABLE`. `session_status("NQ=F")=UNKNOWN`.
Answer for "Nasdaq cash closed, CME NQ open": the system would use the **last `NQ=F` daily bar** with no
session/freshness truth; NQ live = **NOT_AVAILABLE** (no managed feed). CME being theoretically open does
not confer data availability.

## I. Trading-day assignment

- `calendar.trading_date_of` = exchange-local calendar date. Correct for TSE/TWSE **cash day** sessions.
- Night sessions: **not implemented**. Live check: `trading_date_of(2026-09-24 20:00 JST, "^N225")`
  → `2026-09-24`, but an OSE derivatives night bar at 20:00 JST belongs to the **next** trading day
  (per OSE "trading day begins with night session"; the local 225LABO manifest rule is
  `time >= 16:30 JST -> next trading date`). At `2026-09-25 03:00 JST` it returns `2026-09-25`, so a single
  night session is **split across two trading dates** if this helper is applied to derivatives.
- TAIFEX after-hours "belongs to next regular session" rule: **not implemented**.
- Current runtime does not apply `trading_date_of` to derivatives (it derives OSE dates from the proxy
  date + holiday-trading list), so the defect is latent, not active — but it blocks any future router.

## J. Cross-representation return audit

- `analysis.cross_market`: `return_1d = series.pct_change().iloc[-1]` — **close-to-close within one
  symbol's own series**. No open-to-current, no session-open anchoring, no previous-close-to-current
  variant, no night-session-open anchoring.
- `regime/engine.py`: within-series rolling stats only (`^N225` MA/vol, `^VIX` level, `USDJPY=X` 20-bar
  return, US10Y–US5Y/level).
- **No cash/futures stitching currently occurs** (each representation is fetched and computed
  independently), so there is no active `CRITICAL_SEMANTIC_RISK` today. However there is **no contract**
  preventing it: nothing today would block a future router from chaining a cash close into a futures
  price. `BLOCKED_CROSS_REPRESENTATION_RETURN` is therefore a required new guard.

Concrete `regime` defects found (read-only synthetic panel, actual column names):
```
risk_regime   label=insufficient  (engine reads panel["^VIX"], builder maps "^VIX" -> column "VIX")
rates_regime  label=insufficient  (engine reads panel["US2Y"], panel only provides US10Y/US5Y)
```
So the fetched VIX factor is effectively dropped and the rates regime is permanently insufficient.

## K. Current runtime failure modes

1. Cross-market factor rows have **no timestamp/session/freshness** → stale daily close cannot be
   distinguished from fresh; "market closed" cannot be distinguished from "feed stale". (HIGH)
2. `session_status` returns `UNKNOWN` for 11/13 factor symbols; `^N225` is day-level-only and reports
   OPEN outside cash hours (night/pre-market/after-hours). (HIGH)
3. Night-session trading-date rule missing → applying `trading_date_of` to derivatives splits a session
   across two dates. (HIGH, latent)
4. Venue-mapping fallback (`exchange_for_symbol` → TWSE) for CME/TAIFEX symbols. (MEDIUM, latent)
5. `LIVE_VERIFIED` label applied to a 4-day-old JPX daily settlement and to "VIX Cboe official" while the
   runtime VIX factor is yfinance RESEARCH_PROXY — label/source ambiguity. (MEDIUM)
6. `regime.risk_regime`/`rates_regime` always `insufficient` due to column-name mismatch / missing column.
   (MEDIUM)
7. `packet.market_session` / `packet.freshness` declared but never populated. (LOW)
8. `get_market_data` accepts an arbitrary caller `interval` with no allowlist and no `prepost`/session
   handling. (MEDIUM)
9. 225LABO manifest `session_semantics` ("night 16:30-06:00 + day 08:45-15:15") disagrees with current OSE
   hours (night 17:00-06:00, day 08:45-15:45). (LOW, doc/provenance)
10. No `available_at`/provider timestamp anywhere in the factor path → point-in-time joins for factors
    cannot be validated. (HIGH)

Severity: none reach `CRITICAL` today (no stitching, no future leakage found in the factor path);
the schedule above is the honest current state.

## L. Proposed session-aware factor routing contract (design only, NOT implemented)

```
resolve_factor_representation(economic_factor, asof_timestamp, target_context) ->
    list[FactorRepresentation]   # never a single price; representations are independent

FactorRepresentation:
    economic_factor_id      e.g. US_TECH_RISK, JP_EQUITY, TW_INDEX
    representation_id       e.g. NASDAQ100_CASH, NQ_FUTURES, MNQ_FUTURES, TAIEX_CASH, TX_FUTURES,
                                 NIKKEI225_CASH, OSE_MICRO_FUTURES, TAIEX_UNF
    instrument_type         CASH_INDEX | EQUITY | FUTURE | FX | YIELD | MACRO | OTHER
    venue / calendar_id / timezone
    session_status          (see §M)
    role                    (see §M)
    event_timestamp / available_at / provider_timestamp / received_at
    quote_age_seconds / freshness_status (see §M)
    contract_code / contract_month / roll_status / series_semantics / days_to_expiry
    provenance              provider, source_method, data_grade, revision_status
    availability_status      AVAILABLE | NOT_AVAILABLE | UNKNOWN
```

Correct priority semantics (replaces "pick a price"):
1. canonical **direct** representation trading + fresh → `DIRECT_LIVE`.
2. cash representation closed, official **futures** representation trading + fresh → `LIVE_DERIVATIVE_PROXY`
   (never labelled `DIRECT_LIVE`).
3. cash last close retained as `PREVIOUS_SESSION_REFERENCE`; **not overwritten** by futures.
4. cash and futures both trading → keep both; **no automatic fusion**.
5. market theoretically open but feed stale → **never LIVE** (`DELAYED`/`STALE`).
6. all live representations unavailable → `PREVIOUS_SESSION_REFERENCE` (explicitly labelled) or
   `NOT_AVAILABLE`.

Target rules:
- `OSAKA_MICRO`: direct OSE Micro live (if trading+fresh) outranks `^N225`; `^N225` can never overwrite the
  direct target identity.
- `TAIWAN_INDEX`: TAIEX cash = reference target; TX/MTX/TMF = derivative representations; a futures price
  must never be written as the TAIEX cash value.
- `TAIWAN_STOCK`: single-stock cash ≠ index futures; futures may be context only, never target substitution.
- `US_TECH_RISK`: `NASDAQ100_CASH` / `NQ_FUTURES` / `MNQ_FUTURES` / `TAIFEX_UNF` are **independent**
  representations. In the Asian session: cash = closed/previous-session reference; NQ = potentially
  `LIVE_DERIVATIVE_PROXY` **only if the NQ feed is actually fresh and timestamp-verifiable**; with no
  managed NQ feed, `NQ live = NOT_AVAILABLE` (CME being open ≠ we have data).

No-cross-representation arithmetic: a cash close chained to a futures price must be blocked
(`BLOCKED_CROSS_REPRESENTATION_RETURN`) unless a typed `cross_representation_gap/basis` calculation exists.

## M. Proposed fields / enums (design only)

- Factor roles: `DIRECT_LIVE`, `LIVE_DERIVATIVE_PROXY`, `LIVE_SPOT_PROXY`, `PREVIOUS_SESSION_REFERENCE`,
  `STALE_REFERENCE`, `UNVERIFIED`, `NOT_AVAILABLE` (note `LIVE_DERIVATIVE_PROXY != DIRECT_LIVE`).
- Session statuses (per-venue naming, not globally shared): `REGULAR_SESSION`, `AFTER_HOURS_SESSION`,
  `NIGHT_SESSION`, `PRE_MARKET`, `POST_MARKET`, `MAINTENANCE`, `CLOSED`, `HOLIDAY_CLOSED`, `UNKNOWN`.
- Freshness fields: `event_timestamp`, `available_at`, `provider_timestamp`, `received_at`,
  `quote_age_seconds`, `freshness_status ∈ {FRESH, DELAYED, STALE, UNKNOWN}`; keep **market-closed** and
  **feed-stale** as separate axes.
- Contract/roll fields: `contract_code`, `contract_month`, `roll_status`, `series_semantics`,
  `front_contract?`, `continuous_contract?`, `days_to_expiry` — so `NQ continuous` / `front-month` /
  `expired` never collapse into one factor without provenance.

Reuse (do not reinvent): `research/v2/asof.py` already has `STALENESS_STATUS`, `CONTEXT_ROLE`,
`SESSION_TYPES`, `REVISION_STATUS`, `MarketSessionContext`, `TemporalContext`, `staleness_for`,
`context_role_for`, `EXCHANGE_TIMEZONES`, `DATA_CAPABILITY_REGISTRY`. What is missing is a **venue/session
registry with intraday hours + maintenance/holiday/expiry** and the **representation router** itself.

## N. Architecture placement recommendation

Recommendation: **D. combination — (A) extend V2-A As-Of / Session Truth + (C) new dedicated
Factor-Representation Routing contract**, not V2-F.

Reasons:
- V2-A already owns time identity, staleness/role vocabulary, exchange timezones, and the capability
  registry — the session/venue truth belongs there (extend `MarketSessionContext` + add a venue session
  registry with intraday hours, maintenance, holiday/expiry rules).
- Factor representation routing (economic_factor → representations → role/freshness) is a distinct concern
  from V2-F catalyst response; it should be its own typed contract that V2-H can persist.
- V2-F must stay unchanged (catalyst association ≠ factor routing).
- Not chosen in this round: no code written, per §24.

## O. V2-H gate

```
V2H_CAN_START_WITH_CURRENT_FACTOR_CONTRACT: NO
```

Because the missing session/freshness/representation fields would change the audit-DB lineage schema:
factor representation fields, session fields, freshness fields, and contract/roll fields do not exist on
the factor path today. Starting V2-H now would persist incomplete factor lineage and require a schema
migration later.

Required prior step: a **V2-A extension** delivering (1) per-venue session truth (intraday hours,
maintenance, holiday, expiry, night-session trading-day attribution) and (2) the typed
factor-representation + freshness contract; then V2-H can encode it directly.

## P. Safety

```
runtime source modification: NO
schema bump: NO
build-id update: NO
new provider: NO
data download: NO
broker: NO
scheduler: NO
network fetch during audit: NO (code inspection + read-only local parquet/duckdb + local function calls)
persistent DB write: NO
V2-H: NOT STARTED
```

Report file created this round (not committed): `research/phase3/reports/PREV2H_SESSION_AWARE_MULTIFACTOR_ROUTING_AUDIT.md`

STOPPED AFTER PRE-V2H SESSION-AWARE MULTI-FACTOR ROUTING AUDIT.
NO RUNTIME IMPLEMENTATION PERFORMED.
V2-H NOT STARTED.
