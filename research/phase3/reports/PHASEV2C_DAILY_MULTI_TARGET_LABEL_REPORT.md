# PHASE V2-C — Daily Multi-Target Label Engine (Touch / Break / Acceptance) — REPORT

- **Schema**: `V2_DAILY_LABEL_SCHEMA_VERSION = "2C.1"` (`src/market_ai_hub/research/v2/labels.py`)
- **V2-A unchanged**: `2A.1`; **V2-B unchanged**: `2B.1`; **PPM unchanged**: `3A.2.3`
- **Baseline main**: `f15773f3c100dc3c6c3cef071a7b624e9f951feb`
- **Runtime build_id (new)**: `53d5b83595d8a639` (was `fdeb51bad6a639b9`)
- **Tests**: `1060 passed, 20 deselected` (was `1011`; +49 V2-C)

## Preflight findings

- **P1 roadmap/freeze**: formal `MARKET_AI_HUB_ARCHITECTURE_V2_FREEZE.md` keeps V2-C Label Engine;
  not reverted.
- **P2 old label design**: `MULTI_TARGET_LABEL_DESIGN.md` described intraday touch/acceptance; V2-C
  implements **daily research proxies** (`DAILY_TOUCH` / `DAILY_CLOSE_BREAK` /
  `DAILY_CLOSE_ACCEPTANCE`), explicitly not intraday equivalence.
- **P3 capability registry semantics**: `asof.py::_CAPABILITY_REGISTRY` expresses coarse
  target/provider capability, NOT local field readiness. V2-C does **not** use
  `supports_capability(target,"OHLCV")` to allow Touch; it validates actual input `DailyOutcomeBar`
  fields (open+high+low+close). Separated via `daily_adapter.local_field_readiness()`. No V2-A
  registry rewrite (semantic debt documented, not churned).
- **P4 target/proxy isolation**: `validate_identity_scope()` machine-enforces instrument /
  target_family / instrument_role / calendar_id consistency → `BLOCKED_IDENTITY_MISMATCH`.
- **P5 roll provenance**: `DailyOutcomeBar.roll_status` default `UNKNOWN` (not `NONE`); futures
  `UNKNOWN`/`ROLL_BOUNDARY` → `BLOCKED_ROLL_PROVENANCE`. OSE parquet has no contract id/roll →
  adapter sets `UNKNOWN` honestly.
- **P6 build fingerprint**: build_id = `src/**/*.py` + listed runtime config (verified
  `build_info.py`). No new runtime config added; label policy is code-side typed
  (`DailyLabelPolicy`). build_id changed only because new runtime source was added.

Existing labels/callers: `future_return_k` / `make_classification_labels` used by
`baseline_ml.py`, `mcp/server.py` (backtest), `tournament/v1_adapters.py`. No prior
touch/break/acceptance implementation existed. `gap_session.py` has no runtime caller.

## Contract implemented

- schema `2C.1`; Touch = `low <= L <= high`; Break = strict `close > L`/`< L`; Acceptance =
  N=2 consecutive daily closes beyond; horizon = first H trading sessions after forecast_origin;
  gap-cross → `AMBIGUOUS_GAP_CROSS` (no fake Touch); maturity = negative requires full horizon +
  no missing; roll `UNKNOWN`/`ROLL_BOUNDARY` fail closed; identity machine-enforced; legacy stays
  `LEGACY_TEMPORAL_UNVERIFIED`.

## Actual local data evidence (read-only)

| dataset | rows | range | fields | OHLC | asof | roll | V2-C runnable | blocker |
|---|---|---|---|---|---|---|---|---|
| OSAKA_MICRO daily | 960 | 2023-07-24 → 2026-09-01 | trading_date,open,high,low,close,volume,count | full OHLC | LEGACY_TEMPORAL_UNVERIFIED | UNKNOWN (no contract id/roll) | single-session Touch/Break only; multi-session blocked | NO_ROLL_PROVENANCE |
| TAIWAN_STOCK / TWSE | NOT_CHECKED (cache json; known OHLC fields) | — | Opening/Highest/Lowest/ClosingPrice | full OHLC | LEGACY_TEMPORAL_UNVERIFIED | NOT_APPLICABLE | yes (per-symbol, no roll) | — |
| ^N225 | NOT_CHECKED this phase (feature store close-only) | — | close | close-only | LEGACY_TEMPORAL_UNVERIFIED | NOT_APPLICABLE | Break/Acceptance only (close); Touch NOT possible | NO_HIGH_LOW |
| TAIWAN_INDEX | NOT_CHECKED | — | — | none | — | NOT_APPLICABLE | NOT_AVAILABLE_LOCAL_DATASET | no managed OHLC |

## Tests

- V2-C focused: `pytest tests/test_v2c_daily_labels.py -q` → **49 passed**.
- V2-A+B+C regression: `pytest tests/test_v2a_asof.py tests/test_v2b_gap_session.py tests/test_v2c_daily_labels.py -q` → **99 passed**.
- Probability contract regression: `tests/test_phase3a*.py` → **121 passed**.
- Full suite: `pytest tests/ -q -p no:cacheprovider` → **1060 passed, 20 deselected, 144 warnings**.

## Unit vs dataset vs MCP vs UAT

- Unit tests: PASS (49).
- Actual dataset run: OSE micro inspected read-only (960 rows); label engine does NOT run
  multi-session futures labels (roll provenance blocks). Single-session synthetic runs verified.
- MCP integration: `NOT_INTEGRATED_THIS_PHASE`.
- Manual Cherry UAT: `RETEST_REQUIRED`.

## Research / safety status

model training NO · distribution fitting NO · calibration fitting NO · public probability NO ·
trade signal NO · broker/order NO · new scheduler NO · V2-D started NO · 3B.1 started NO ·
Phase2 frozen conclusions changed NO.

## Known limitations / unresolved risks

- daily OHLC path-order limitation (no first-passage, no intraday ordering).
- gap exact-touch ambiguity (`AMBIGUOUS_GAP_CROSS`).
- OSE futures roll provenance absent → multi-session Osaka futures labels blocked.
- OSE holiday-trading calendar coverage limited (config + exchange_calendars XTKS cash only).
- legacy temporal status (no ASOF_VERIFIED).
- `^N225` close-only, `TAIWAN_INDEX` no managed OHLC.
- `asof.py::_CAPABILITY_REGISTRY` coarse target-capability semantic debt (documented, not churned).

## Gate recommendation

**PHASEV2C_DAILY_MULTI_TARGET_LABEL_PASS** (engine contract complete + truthful; Osaka multi-session
futures actual-dataset run remains `BLOCKED_ROLL_PROVENANCE`, documented as per-dataset readiness,
not an engine failure).

STOPPED AFTER V2-C. V2-D NOT STARTED.
