# W3 Evaluation Governance Contract

- **Schema**: `W3_EVALUATION_GOVERNANCE_SCHEMA_VERSION = "W3.1"`
- **Module**: `src/market_ai_hub/research/v2/evaluation_governance.py`
- **Upstream audit**: V2-H **2H.3**
- **Metric engine**: V2-I **2I.1**, unchanged
- **Purpose**: decide which already-audited samples are legally eligible for evaluation. It does **not** fit a calibrator.

## Core rule

A sample may enter governed evaluation only when all of the following are true:

1. prediction identity already sealed an explicit `sample_origin` and label window before outcome;
2. `label_window_end <= evaluation_as_of`;
3. the bound outcome became available no earlier than label-window end and no later than `evaluation_as_of`;
4. `outcome.target_period == prediction.label_window_id`;
5. target family, instrument, horizon, model, model version, artifact type, label type, calibration domain,
   probability/event family and partition role match one exact `EvaluationScope`;
6. the selected sample is not a superseded prediction and does not duplicate another logical sample in the same scope.

`FORWARD_PRECOMMITTED` and `RETROSPECTIVE_REPLAY` are separate scopes. `UNKNOWN` is never a
governed scope.

## evaluation_as_of

`evaluation_as_of` is mandatory and timezone-aware. It is the knowledge cutoff for evaluation, not
"now" implicitly. An outcome that exists in the database but whose `available_at` is later than that
cutoff is excluded. This prevents later outcomes from leaking into an earlier evaluation recreation.

## Blocking versus insufficient evidence

Blocking violations include cross/mixed scope, duplicate logical samples, premature outcomes,
outcome-window mismatch and selected superseded samples. Missing outcomes, samples whose horizon has
not matured yet, and outcomes not yet available at the evaluation cutoff are excluded as insufficient
evidence rather than fabricated.

The governed manifest exposes candidate count, valid sample count, missing-outcome count, event count,
observed label-window IDs, deterministic calendar coverage when supported, missing days, overlapping
horizon pairs and rejection counts.

## Relationship to 2I.1

W3.1 calls the existing 2I.1 pairing/metric engine only after governance passes. It does not change
Brier/log-loss/reliability/point/quantile/interval formulas and does not change the 2I.1 result enum.

`READY_FOR_EVALUATION != CALIBRATED`. W3.1 readiness always reports
`CALIBRATION_FITTING=NOT_STARTED` and `CALIBRATED=false`. Actual fitting remains a later W4 work
package and requires real, sufficiently mature, scope-homogeneous samples plus a pre-registered
validation protocol.

## Current evidence boundary

The W3.1 regression suite uses temporary synthetic audit records to prove the governance engine.
Synthetic samples are never predictive evidence. Real forward sample accumulation remains
data/time-dependent and must be reported separately per market family.
