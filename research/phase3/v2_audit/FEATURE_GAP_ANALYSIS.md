# FEATURE GAP ANALYSIS (V2)

Current feature set vs. V2 target (profit-taking / exhaustion / acceptance / catalyst response).
Status: `EXISTS` / `PARTIAL` / `MISSING` / `REQUIRES_NEW_DATA` / `LEAKAGE_RISK`.

## Current feature set (verified)

`features/features.py:FEATURE_COLUMNS` + `FEATURE_INPUT` (baseline_ml.py:54):
`returns, log_returns, rolling_volatility, atr, rsi, ema_10, ema_20, sma_20, distance_from_ma20,
rolling_high_20, rolling_low_20, realized_volatility_20, volume_change, time_of_day, day_of_week`
+ labels `future_return_1, future_return_3`.

## V2 feature audit

| Feature | Status | Note |
|---|---|---|
| Price Extension | `MISSING` | no distance-from-open/range-extension feature |
| Gap / Overnight Return | `MISSING` | no prev-close→open decomposition |
| Distance from VWAP | `MISSING` (REQUIRES_NEW_DATA) | no intraday VWAP; daily-only proxy would be misleading |
| ATR-normalized Extension | `PARTIAL` | `atr` exists; no extension/ATR ratio |
| RSI | `EXISTS` | daily, `_rsi(close,14)` |
| Stochastic | `MISSING` | |
| Williams %R | `MISSING` | |
| ADX slope | `MISSING` | ADX absent |
| Volume | `EXISTS` (raw) | |
| Relative Volume | `MISSING` | no time-of-day / session baseline |
| Price-Volume Divergence | `MISSING` | |
| Failed Breakout Count | `MISSING` | no breakout/acceptance label base |
| Time-at-High / Time-at-Low | `MISSING` | needs intraday |
| Distance from Session High/Low | `MISSING` (REQUIRES_NEW_DATA) | |
| Lower High / Lower Low | `MISSING` | |
| Higher High / Higher Low | `MISSING` | |
| BOS (break of structure) | `MISSING` | needs structure model |
| Round Number Distance | `MISSING` | |
| Previous High/Low | `PARTIAL` | `rolling_high_20/rolling_low_20` are rolling, not "previous session" |
| Pivot | `MISSING` | |
| Volume Profile | `MISSING` (REQUIRES_NEW_DATA) | daily bar has no intraday volume distribution |
| Futures-Cash Basis | `MISSING` (REQUIRES_NEW_DATA) | OSE micro vs ^N225 basis not computed daily; TSE cash holiday degrades it |
| time_of_day | `PARTIAL` (misleading at daily) | `timestamp_utc.dt.hour` on a daily bar is quasi-constant |
| Cross-market features | `PARTIAL` | `cross_market_features()` computes per-symbol returns/volume_change only |

## Key structural gaps

1. **No intraday features at all** — every timing/extension/exhaustion feature is `REQUIRES_NEW_DATA`.
2. **time_of_day is near-constant at daily frequency** — must move to intraday session semantics.
3. **No VWAP / volume profile / session high-low** — these are the backbone of acceptance/exhaustion.
4. **`distance_from_ma20`** is the only "extension" proxy and is a daily 20-bar MA, not intraday extension.
5. **Cross-market** only computes returns/volume_change; no lead-lag, beta, response residual.

## Look-ahead risk flags (see LABEL_LEAKAGE_AUDIT.md + TEMPORAL_ASOF_AUDIT.md)

- `future_return_1/3` are labels, correctly excluded from `FEATURE_INPUT` (verified `baseline_ml.py:54` vs `features.py:20`).
- `time_of_day` at daily frequency is **not leakage but not meaningful**.
- Any future VWAP / session-high / volume-profile feature is `HIGH_LEAKAGE_RISK` unless built **as-of** a bar timestamp (see §16 of the audit spec).

## Signal cluster principle (explicit)

RSI overbought / Stochastic overbought, **alone, are not a reversal signal**. They are evidence
components only. The V2 design must never emit a "reversal" state from a single oscillator value.
