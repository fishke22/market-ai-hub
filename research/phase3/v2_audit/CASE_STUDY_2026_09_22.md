# CASE STUDY — 2026-09-22 (Osaka / Taiwan "high-open then fade")

**RESEARCH CASE STUDY ONLY.** This single-day case must **not** be reverse-engineered into a
permanent rule. No model is required to "predict the drop".

## Fact classification

| Claim | Classification | Verification |
|---|---|---|
| 2026-09-22 is a Japan cash holiday (TSE closed) | `OFFICIAL_VERIFIED_FACT` | JPX holiday-trading schedule + `config/ose_derivatives_calendar.yaml`; IC Markets + OfficeHolidays confirm 2026-09-21 Respect-for-Aged Day, 2026-09-22 Citizens' Holiday ("Silver Week"), 2026-09-23 Autumnal Equinox |
| OSE derivatives open via holiday trading on 2026-09-22 | `OFFICIAL_VERIFIED_FACT` | repo calendar `calendar_kind=OSE_DERIVATIVES` + JPX holiday-trading schedule |
| Price levels 66990 / 67045 / 66515 / 66445 / 66282 | `USER_PROVIDED / UNVERIFIED` | intraday OSE micro prices on a holiday-trading day; not verifiable via free official sources |

## Case-study goal (correct framing)

Not "the model must predict down". The question is: **can the system recognize the transition
sequence earlier** —
`Bullish → Bullish Extended → Acceptance Failed → Exhaustion Warning → CHASE_RISK CAUTION →
CHASE_RISK STOP → Direction Downgrade`?

The current system **cannot** express this sequence (no intraday data, no state machine, no
acceptance/exhaustion labels). This is the concrete gap the case exposes.

## System gap exposed by this case

1. No intraday data → cannot observe "high-open then fade" inside the session.
2. No extension/exhaustion state → cannot flag "extended from open".
3. No acceptance/rejection label → cannot detect "failed breakout / failed acceptance".
4. No chase-risk state → cannot warn against chasing an extended open.
5. TSE cash was closed (holiday) → `cash_reference_status` should be `STALE/CLOSED` and
   `basis_comparability` `DEGRADED`; no normal futures-cash basis should be used.

## Normalization (do NOT encode raw prices as rules)

Candidate research transforms (all `HYPOTHESIS_ONLY`): ATR-normalized extension, VWAP-normalized
distance, percentile of range, volatility-adjusted move, time-based, relative volume, distance
from session high, drawdown from local high.

## Anti-overfitting statement

The 2026-09-22 case is a single observation. Any rule derived from it requires historical
backtest + walk-forward + untouched OOS + regime coverage + cost/slippage + calibration +
multiple-testing safeguards before it may be considered.
