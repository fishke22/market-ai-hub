# MARKET_AI_HUB — Architecture V2 FREEZE (formal)

- **Status**: FORMAL FREEZE (was `MARKET_AI_HUB_ARCHITECTURE_V2_FREEZE_DRAFT` under `research/phase3/v2_audit/`)
- **Date**: 2026-09-22
- **V2-A gate**: `PHASEV2A_ASOF_DATA_TRUTH_PASS`
- **Baseline**: main `1ba46e9fa23478ec622395274c50d9d283a30141`; V2 as-of schema `2A.1`; build_id `65abb3af1b561afc`

The audit (Phase 3-V2) is complete. This document freezes the V2 architecture into
**CORE_V2 / RESEARCH_CHALLENGER / DATA_DEPENDENT / DEFERRED** categories. The as-of/timestamp/
data-truth foundation (V2-A) is the first constructed phase.

## CORE_V2

1. As-Of Data Layer
2. Timestamp / Session Truth
3. Gap / Overnight Decomposition
4. Multi-Horizon Architecture
5. Touch / Break / Acceptance separation
6. Dynamic State Machine
7. Extension / Exhaustion
8. Catalyst Response
9. Sequential Updating
10. CHASE_RISK_STATE
11. Prediction Audit lineage
12. Calibration / OOS governance
13. LLM late-stage interpretation

## RESEARCH_CHALLENGER

- Dynamic Beta
- Online Change Point variants (CUSUM / Page-Hinkley / Bayesian Online Change Point)
- HMM / HSMM
- Survival / Hazard
- Competing Risks
- Multimodality diagnostics
- Advanced catalyst saturation
- State-transition probability

Not implemented now; retained in research backlog.

## DATA_DEPENDENT

- True 1m intraday
- Tick
- L1
- L2
- True OFI
- Cumulative delta
- Depth imbalance
- Cancellation dynamics
- Full order-book microstructure

All blocked on licensed data (audit truth: no intraday / L1 / L2 / order events exist).

## DEFERRED

Items with no current evidence, high cost, non-core, or insufficient data are kept in backlog —
**not deleted**. Examples: non-core order-flow, additional LLM layers beyond late interpretation,
Phase 3B.1 terminal predictive distribution (until V2 data foundation is ready).

## Dependency order (V2)

V2-A As-Of/Timestamp/Data Truth → V2-B Daily Gap/Overnight + Session Truth → V2-C Multi-Target
Label Engine (Touch/Break/Acceptance) → V2-D Dynamic State Machine Scaffold → V2-E
Extension/Exhaustion → V2-F Catalyst Response → V2-G Sequential Updating/Change Point → V2-H
Prediction Audit Database → V2-I Calibration/Evaluation → V2-J Intraday (after data capability) →
V2-K Order Flow (after L1/L2/order-event).

Phase 3B.1 (Terminal Predictive Distribution) = `DEFERRED_PENDING_V2_DATA_FOUNDATION`; not started.

## Change control

Any new idea must follow:

```
Idea → Research Backlog → Data Check → Label Feasibility → Leakage Review
→ Architecture Compatibility → Formal Phase Approval
```

New ideas must **not** be inserted into an active construction phase.

## Invariants

1. LLM is a late explainer, never the primary numeric predictor.
2. `CALIBRATED` is evidence-derived, not caller-declared.
3. Distribution samples ≠ probability samples ≠ calibration samples.
4. Direction state is separate from CHASE_RISK_STATE (`STOP ≠ SHORT`).
5. Terminal calibration ≠ touch calibration (type-specific).
6. A prior-day US close is not a live intraday signal.
7. OHLCV-only must not claim true order-flow.
8. Single-day cases do not become permanent rules.
9. V2 canonical timestamps are tz-aware UTC; naive datetimes are rejected.
10. Data capability registry is truthful: 1m / L1 / L2 remain unavailable until actual data appears.