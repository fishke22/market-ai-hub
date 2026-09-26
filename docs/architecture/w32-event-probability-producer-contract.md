# W3.2-EP1 Raw Event-Probability Producer Contract

Status: RESEARCH_ONLY / UNCALIBRATED_RAW_PROBABILITY

The producer runs alongside the existing W3.2 POINT forward cycle. It does not replace the
last-price-naive prediction and does not publish calibrated probabilities.

## Event

Target family: OSAKA_MICRO
Instrument: exact JNU contract
Horizon: next full OSE derivatives session
Probability type: TERMINAL
Event definition: TERMINAL_CLOSE_GT_SOURCE_CLOSE_1D
Label: TERMINAL_ABOVE_SOURCE_CLOSE_1D

At forecast origin the exact source-session terminal close is frozen into the immutable
EVENT_PROBABILITY artifact as event_threshold_value. Settlement compares the exact target-session
verified contract terminal close with that frozen threshold. Equality is false, not ambiguous.

## Raw probability

Method: causal Beta-Bernoulli prior/posterior mean with Beta(1,1).

p = (prior settled successes + 1) / (prior settled successes + prior settled failures + 2)

Only outcomes whose available_at is no later than the current forecast origin may enter the
history. A stored outcome that became available later is excluded. The history is additionally
restricted to the same exact contract_code + contract_month with series_semantics=CONTRACT and
roll_status=NONE; rollover contracts never silently share a prior. With no prior settled outcomes,
the first raw probability is exactly 0.5 and explicitly represents the uninformative prior.

The artifact is always calibration_status_at_origin=UNCALIBRATED and is_public_probability=false.
It uses a stable model/version and distribution id/version so later W4 governance can form
scope-homogeneous CALIBRATION / VALIDATION / one-use FINAL_OOS partitions.

## Automatic operation

run_w32_osaka_forward_cycle.py now operates two independent W3.2 scopes from the same verified
DAILY exact-contract input:

1. existing POINT last-price-naive prediction;
2. W3.2-EP1 raw EVENT_PROBABILITY prediction.

On each eligible C2.3 maintenance cycle it first settles pending predictions from the exact target
terminal close, then precommits both scopes for the next full OSE session. Failure of either
precommit makes the operator non-zero/fail-closed.

## Evidence boundary

A raw EVENT_PROBABILITY sample is not CALIBRATED, predictive evidence, or trading edge.
W4 requires at least 50 CALIBRATION + 50 VALIDATION + 50 FINAL_OOS samples under its tracked
protocol, plus all acceptance tests. Sample count alone never guarantees CALIBRATED.
