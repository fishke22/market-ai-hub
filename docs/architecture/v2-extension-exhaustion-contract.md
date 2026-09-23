# V2 Extension / Exhaustion Contract

- **Schema**: `V2_EXTENSION_EXHAUSTION_SCHEMA_VERSION = "2E.1"` (module
  `src/market_ai_hub/research/v2/extension_exhaustion.py`)
- Independent from `2A.1` / `2B.1` / `2C.2` / `2D.3` / `3A.2.3`.

## Scope

`DAILY_RESEARCH_PROXY`. Daily OHLC/ATR only. No intraday extension, no VWAP/session-high-low, no
time-at-high/low, no intraday relative volume, no order flow.

## Canonical extension definition

`reference_kind = PREVIOUS_CLOSE` (current completed daily close vs previous completed daily close,
normalized by a PRIOR ATR baseline):

```
signed_extension_units   = (current_close - previous_close) / atr_baseline
absolute_extension_units = abs(signed_extension_units)
extension_side           = UP / DOWN / FLAT
extension_state:
  abs_units <  1.0  -> NORMAL
  1.0 <= abs_units < 2.0 -> EXTENDED
  abs_units >= 2.0  -> EXTREME
```

ATR units are NOT σ / z-score / probability. ATR baseline is pre-move:
`atr_event <= previous_close_event < current_close_event`, and every
`event <= available <= cutoff <= origin`.

## Research thresholds (1 / 2 ATR)

`extended_threshold_atr = 1.0`, `extreme_threshold_atr = 2.0`. Both `HYPOTHESIS_ONLY` /
`NOT_OPTIMIZED`. No grid search / Optuna / PnL selection / 2026-09-22 single-day tuning.

## Invariants

- `EXTENSION != EXHAUSTION`; `EXTENDED`/`EXTREME` alone never imply exhaustion.
- `extension_side` (UP/DOWN) is NOT Direction/Bullish/Bearish/Long/Short.
- `EXHAUSTION_WARNING != REVERSAL / BEARISH / CHASE_STOP / SHORT / SELL`.
- No probability, no trade semantics.

## Exhaustion Warning rule

Warning established only when: extension ∈ {EXTENDED, EXTREME} **and** >= 2 distinct trusted
positive confirmation families. Families: `MOMENTUM_STALL`, `PRICE_VOLUME_DIVERGENCE`,
`STRUCTURAL_FAILURE`, `OSCILLATOR_EXTREME`. Multiple evidence rows of the SAME family count once
(no oscillator vote-stuffing). A family with both `present=True` and `present=False` trusted rows
→ `CONFLICT` (no warning). `UNKNOWN`-provenance components are lineage-preserved but not counted.
Insufficient confirmation → `INSUFFICIENT_CONFIRMATION`, never a false `RISK=NORMAL`.

## State-machine integration (V2-D 2D.3)

- `extension_to_state_evidence` → `layer=EXTENSION`, `value∈{NORMAL,EXTENDED,EXTREME}`, only when
  `EVALUATED`.
- `exhaustion_to_state_evidence` → `layer=RISK`, `value=EXHAUSTION_WARNING`, only when
  `WARNING_ESTABLISHED`; otherwise `None` (never emits `RISK=NORMAL`).
- Generated evidence: `provenance_status=VERIFIED_INPUT`, `validation_status=HYPOTHESIS_ONLY`,
  deterministic `evidence_id`.
- Exhaustion Warning does NOT alter Direction, does NOT set CHASE_RISK, is NOT REVERSAL_RISK.

## Capability matrix

```
DAILY_ATR_EXTENSION:                     ENGINE_AVAILABLE
DAILY_EXHAUSTION_COMPONENT_AGGREGATION:  ENGINE_AVAILABLE
INTRADAY_EXTENSION_FROM_OPEN:            DATA_DEPENDENT
VWAP_EXTENSION:                          DATA_DEPENDENT
SESSION_HIGH_LOW_EXTENSION:              DATA_DEPENDENT
TIME_AT_HIGH_LOW:                        DATA_DEPENDENT
INTRADAY_RELATIVE_VOLUME:                DATA_DEPENDENT
VOLUME_PROFILE:                          DATA_DEPENDENT
ORDER_FLOW_EXHAUSTION:                   DATA_DEPENDENT
```

## Actual data limitations

OSAKA_MICRO: daily OHLCV field-capable but roll/calendar/session provenance incomplete → NOT_READY.
TAIWAN_STOCK: FIELD_READY_ONLY. `^N225`: close-only → ATR requires high/low → DAILY_ATR_EXTENSION
NOT_READY. TAIWAN_INDEX: NOT_AVAILABLE_LOCAL_DATASET. ENGINE PASS != MARKET VALIDATION !=
PREDICTIVE EVIDENCE != TRADING EDGE.
