# IMPLEMENTATION ROADMAP (V2)

Dependency-ordered. Phase boundaries are **draft** and must be re-sequenced by the final audit
conclusion. No implementation is started in this audit phase.

## Phase ordering rationale

Data truth → session semantics → labels → state machine → extension/exhaustion → catalyst →
sequential updating → audit DB → calibration → order flow (only if data supports it).

## Proposed phases

| Phase | Name | Depends on | Output (design intent) |
|---|---|---|---|
| V2-A | As-Of / Timestamp / Data Truth | — | canonical `event_timestamp / observed_at / source_timestamp / ingested_at / feature_cutoff_timestamp / forecast_origin`; point-in-time loader |
| V2-B | Intraday Session + Gap Decomposition | V2-A | session semantics, gap/overnight decomposition, time-of-day regimes |
| V2-C | Label Engine (Touch/Break/Acceptance) | V2-B | barrier/event labels, acceptance definitions (research) |
| V2-D | Dynamic State Machine | V2-C | 4-layer state + chase risk + transition log |
| V2-E | Extension / Exhaustion | V2-D | extension & exhaustion features/states |
| V2-F | Catalyst Response | V2-A | cross-market lead-lag, response residual, decay |
| V2-G | Sequential Updating / Change Point | V2-D | probability velocity/accel, CUSUM/Bayesian challenger |
| V2-H | Prediction Audit DB | V2-A | persist forecast_origin, cutoff, snapshots, versions, actual outcome |
| V2-I | Calibration / Evaluation | V2-C/V2-D | Brier/log-loss/calibration-curve/early-warning metrics |
| V2-J | Order Flow | data-only | only if L1/L2/order-event data is licensed |

## Priority principle

V2 Core = `As-Of Data Layer, Intraday Session Semantics, Gap/Overnight Decomposition, State
Machine, Touch/Break/Acceptance labels, Exhaustion/Extension features, Catalyst Response,
Sequential Updating, Prediction Audit DB`.

`L2/order-event` = `DATA-DEPENDENT` (not in V2 Core).

## Keep LLM late (architecture invariant)

```
Market Data → As-Of / Feature Store → Quant / Time-Series Models → Regime / Event Models
→ Calibration → Decision/Risk State → Audit → LLM
```

The LLM is a **late explainer**, never the primary numeric predictor.

## Buildable-now vs data-dependent (summary)

| Capability | Class |
|---|---|
| As-Of/timestamp contract, schema | `BUILDABLE_NOW` |
| Gap/overnight decomposition (daily) | `BUILDABLE_NOW` |
| State machine scaffold (daily) | `BUILDABLE_NOW` |
| Touch/Break/Acceptance labels (daily barrier) | `BUILDABLE_NOW` (daily) |
| Prediction Audit DB schema | `BUILDABLE_NOW` |
| Intraday features (1m/5m/…) | `BUILDABLE_AFTER_DATA_WORK` |
| VWAP / session high-low / volume profile | `DATA_DEPENDENT` |
| True order flow / OFI / delta | `DATA_DEPENDENT` |
| 1m Taiwan / 1m Osaka | `DATA_DEPENDENT` |
| L1 / L2 | `DATA_DEPENDENT` |
| Transition probability / time-to-event | `RESEARCH_CHALLENGER` |
| Change-point (CUSUM/BOCPD) | `RESEARCH_CHALLENGER` |
