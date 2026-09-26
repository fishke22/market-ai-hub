# W5.1 Daily First-Passage Contract

Schema: W5_FIRST_PASSAGE_SCHEMA_VERSION = W5.1
Module: src/market_ai_hub/research/v2/first_passage.py

## Purpose

W5.1 closes the path-event labeling gap between the existing daily V2-C barrier engine and the
Price/Probability Map FIRST_PASSAGE probability family.

The engine is research-only. It does not generate probabilities and does not infer intraday order
from daily OHLC.

## Inputs

- one DailyLabelRequest
- one frozen upper BarrierSpec(direction=UP)
- one frozen lower BarrierSpec(direction=DOWN)
- the same daily outcome bars, trusted calendar provenance and expected-session window used by V2-C

Upper must be strictly above lower. Both barriers must satisfy the existing V2-C provenance and
cutoff rules.

## Outcomes

After a fully mature observable horizon:

- UPPER_FIRST
- LOWER_FIRST
- NEITHER
- AMBIGUOUS_WITHIN_DAILY_BAR

If both barriers are touched in the same daily bar, daily OHLC cannot establish which happened
first. The result is AMBIGUOUS_WITHIN_DAILY_BAR; it is never guessed.

Gap-cross ambiguity, invalid OHLC, missing sessions, untrusted previous close, identity/roll/calendar
or temporal blockers remain fail-closed and do not yield a binary first-passage outcome.

## Audit / calibration semantics

FIRST_PASSAGE is an independent OutcomeRecord.outcome_kind and an independent label_scope. It is no
longer evaluated as TOUCH.

A categorical result may be converted to a binary target (UPPER_FIRST, LOWER_FIRST, or NEITHER) only
when the categorical status is OBSERVED. Ambiguous or unobservable results remain value=None.

This allows W3/W4 to accumulate and calibrate first-passage event probabilities without conflating
them with ordinary touch probabilities.

## Evidence boundary

Engine tests are synthetic contract tests only. They do not establish a market first-passage
probability, calibration quality, or trading edge.
