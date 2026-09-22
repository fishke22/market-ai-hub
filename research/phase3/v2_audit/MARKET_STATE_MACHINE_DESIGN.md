# MARKET STATE MACHINE DESIGN (V2)

**Design only — no implementation.** Layered state machine replacing the single 7-class enum.
Human label = composition of layers (e.g. "Bullish but Extended", "Bullish Exhaustion Warning").

## Layer 1 — Directional State

| Value | Meaning |
|---|---|
| `STRONG_BULL` | persistent uptrend, structure intact |
| `BULLISH` | positive bias |
| `NEUTRAL` | no edge / range |
| `BEARISH` | negative bias |
| `STRONG_BEAR` | persistent downtrend |

## Layer 2 — Extension State

| Value | Meaning |
|---|---|
| `NORMAL` | price within normal band |
| `EXTENDED` | price > 1σ ATR/range from reference (VWAP/prior close) |
| `EXTREME` | price > 2σ, exhaustion-prone |

## Layer 3 — Structural State (event-driven)

| Value | Meaning |
|---|---|
| `BREAKOUT_ATTEMPT` | level touched, break being tested |
| `ACCEPTANCE_CONFIRMED` | breakout held, accepted |
| `ACCEPTANCE_FAILED` | breakout faded |
| `REJECTION` | touch rejected |
| `BREAKDOWN_ATTEMPT` | support broken attempt |
| `RECLAIM` | level reclaimed after loss |

## Layer 4 — Risk State

| Value | Meaning |
|---|---|
| `NORMAL` | no elevated risk |
| `EXHAUSTION_WARNING` | extension + volume divergence |
| `REVERSAL_RISK` | structure break + failed acceptance |
| `MODEL_FAILURE` | calibration/coverage failure |

## CHASE_RISK_STATE (separate from Direction)

`CHASE_RISK_STATE ∈ {ALLOW, CAUTION, STOP}`. Directionally independent — `Direction=BULLISH` +
`CHASE_RISK_STATE=STOP` is legal. `STOP ≠ SHORT`.

## State transition log (design)

Per transition record:
`previous_state, new_evidence, trigger, new_state, probability_before, probability_after,
feature_delta, cross_market_delta, invalidation_status, timestamp, model_version`.

## State persistence (anti-flicker)

`minimum_dwell_time, entry_threshold, exit_threshold, confirmation_count, hysteresis`.
No fixed optimal parameter is chosen here (all `HYPOTHESIS_ONLY`).

## Forecast revision (design)

Persist `probability_level, probability_velocity, probability_acceleration`
(e.g. 72% → 68% → 59% → 52% is itself a researchable series).

## Transition probability (research backlog)

`P(Bullish Extended → Exhaustion within 30m)`, `P(Neutral → Acceptance Confirmed)`, etc.
Architecture only; no fitting.

## Time-of-day regime (design)

`Overnight, Pre-open, Open 0-30m, Morning, Midday, Afternoon, Final Hour, Night Session,
US Open Window`. Data support for each is audited in `INTRADAY_DATA_FEASIBILITY.md`.

## State machine interfaces (proposed, not built)

- `evaluate_state(evidence) -> StateSnapshot` (4 layers + chase risk + probabilities)
- `transition(prev, evidence) -> TransitionRecord`
- `persist(StateSnapshot)` (to future Prediction Audit DB)
