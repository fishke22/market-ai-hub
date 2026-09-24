# W3.2 Precommitted Forward Cycle Contract

- **Schema**: `W3_FORWARD_CYCLE_SCHEMA_VERSION = "W3.2"`
- **Module**: `src/market_ai_hub/research/v2/forward_cycle.py`
- **Audit store**: V2-H **2H.3**
- **Evaluation governance**: W3.1
- **Metric engine**: V2-I **2I.1**, unchanged
- **First supported scope**: OSAKA_MICRO / JNU / 1 OSE derivatives session / `last_price_naive`
- **Research only**: no order, account query, broker login, calibration fitting or probability publication.

## Purpose

W3.2 provides the smallest auditable real-forward lifecycle:

```text
eligible contract daily close
  -> precommit prediction before target session begins
  -> immutable 2H.3 prediction + lineage + POINT artifact
  -> wait until the sealed target session closes
  -> append exact contract terminal-close outcome
  -> W3.1 governed FORWARD evaluation
  -> unchanged 2I.1 point metrics
```

It does not backdate predictions and does not convert historical replay into forward evidence.

## Precommit timing

For the first Osaka 1-session contract, the input is a completed OSE day-session close. The next target
exchange day begins with its night session:

- source day close: **15:45 Asia/Tokyo**
- target full-session window start: **17:00 Asia/Tokyo on the completed source date**
- target full-session window end: **15:45 Asia/Tokyo on the next verified OSE session date**

A W3.2 precommit is accepted only after the source close and before the target night session starts.
Once 17:00 JST is reached, a full-session 1d prediction for that target is too late and is refused.

## Eligible input

`OsakaForwardInput` must carry, without inference:

- trading date and exact 15:45 JST session-close timestamp;
- `available_at <= forecast_origin` and `available_at >= session close`;
- finite positive close;
- source snapshot IDs, provider and data grade;
- point-in-time-safe status;
- source frequency DAILY/1D;
- exact contract code and contract month;
- `series_semantics=CONTRACT`;
- `roll_status=NONE`.

The first model is the existing `last_price_naive`: its POINT forecast equals the last eligible
contract close. This is a baseline, not a probability and not a trading recommendation.

## Feature Store boundary

W3.2 reads a dedicated feature contract:

- feature name: `terminal_close`
- feature version: `w3.2-contract-daily-close-1`
- representation: `OSE_MICRO_FUTURES`
- source frequency: DAILY

The adapter reuses the W2 read-only model-input gate and then resolves the exact latest lineage snapshot.
It does not create/migrate the Feature Store and does not silently resample current broker TICK rows.
Missing or incompatible input returns a typed abstention and creates no audit prediction.

## Settlement

The target outcome must be the same contract/month as the prediction lineage, have the exact sealed
target trading date and 15:45 JST close timestamp, become available after that close, and be available
no later than the settlement attempt. Settlement before `label_window_end` is refused.

Outcome records use:

- label: `TERMINAL_PRICE_1D`
- kind: `TERMINAL`
- target period: sealed target trading date
- schema: W3.2
- exact source snapshot IDs

Append-only/idempotent 2H.3 rules still apply.

## Evaluation

`build_forward_evaluation()` selects only this exact W3.2 OSAKA_MICRO scope with
`sample_origin=FORWARD_PRECOMMITTED` and `partition_role=FORWARD`. W3.1 controls
`evaluation_as_of` and sample eligibility before 2I.1 computes POINT MAE/RMSE.

A successful metric calculation is still not calibration or trading edge. W3.2 readiness reports
`CALIBRATED=false`, `CALIBRATION_FITTING=NOT_STARTED`,
`PREDICTIVE_EVIDENCE=NOT_ESTABLISHED`, and `TRADING_EDGE=NOT_ESTABLISHED`.

## Legacy / current-source boundary

The existing continuous Osaka parquet is never promoted into W3.2 forward evidence. It lacks required
`available_at`, source snapshot IDs, contract code/month and roll provenance. Current W2 broker
observations are TICK and are not the dedicated DAILY feature.

Read-only runtime probe on 2026-09-25 Asia/Taipei found:

- existing continuous daily parquet: 960 rows, latest trading date 2026-09-01;
- legacy forward eligibility: BLOCKED;
- canonical Feature Store existed but returned 0 OSE factor observations for the probe cutoff;
- actual W3.2 forward prediction created by this package: **none**.

Therefore **W3.2 ENGINE PASS != REAL FORWARD EVIDENCE**.

## Scheduling

This package does not enable Windows Task Scheduler or any persistent background job. The old
`research/forward_shadow.py` registry remains a historical Phase-2 forward-shadow component and is
not reclassified as W3.2 evidence. Automatic daily execution can only be enabled in a later, explicitly
reviewed operational package after an eligible DAILY contract-close source exists.
