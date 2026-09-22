# MULTI-TARGET LABEL DESIGN (V2)

**Design only — no label implementation.** Defines the probability/label families V2 should
support, strictly separated from the current 3-class direction label.

## Current label (verified, unchanged)

- Regression: `future_return_k = close.shift(-k)/close - 1` (`features/features.py:93`).
- Classification: 3-class `>threshold / flat / <-threshold`, threshold 0.005 (`make_classification_labels`, `baseline_ml.py`).

## New label families (design)

| Label | Definition candidate | Data requirement |
|---|---|---|
| Direction Probability | P(close_T+h > close_0) | daily OK |
| Touch Probability | P(hit level L before expiry) | needs intraday barrier tracking |
| Break Probability | P(close beyond L) | daily OK |
| Acceptance Probability | P(break holds — see acceptance def) | intraday |
| Profit-Taking Probability | P(mean-revert from extended) | intraday extension |
| Exhaustion Probability | P(momentum stall given extension) | intraday |
| Reversal Probability | P(direction flip) | daily/intraday |
| Reclaim Probability | P(level reclaimed after loss) | intraday |
| Re-Acceptance Probability | P(re-accept after rejection) | intraday |
| Failed Breakdown Probability | P(breakdown fails and reclaims) | intraday |

## Event chain (strict separation)

```
Touch
  ├── Break          (touch resolves into break)
  └── Reject         (touch rejected)
Break
  ├── Acceptance     (break holds)
  └── Failure        (break fails / fade)
Acceptance
  ├── Continuation
  └── Reversal
```

Conditional probabilities to research (no fitting): `P(Break|Touch)`, `P(Acceptance|Break)`,
`P(Continuation|Acceptance)`, `P(Rejection|Touch)`, `P(Failure|Break)`.

## Acceptance definition candidates (all `HYPOTHESIS_ONLY`, no winner selected)

1. time-above-level (e.g. ≥ N bars above)
2. N consecutive closes above level
3. close-above ratio over a window
4. volume above level
5. successful retest (pullback to level holds)
6. VWAP location (price vs VWAP relative to level)
7. ATR-normalized distance held beyond level

Each must be backtested + walk-forward + OOS + calibrated; none is pre-selected.

## Multi-horizon (design)

Horizons: `1m, 5m, 15m, 30m, 60m, Session Close`. Different horizons may hold different states
simultaneously; a long horizon must **not** override a short horizon.

## Gap / overnight decomposition (design)

Segments: `previous close → current open`, `open → 30m`, `30m → 60m`, `open → session close`,
`close → close`. Classification: `gap-up continuation / gap-up fade / gap-down continuation /
gap-down recovery`.

## Label anti-overfitting

All labels are `HYPOTHESIS_ONLY`; future validation requires historical backtest + walk-forward +
untouched OOS + multiple-testing safeguards + cost/slippage + calibration. The 2026-09-22 case
must not be encoded as a permanent rule.
