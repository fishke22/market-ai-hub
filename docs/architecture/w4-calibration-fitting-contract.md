# W4 Calibration Fitting Contract

Schema: W4_CALIBRATION_FITTING_SCHEMA_VERSION = W4.1
Module: src/market_ai_hub/research/v2/calibration_fitting.py
Protocol: config/calibration_protocols.yaml

## Purpose

W4 turns already-governed EVENT_PROBABILITY samples into typed calibration evidence. It does not
create probability forecasts, does not read external labels, and does not consume FINAL_OOS for
fitting or model selection.

ENGINE PASS != CALIBRATED. Synthetic tests only prove the fitter.

## Input boundary

Both inputs must be W3.1 GovernedEvaluationManifest objects with identical scope except partition:

- fit partition = CALIBRATION
- evaluation partition = VALIDATION
- artifact_type = EVENT_PROBABILITY
- calibration_domain = PRICE_DISTRIBUTION
- sample_origin = FORWARD_PRECOMMITTED
- probability family in TERMINAL / TOUCH / FIRST_PASSAGE
- no W3 or 2I.1 blocking rejections
- no overlapping label-window pairs when the tracked protocol requires purge
- calibration window must not overlap validation window
- member-level label windows must be purged before the next partition forecast origin
- one exact model/version, event definition, label type, distribution id/version

FINAL_OOS is rejected by construction.

## Pre-registered protocol

w4_ppm_sigmoid_v1 is tracked before real fitting results exist:

- sigmoid (Platt-style) calibration on logit(raw_probability)
- fit >= 50 samples; validation >= 50 samples; final OOS >= 50 samples
- each binary class >= 10 in each evaluation partition
- each calibration / validation / final-OOS partition spans at least 30 calendar days
- validation and final-OOS Brier, log-loss and ECE may not degrade
- paired deterministic bootstrap (1000 replicates, 95% CI) upper bounds must also show non-degradation
- at least one of those metrics must strictly improve
- fitted sigmoid slope must be non-negative

The thresholds are a research protocol, not a claim that 50 samples proves trading edge.

## Output

The validation fitter produces a frozen content-addressed w4_cal_* candidate and the existing
price_probability_map.CalibrationEvidence type, but its status remains EVALUATED_UNCALIBRATED even
when validation passes. Public CALIBRATED evidence requires a second w4_final_* artifact created by
finalize_with_final_oos().

FINAL_OOS is a separate one-use partition. The frozen sigmoid parameters are not refit or selected
after looking at FINAL_OOS. The local artifact store records a consumption marker keyed by the
content-addressed final dataset id; a second attempt to use the same final dataset is rejected.
Only a final-OOS result that passes the same pre-registered non-degradation rule can emit
status=CALIBRATED.

## Current market-evidence boundary

As of 2026-09-26 W3.2-EP1 is implemented to precommit raw UNCALIBRATED Osaka EVENT_PROBABILITY
artifacts alongside the POINT baseline once a verified C2.3 DAILY close exists. No real W3.2-EP1
artifact has settled yet because the producer was completed on a non-OSE-session date. W4 therefore
remains REAL_CALIBRATION_FIT_NOT_STARTED until scope-homogeneous forward event-probability samples
actually accumulate; implementation availability is not calibration evidence.
