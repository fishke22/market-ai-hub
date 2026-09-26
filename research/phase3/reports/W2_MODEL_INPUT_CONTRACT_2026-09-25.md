# W2 Gated Model-Input Contract — 2026-09-25

Implementation commit: `9a11ce309ef5159545cb64e4ed8fa81ca0bbacfd`  
Runtime build_id: `bed003b51f6d1f8b`

## Result

The W2 offline engineering path now reaches a model-input boundary:

`persisted quote -> V2-A.2 -> V2-H lineage -> Feature Store gate -> packet provenance -> model-input contract`

This is `W2_OFFLINE_CONTRACT_PASS`, not `DATA READY`.

## Model-input rules

The input builder is read-only and only sees Feature Store rows that were materialized through the W2 eligibility gate. It fixes `information_cutoff` and requires homogeneous representation, contract and source frequency. Later-available rows are excluded. Multiple contracts without an explicit contract request, mixed/unknown frequency, duplicate event timestamps, missing W2 schema and insufficient history produce typed abstention statuses.

Lineage IDs and source snapshot IDs remain attached to the input bundle. Public readiness metadata never exposes model-input values.

## Current broker-to-model truth

Yuanta broker quote observations are `TICK`. Current Chronos-2, TimesFM-3 and classification forecast contracts are `1d`. The system therefore reports `INCOMPATIBLE_FREQUENCY` for Osaka direct broker features at the current daily-model boundary. It does not resample a few ticks into fake daily bars and it does not silently fall back while calling the result a direct OSE model.

A `TICK`-compatible request can build a homogeneous lineaged series when enough points exist; that proves the data reaches the model-input boundary. No currently approved daily model consumes that tick series.

## Validation

- focused model-input contract: `117 passed, 1 deselected`;
- packet group: `76 passed, 1 deselected`;
- V2/quote group: `146 passed`;
- final default suite: `1735 passed, 23 deselected, 132 warnings in 141.75s`, exit 0;
- changed-file secret scan: 0 hits;
- `git diff --check`: PASS.

## Remaining boundaries

Live recorder runtime adoption remains pending and requires an explicitly authorized maintenance window. No validated TICK→daily bar aggregation contract exists yet, so broker data is not DATA READY for the existing daily models. Reconnect/roll/WAL are still separate W1 operational gaps.

The next correctness package is W3: horizon maturity, `evaluation_as_of`, and homogeneous target/model-version/event-family scope. Calibration fitting remains forbidden until W3 and real settled probabilistic evidence exist.
