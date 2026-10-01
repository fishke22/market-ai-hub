# Microstructure night-window features — v1 coverage report

Protocol: `research/phase3/MICROSTRUCTURE_NIGHT_WINDOW_PREREGISTRATION_v1.yaml`
(`AV2.MICROSTRUCTURE.NIGHT_WINDOW.v1`, frozen 2026-10-02)
Module: `src/market_ai_hub/research/v2/microstructure_features.py` (schema `MS.1`)
Runner: `scripts/microstructure_feature_coverage.py`
Tests: `tests/test_microstructure_features.py` (14)

## What this is

Feature extraction and coverage only. **No model was fit, no probability was produced, no
ranking was produced, and no holdout was created.** The recorded tick sample is
`DEVELOPMENT_ONLY` and can never be reported as out-of-sample evidence.

## Measured coverage (recorded store, 2026-10-02)

| date | instrument | status | tape rows | window |
|---|---|---|---|---|
| 2026-09-24 | JNUPM2612 / JNU2612 | `TAPE_FIELDS_NOT_IN_STORE` | 0 | — |
| 2026-09-25 | JNUPM2612 / JNU2612 | `TAPE_FIELDS_NOT_IN_STORE` | 0 | — |
| 2026-09-27 | JNUPM2612 / JNU2612 | `NO_TRADE_ROWS` | 0 | — |
| 2026-09-28 | JNUPM2612 | `OK` | 19,204 | 184.5 min |
| 2026-09-29 | JNUPM2612 | `OK` | 15,078 | 214.0 min |
| 2026-09-30 | JNUPM2612 | `OK` | 19,282 | 428.2 min |
| 2026-10-01 | JNUPM2612 | `OK` | 23,336 | 466.4 min |
| all dates | JNU2612 (non-PM) | `NO_TRADE_ROWS` | 0 | — |

**4 usable windows out of 14 date/instrument combinations.**

- 09-24 / 09-25: the partitions predate the tape columns, so the reader reports
  `TAPE_FIELDS_NOT_IN_STORE` instead of silently computing from the wrong fields.
- 09-27: no tape rows in the night window (capture gap).
- `JNU2612` has no tape rows at all; only the `PM`-suffixed contract was subscribed for the
  microstructure tape. This is a recording-configuration fact, not a bug in the extractor.

Sample features for the usable windows (night-session, receipt-clock window):

| date | window_log_return | realized_vol | vwap_deviation | signed_volume_imbalance |
|---|---|---|---|---|
| 2026-09-28 | -0.00847 | 0.00006 | -0.00592 | -0.022 |
| 2026-09-29 | +0.00099 | 0.00005 | -0.00041 | +0.083 |
| 2026-09-30 | +0.00207 | 0.00008 | +0.00354 | -0.024 |
| 2026-10-01 | +0.00058 | 0.00008 | -0.00017 | +0.016 |

## Data-source facts established (and corrected) before any statistic

1. The price-bearing **tape** is `SubscribeStockTick` / `TRADE_TICK`, carrying
   `DealPrice`, `DealVol`, `InOutFlag`, `BuyPrice`, `SellPrice`.
   `SubscribeWatchlistAll.deal/vol` is a last-trade snapshot plus cumulative totals and is
   deliberately **not** combined with the tape, so a trade can never be counted twice.
2. `InOutFlag` is **verified**, not assumed: on recorded 2026-10-01 tape rows, flag=1 occurs at
   or above the ask 92.1% of the time and never at/below the bid; flag=0 occurs at or below the
   bid 100% of the time and never at/above the ask. Hence 1 = buyer-initiated, 0 =
   seller-initiated. Spread measured 5.0–10.0 points (mean 5.5), consistent with JNU Micro.
3. `received_at` is stored as **VARCHAR** ISO-8601 `+00:00`, so a lexicographic comparison is
   the chronological comparison. Binding a datetime object to it raises a DuckDB
   `BinderException`.
4. Parquet parts **drift in schema** (some have `microstructure_kind`/`depth_index_flag`, some
   do not, older partitions have no tape columns). Every reader needs
   `union_by_name=true`, and a day whose union lacks the tape columns must be reported as
   unusable rather than guessed.

## Why no model was fit

- The sample is 4 nights. It cannot support training, and the repo forbids presenting
  in-sample statistics as evidence.
- The package created **no** new holdout and **no** new evidence channel. Any model that
  consumes these features must be validated through the **existing** forward protocol of the
  1d settlement family (P5 canonical origins + W3.2-EP1), exactly like every other 1d model.
- Credibility is currently blocked by `ACTUAL_FORWARD_EVIDENCE = NONE_YET`, not by feature
  availability. Building a model now would produce an unvalidatable artifact.

## Honest statement

This is feature **coverage**, not signal, not evidence, not a probability and not a trading
edge. `PREDICTIVE_GAIN=false`, `CALIBRATED=false`, `TRADING_EDGE=false` are unchanged.

## Next package (only after this registration exists)

Fit nothing until the operator confirms the target/horizon reuse. When a model is eventually
tried, it may only be promoted through the existing forward protocol; the 4-night sample stays
`DEVELOPMENT_ONLY`.
