# PHASE V2-E — Daily Extension / Exhaustion Research Engine — REPORT

- **Schema**: `V2_EXTENSION_EXHAUSTION_SCHEMA_VERSION = "2E.1"` (`src/market_ai_hub/research/v2/extension_exhaustion.py`)
- **Baseline**: main = `f73d30b0981fc8c44902257fab2c41eedc00aed9`, build_id `e4a956c16c59b828`.
- **Final build_id**: `fe9b5bf1cfe2f020`.
- **Final tests**: `1234 passed, 20 deselected, 144 warnings`.

## A. Baseline
```
root: D:\MARKET_AI_HUB
branch: main → feat branch
starting HEAD: f73d30b0981fc8c44902257fab2c41eedc00aed9
origin/main: same
working tree: clean → clean
Python: 3.12.13
starting build_id: e4a956c16c59b828
ending build_id: fe9b5bf1cfe2f020
```

## B. Preflight
```
existing extension evaluator: NONE (only V2-D EXTENSION value enum)
existing exhaustion evaluator: NONE
existing ATR: features/features.py::_atr (Wilder EWM alpha=1/n, n=14)
existing RSI: features/features.py::_rsi (n=14)
existing relative volume: NONE
existing divergence: NONE
existing VWAP: NONE
runtime callers: NONE
```

## C. Data boundary
```
DAILY capability: YES (OHLCV)
INTRADAY capability: NO
VWAP: DATA_DEPENDENT
session high/low: DATA_DEPENDENT
relative-volume-by-time: DATA_DEPENDENT
order flow: DATA_DEPENDENT
```

## D. Extension contract
```
schema: 2E.1
scope: DAILY_RESEARCH_PROXY
reference: PREVIOUS_CLOSE
ATR baseline: prior (atr_event <= prev_close_event < curr_close_event)
formula: signed=(curr-prev)/atr; state by abs threshold
NORMAL: <1.0 | EXTENDED: [1.0,2.0) | EXTREME: >=2.0
policy validation: HYPOTHESIS_ONLY
optimization: NOT_OPTIMIZED
```

## E. Exhaustion contract
```
required extension: EXTENDED_OR_EXTREME
confirmation families: MOMENTUM_STALL / PRICE_VOLUME_DIVERGENCE / STRUCTURAL_FAILURE / OSCILLATOR_EXTREME
minimum distinct families: 2
oscillator duplicate rule: same family counts once
conflict behavior: same-family present True+False → CONFLICT (no warning)
warning false semantics: INSUFFICIENT_CONFIRMATION (never RISK=NORMAL)
```

## F. State-machine integration
```
Extension -> layer: EXTENSION (EVALUATED only)
Warning -> layer: RISK / EXHAUSTION_WARNING (WARNING_ESTABLISHED only)
Direction auto-change: NO
CHASE auto-change: NO
REVERSAL_RISK auto-change: NO
```

## G. Actual dataset readiness
```
OSAKA_MICRO: NOT_READY (roll/calendar/session provenance incomplete)
TAIWAN_STOCK: FIELD_READY_ONLY
^N225: DAILY_ATR_EXTENSION_NOT_READY (close-only; ATR needs high/low)
TAIWAN_INDEX: NOT_AVAILABLE_LOCAL_DATASET
```

## H. Synthetic examples
```
A NORMAL:  curr=101 prev=100 atr=2 → +0.5 units → NORMAL
B EXTENDED: curr=103 → +1.5 → EXTENDED
C EXTREME not exhausted: curr=105 → +2.5 → EXTREME, no confirmations → warning NOT established
D WARNING: EXTREME + MOMENTUM_STALL + PRICE_VOLUME_DIVERGENCE → EXHAUSTION_WARNING; Direction unchanged; CHASE unchanged; probability unavailable
```

## I. Changed files
- ADD `src/market_ai_hub/research/v2/extension_exhaustion.py`
- ADD `tests/test_v2e_extension_exhaustion.py` (46 tests)
- ADD `docs/architecture/v2-extension-exhaustion-contract.md`
- ADD `research/phase3/reports/PHASEV2E_EXTENSION_EXHAUSTION_REPORT.md`
- MOD `docs/development/project-status.md`
- MOD `tests/test_challengers_2d1.py` / `test_research.py` / `test_tournament.py` (build_id)

## J. Tests (adversarial)
extreme-alone-not-exhaustion, single-oscillator-insufficient, duplicate-oscillator-family-count-once, requires-two-distinct-families, warning-not-change-direction, warning-not-set-chase-stop, warning-not-reversal, future-outcome-blocks, futures-roll-unknown-blocks, identity-deterministic, component-order-deterministic.

## K. Regression
```
test_v2e_extension_exhaustion.py: 46 passed (exit 0)
v2a+b+c+d+e: 273 passed (exit 0)
phase3a*: 121 passed (exit 0)
full suite: 1234 passed, 20 deselected, 144 warnings (exit 0)
V2-E -W error: 46 passed (no V2-E warnings)
```

## L. Integration status
```
actual market V2-E evaluation: NOT_AVAILABLE (scaffold + synthetic only)
V2-D compatibility: VERIFIED (synthetic compose_state_snapshot)
MCP: NOT_INTEGRATED_THIS_PHASE
V2-F/G/H/I: NOT_STARTED
```

## M. Safety
```
model training: NO
threshold optimization: NO
distribution fitting: NO
calibration fitting: NO
public probability: NO
trade signal: NO
broker/order: NO
new scheduler: NO
persistent audit DB: NO
Phase2 freeze changed: NO
```

## N. Gate
**PHASEV2E_EXTENSION_EXHAUSTION_PASS** (engine contract; actual target data readiness NOT_READY /
FIELD_READY_ONLY / NOT_AVAILABLE — ENGINE PASS != MARKET VALIDATION).

STOPPED AFTER V2-E. V2-F NOT STARTED.
