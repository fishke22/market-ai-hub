# JNU Historical Prequential Replay — 2026-09-27

## Method preregistration

- Protocol and engine preregistration commit: 49f46ec6abc51723c18fe393ee90659f014c6e30
- Schema: HPQ1
- Protocol: jnu_front_exact_settlement_1d_v1
- Data source: official JPX/OSE public Daily Report Micro settlements
- History: 32 exact-contract observations
- One front exact contract per origin date; no continuous-contract stitching
- Partition boundaries selected from sample counts only before model replay
- Final holdout one-use seal enabled

The public JPX archive available on 2026-09-27 exposed months 202601 through 202609.
Missing local months 202601 through 202606 were materialized before replay: 106 additional trading days with zero parser errors.

## Sealed evidence

- Evidence ID: 3f28cec82268445d7d377356
- Grade: HISTORICAL_PREQUENTIAL_TRAINING_CUTOFF_UNKNOWN
- Origins: 131, one per trading day
- Development: 43
- Validation: 40
- Final holdout: 48
- First origin: 2026-03-11
- Last origin: 2026-09-18

The seal is stored under the configured data root and is not committed to Git.

## Results

### Chronos-2

- Development: MASE 1.0935; direction 58.1%; paired 95% CI [-18.70, 184.14]
- Validation: MASE 1.0466; direction 50.0%; paired CI [-43.49, 155.19]
- Final holdout: MASE 1.0907; direction 52.1%; paired CI [-30.42, 179.62]
- Pooled 131: MASE 1.0747; paired CI [16.36, 129.24]

### TimesFM-3.0

- Development: MASE 1.1014; direction 48.8%; paired CI [-35.08, 212.38]
- Validation: MASE 1.0120; direction 50.0%; paired CI [-90.98, 114.09]
- Final holdout: MASE 1.1590; direction 47.9%; paired CI [-31.31, 304.60]
- Pooled 131: MASE 1.0859; paired CI [3.99, 157.82]

### Existing equal-weight JNU ensemble

The ensemble was derived only from already sealed per-origin forecasts; models were not rerun.

- Development: MASE 1.0929; direction 51.2%; paired CI [-18.04, 185.90]
- Validation: MASE 1.0247; direction 57.5%; paired CI [-47.24, 111.71]
- Final holdout: MASE 1.1228; direction 50.0%; paired CI [-24.34, 229.28]
- Pooled 131: MASE 1.0766; paired CI [11.01, 132.44]

The final-holdout intervals all cross zero. Therefore the pre-registered final holdout does not establish a stable advantage over last-price naive.
The pooled 131-sample CIs are positive and are a risk signal that average error may be worse than naive, but pooled diagnostics do not override the pre-registered final-holdout interpretation.

## Important limitation

Chronos-2 and TimesFM-3.0 both have training_cutoff = unknown in the tracked model registry.
Therefore these 131 observations are not claimed as clean model-training OOS.
They prove that the evaluation replay itself is causal with respect to the supplied exact-contract series, not that the foundation models could not have seen related historical data during pretraining.

These samples do not count toward the W4 minimum 50 calibration + 50 validation + 50 one-use real-forward final OOS.
W3.2 real forward remains a separate evidence stream.

## Validation

- Preregister/build focused: `52 passed, 3 deselected`
- Sealed-evidence integration focused: `46 passed`
- Agent/Skill focused: `82 passed, 4 deselected`
- Full offline: `1984 passed, 1 skipped, 35 deselected, 110 warnings in 185.43s`
- Real CherryStudio-style stdio public/audit JNU smoke: PASS on build `03f1971c29d2f394`
- No broker login/logout/restart/order/account action was performed.
