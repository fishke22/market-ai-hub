# PHASE V2-A — As-Of / Timestamp / Data Truth — REPORT

- **Schema**: `V2_ASOF_SCHEMA_VERSION = "2A.1"` (module `src/market_ai_hub/research/v2/asof.py`)
- **Baseline main**: `1ba46e9fa23478ec622395274c50d9d283a30141`
- **Runtime build_id (new)**: `94b5c1a8a55becfb` (was `c7417f7c4cbfb388`)
- **Tests**: `989 passed, 20 deselected` (was `961`; +28 V2-A)
- **Focused V2-A**: 28 passed

## Answers

### 1. actual starting main 是否等於 reported baseline？
YES. `1ba46e9fa23478ec622395274c50d9d283a30141` == reported, working tree clean, build_id matched.

### 2. V2 canonical time fields 有哪些？
`event_timestamp, source_timestamp, observed_at, ingested_at, feature_cutoff_timestamp,
forecast_origin, trading_date, session_date, exchange_timezone, source_timezone,
canonical_timezone, session_id, calendar_id, market_open_status, source_frequency,
data_latency_seconds, data_staleness_seconds` (in `TemporalContext`).

### 3. event_timestamp 與 observed_at 有何不同？
`event_timestamp` = actual market event time; `observed_at` = when the system first saw it.
Point-in-time truth is gated on `observed_at` — an early event observed late is unusable.

### 4. forecast_origin 如何防 future leakage？
`TemporalContext.validate_ordering()` enforces `feature_cutoff_timestamp <= forecast_origin`;
`reject_future_information()` blocks any observation with `observed_at` / `event_timestamp` /
`release_timestamp` after the cutoff; `get_asof()` / `point_in_time_join()` only return
observations available at or before the cutoff.

### 5. macro release 如何防 look-ahead？
`ReleaseTimeContext` + `macro_asof_safe()`: a release after the cutoff → `FAIL_RELEASE_AFTER_CUTOFF`;
without ALFRED/vintage the historical value is `REVISION_RISK_PRESENT` (never treated as fresh).

### 6. legacy datasets 是否全部 ASOF_VERIFIED？
NO. The DuckDB feature-store bridge tags rows `LEGACY_TEMPORAL_UNVERIFIED`; nothing is auto-marked
`ASOF_VERIFIED`.

### 7. 目前哪些 dataset 可以標 ASOF_VERIFIED？
None yet. Current on-disk data is daily, single-series, without full as-of/snapshot/vintage
metadata; all remain `LEGACY_TEMPORAL_UNVERIFIED` until a migration verifies each.

### 8. OSE Direct / ^N225 Proxy calendar 是否仍分離？
YES. `TARGET_SEMANTICS["OSAKA_MICRO"].calendar == OSE_DERIVATIVES (DIRECT)`; `^N225` = `XTKS (PROXY)`.

### 9. Japan cash holiday + OSE holiday trading 是否能 machine represent？
YES. `MarketSessionContext` + `ose_holiday_session_context()` represent
`cash_market_open=False, derivatives_market_open=True, is_holiday_trading=True, session_type=HOLIDAY_DAY`.

### 10. stale data 是否還會假裝 fresh？
NO. `staleness_for()` returns `CLOSED_MARKET_REFERENCE` when market closed; `context_role_for()`
returns `PREVIOUS_SESSION_REFERENCE` for a prior-session reference, never `LIVE`.

### 11. 目前 OSAKA 1m 是否 suddenly supported？
NO. `supports_capability("OSAKA_MICRO","1M") == (False, "MISSING_DATA_CAPABILITY")`.

### 12. 目前 Taiwan 1m 是否 suddenly supported？
NO. `supports_capability("TAIWAN_STOCK","1M") == (False, "MISSING_DATA_CAPABILITY")`.

### 13. L1/L2 是否 suddenly available？
NO. `TICK/L1/L2/ORDER_EVENT` all `(False, "MISSING_DATA_CAPABILITY")`.

### 14. 是否開始 V2 state model？
NO.

### 15. 是否開始 distribution fitting？
NO.

### 16. V2 architecture 是否正式 freeze？
YES. `docs/architecture/MARKET_AI_HUB_ARCHITECTURE_V2_FREEZE.md` (CORE_V2 / RESEARCH_CHALLENGER /
DATA_DEPENDENT / DEFERRED + dependency order + change control), all freeze checks passed.

## Files added/changed

- ADD `src/market_ai_hub/research/v2/__init__.py`, `research/v2/asof.py`
- ADD `config/data/staleness_policy.yaml`
- ADD `docs/architecture/MARKET_AI_HUB_ARCHITECTURE_V2_FREEZE.md`, `docs/architecture/v2-asof-data-contract.md`
- ADD `tests/test_v2a_asof.py`
- MOD `tests/test_challengers_2d1.py`, `tests/test_research.py`, `tests/test_tournament.py` (build_id snapshot)

## ASOF verified datasets
None.

## Legacy temporal-unverified datasets
OSE micro daily bars, preclose snapshots, JPX settlement, TWSE daily cache, TAIFEX cache, US
Treasury cache, DuckDB feature store (all `LEGACY_TEMPORAL_UNVERIFIED`).

## Data capability registry summary
`OSAKA_MICRO/TAIWAN_STOCK/TAIWAN_INDEX/^N225`: DAILY=YES, 1M/5M/…/TICK/L1/L2/ORDER_EVENT=NO.
`NQ/ES/USDJPY/SOX/VIX/WTI/BRENT`: NOT_AVAILABLE. `USTREASURY` daily available; `FRED_MACRO`
periodic, REVISION_RISK_PRESENT. Registry version `2A.1`.

## Gate result
**PHASEV2A_ASOF_DATA_TRUTH_PASS** — canonical tz-aware schema; event/source/observed/ingested
separated; feature cutoff + forecast origin explicit; point-in-time lookup future-safe; late
observation blocked; release-time leakage blocked; staleness machine-readable; market/session
context machine-readable; OSE Direct/Proxy calendars preserved; holiday trading representable;
snapshot lineage available; data capability registry truthful; 1m/L1/L2 unavailable; legacy not
falsely ASOF_VERIFIED; V2 freeze created; existing gates unchanged; full pytest PASS; 0 Critical /
0 High.

## Recommended next phase
**V2-B — Daily Gap / Overnight + Session Truth** (builds on the V2-A temporal/session foundation).