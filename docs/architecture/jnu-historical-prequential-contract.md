# JNU Historical Prequential Replay Contract

Schema: HPQ1

## 2026-09-27 repair amendment

The existing 131-origin seal is retained but blocked for next-session use: its
2026-09-18 target is 2026-09-24 although OSE next trades on 2026-09-21. Builder
and sealed-summary consumers now reject this horizon mismatch. Do not rerun the
opened final or silently remove the offending record to reclaim validation.
The frozen protocol YAML is unchanged; a new target/publication-time protocol
requires a new registration and new untouched evidence, not a rewrite of HPQ1.

The operational CLI reads an existing seal before loading models. A first replay
exclusively creates FINAL_HOLDOUT_ATTEMPTED before any model factory; failures
retain that marker for explicit audit. Sealing exclusively creates the artifact;
only fully identical content is idempotent. Interrupted writes remain blocking
instead of allowing silent replacement. This is local process coordination, not
a tamper-proof external ledger. Direct library replay with supplied frames remains
available for synthetic tests; operational real replay must use the guarded CLI.

All price quantile paths must be finite, positive, ordered and exactly match the
requested horizon. HPQ1 rejects horizons other than one. A known training-cutoff
string alone yields HISTORICAL_PREQUENTIAL_OOS_NOT_VERIFIED, never CLEAN OOS;
actual cutoff chronology and publication availability would need independent gates.

Protocol: jnu_front_exact_settlement_1d_v1

## Purpose

This layer provides rigorous retrospective pseudo-forward evidence before enough real W3.2 forward samples exist.
At each historical origin, the frozen model receives only the exact-contract settlement history available through that origin.
The next exact-contract settlement is revealed only after the forecast has been produced.

Historical prequential evidence is not W3.2 FORWARD_PRECOMMITTED evidence, not W4 calibration evidence and not trading edge.

## Data and contract selection

- Source: persisted official JPX/OSE public Daily Report Micro settlements only.
- Target: next-session official settlement.
- History length: 32 exact-contract observations.
- An eligible contract must be unexpired, have 32 observations through the origin, and have a next exact-contract settlement before expiry.
- If multiple contracts qualify on the same origin date, choose the nearest expiry month.
- Count at most one observation per origin date.
- Different contracts are never stitched into one continuous price series.

The one-origin-one-front-contract rule prevents overlapping listed contracts from artificially multiplying the sample count.

## Frozen partitions

The partition boundaries were selected from sample counts only, before the real model replay was run:

- HISTORICAL_DEVELOPMENT: origin through 2026-05-15
- HISTORICAL_VALIDATION: 2026-05-16 through 2026-07-10
- HISTORICAL_FINAL_HOLDOUT: 2026-07-11 through 2026-09-18

The final holdout is one-use. The local SEALED.json artifact is immutable by evidence identity.
A different source, model or protocol identity is refused after the first final-holdout opening.

## Time boundary

For every sample:

1. Context ends at the origin exact-contract settlement.
2. Forecast is produced.
3. Only then is the next exact-contract settlement used as outcome.

Drift and moving-average baselines are also frozen from the origin context before the target is read.

The public Daily Report archive does not expose a separately governed historical publication timestamp for each parsed row.
Therefore the availability grade is SESSION_ORDER_CAUSAL_NOT_PUBLICATION_TIMESTAMP and cannot be promoted to governed real-forward evidence.

## Model-training boundary

The tracked model registry currently records the training cutoff for Chronos-2 and TimesFM-3.0 as unknown.
Therefore even a perfectly causal replay is graded HISTORICAL_PREQUENTIAL_TRAINING_CUTOFF_UNKNOWN, not clean model-training OOS.

If verifiable training cutoffs become available later, only origins strictly after the relevant cutoff may qualify for a stronger historical-OOS grade.

## Metrics

For each model and the existing equal-weight ensemble:

- MAE, RMSE and MASE against last-price naive
- direction accuracy
- causal drift and moving-average baselines
- paired model-minus-naive absolute-error delta with deterministic bootstrap CI
- p10-p90 empirical coverage

Development, validation and final holdout are reported separately.
Pooled results may be used as a diagnostic but do not override the pre-registered final-holdout interpretation.

## Evidence hierarchy

Historical prequential replay is not clean training-OOS when training cutoff is unknown.
It is also not FORWARD_PRECOMMITTED, CALIBRATED, PREDICTIVE_EVIDENCE or TRADING_EDGE.
