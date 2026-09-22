# PHASE V2-B — Daily Gap / Overnight Decomposition + Session Truth — REPORT

- **Schema**: `V2_GAP_SESSION_SCHEMA_VERSION = "2B.1"` (module `src/market_ai_hub/research/v2/gap_session.py`)
- **V2-A schema**: unchanged `2A.1` (two defects fixed in-place, no version bump needed)
- **Baseline main**: `e5824ecc5bb750e4ff790f46009c8b3d2ca12ba0`
- **Runtime build_id (new)**: `fdeb51bad6a639b9` (was `94b5c1a8a55becfb`)
- **Tests**: `1011 passed, 20 deselected` (was `989`; +22 V2-B)
- **Focused V2-A + V2-B**: 50 passed

## Answers

### 1. V2-A missing-count defect 是否確認並修正？
YES. `market_context_quality({}, expected_sources=["NQ","SOX"])` now returns
`missing_source_count=2`, `source_coverage={NQ:MISSING, SOX:MISSING}`, `overall_status=CRITICAL`.
Regression test `test_market_context_quality_missing_count_truthful`.

### 2. forward_fill flag defect 是否確認並修正？
YES. `point_in_time_join()` now sets `forward_filled=True` whenever the output is carry-forward
from a prior observation (not a freshly matched observation), while preserving the original
value / observed_at / event_timestamp / age / staleness. Regression test
`test_forward_fill_flag_truthful`.

### 3. 哪些 dataset 實際具 OHLC？
- OSE Micro daily bars: `open/high/low/close/volume/count` — full OHLC.
- OSE preclose snapshots: `close_T/open_T1` — open+close only (no high/low).
- TWSE daily cache: `OpeningPrice/HighestPrice/LowestPrice/ClosingPrice` — full OHLC.
- ^N225 feature store: `close` only.

### 4. 哪些 target 能計算 true daily gap？
`OSAKA_MICRO` (OSE daily bars) and `TAIWAN_STOCK` (TWSE daily cache) — both have reliable
previous-close + open.

### 5. 哪些只能 close-to-close？
`^N225` (feature store has `close` only, no open) — close-to-close only, no gap.
`TAIEX`/`TAIWAN_INDEX` — not stored as a managed OHLC dataset locally (would require yfinance
`^TWII`).

### 6. Osaka Direct / ^N225 是否完全隔離？
YES. Direct Micro = `OSE_DERIVATIVES` / `DIRECT`; `^N225` = `XTKS` / `PROXY`. Records carry
`target_family` + `instrument_role` + `calendar_id`; no cross-target merge.

### 7. roll boundary 如何處理？
`roll_status == ROLL_BOUNDARY` → `gap_interpretation = NOT_COMPARABLE`, no overnight-gap return
computed (not treated as a real overnight market gap).

### 8. Japan cash holiday + OSE open 如何表示？
`holiday_status=HOLIDAY_TRADING`, `cash_reference_status=CLOSED_MARKET_REFERENCE`,
`basis_comparability=NOT_COMPARABLE`.

### 9. 是否建立任何 intraday claim？
NO. Daily OHLC only; no 1m/5m/tick; the module documents that high/low ordering is unknowable.

### 10. 是否建立 public probability？
NO. `summarize_gaps()` / `conditional_rate()` output is `DESCRIPTIVE_HISTORICAL_RATE`,
`NOT_CALIBRATED`, `NOT_PUBLIC_PROBABILITY`, `INSUFFICIENT_SAMPLE` when below min_sample.

### 11. 是否建立 trading signal？
NO. `DailyGapSessionRecord` has no instruction/signal/long/short fields.

### 12. 2026-09-22 是否被 hardcode？
NO. No price levels or single-day rules are embedded; the 2026-09-22 case stays in the case study.

## Files added/changed
- ADD `src/market_ai_hub/research/v2/gap_session.py`
- ADD `tests/test_v2b_gap_session.py`
- MOD `src/market_ai_hub/research/v2/asof.py` (2 V2-A defect fixes)
- MOD `tests/test_challengers_2d1.py`, `tests/test_research.py`, `tests/test_tournament.py` (build_id)

## Data capability (unchanged)
1m / tick / L1 / L2 = unavailable for all targets; DAILY only.

## Gate result
**PHASEV2B_DAILY_GAP_SESSION_PASS** — two V2-A defects closed; daily gap decomposition correct
(identity holds); calendar-aware previous session; missing open/prev-close fail closed; roll
boundary protected; holiday semantics correct; Direct/Proxy isolated; Taiwan/Osaka isolated; no
intraday fabrication; no calibrated/public probability; no trade instruction; full pytest PASS;
0 Critical / 0 High.

## Recommended next phase
**V2-C — Multi-Target Label Engine (Touch / Break / Acceptance)** (daily barrier labels, using
the V2-B gap/session + V2-A as-of foundations).