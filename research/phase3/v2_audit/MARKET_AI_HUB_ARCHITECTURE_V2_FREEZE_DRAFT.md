# MARKET_AI_HUB ARCHITECTURE V2 — FREEZE DRAFT

**DRAFT ONLY.** Becomes a formal Freeze only after human review of the audit.

## Scope classification

### CORE_V2
1. As-Of Data Layer (canonical timestamp taxonomy + point-in-time loader)
2. Intraday Session Semantics + Gap/Overnight Decomposition
3. Dynamic State Machine (Directional/Extension/Structural/Risk + CHASE_RISK_STATE)
4. Touch/Break/Acceptance label engine
5. Extension / Exhaustion features + states
6. Catalyst Response engine
7. Sequential Updating (probability velocity/acceleration, change-point challenger)
8. Prediction Audit DB (forecast_origin, cutoff, snapshots, versions, actual outcome)

### RESEARCH_CHALLENGER
- Transition probability model
- Time-to-event / survival / hazard / competing risks
- CUSUM / Page-Hinkley / Bayesian Online Change Point
- Cross-market lead-lag stability + response degradation
- Model disagreement / state entropy
- Early-warning metrics (lead time, false/missed warning rate, downgrade delay)

### DATA_DEPENDENT
- Intraday (1m/5m/15m/30m/60m) bars for Osaka/Taiwan
- VWAP / Volume Profile / session high-low (intraday)
- L1 (bid/ask + size)
- L2 (depth)
- Order events (OFI, cumulative delta, cancellation pressure)
- True futures-cash basis on holiday-trading days

### DEFERRED
- Non-core order-flow (until data licensed)
- Additional LLM layers beyond late explanation

## Invariants

1. LLM is a late explainer, never the primary numeric predictor.
2. `CALIBRATED` is evidence-derived, not caller-declared.
3. Distribution samples ≠ probability samples ≠ calibration samples.
4. Direction state is separate from CHASE_RISK_STATE (`STOP ≠ SHORT`).
5. Terminal calibration ≠ touch calibration (type-specific).
6. A prior-day US close is not a live intraday signal.
7. OHLCV-only must not claim true order-flow.
8. Single-day cases do not become permanent rules.

## Change control (future idea process)

```
New Idea → Research Backlog → Data Availability → Label Feasibility → Leakage Review
→ Architecture Compatibility → Formal Phase Approval
```

New ideas must **not** be injected into an in-progress phase.

## Final decision matrix

| Module | Decision | Reason |
|---|---|---|
| V2 Core | GO (schema/design first) | daily data + existing contract foundations sufficient |
| Intraday State Engine | CONDITIONAL_GO | blocked on intraday data; daily scaffold buildable now |
| Multi-Target Labels | CONDITIONAL_GO | daily barrier labels buildable; intraday variants DATA_DEPENDENT |
| Catalyst Response | CONDITIONAL_GO | daily cross-market buildable; live intraday needs data |
| Order Flow | BLOCKED | no L1/L2/order events |
| 1m Taiwan | BLOCKED | no 1m data |
| 1m Osaka | BLOCKED | no 1m data |
| L1 | BLOCKED | no L1 source |
| L2 | BLOCKED | no L2 source |
| Prediction Audit DB | GO (schema) | no data dependency for schema |
