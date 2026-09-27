# jerry-backtest-lab → MARKET_AI_HUB integration review

Date: 2026-09-27 (Asia/Taipei)

## Reviewed source

- Source repository: `fishke22/jerry-backtest-lab`
- Reviewed local clone HEAD: `4df8b3a12a4d781fa950e32b4c86298f672e4c2e`
- MARKET_AI_HUB base HEAD: `7525337de28dac64f760ba2fd46101eaf866fc28`
- Review goal: adopt only methods that materially improve correctness, uncertainty handling, or research judgment.
- The reviewed source tree has no top-level LICENSE file. No source code was copied. The accepted method was independently reimplemented using MARKET_AI_HUB's existing numpy/DuckDB stack.

## Useful ideas found

Jerry contains several anti-overfit / robustness concepts that are directionally useful:

- walk-forward selection with explicit commission/slippage;
- cost stress and turnover reporting;
- CPCV with purge/embargo;
- Probability of Backtest Overfitting (PBO);
- Deflated Sharpe Ratio (DSR);
- Holm-Bonferroni multiple-testing control;
- second-engine replay and explicit promotion gates.

These ideas are more valuable than adding another forecasting model because MARKET_AI_HUB's current JNU exact-contract evidence is still a small historical OOS sample and does not beat naive baselines.

## What was adopted

Only one bounded capability was integrated now: **paired uncertainty for same-origin model comparisons**.

MARKET_AI_HUB already compares models only on common valid forecast origins. The new implementation adds a deterministic circular block-bootstrap confidence interval for the paired per-origin metric delta:

- price task: per-origin absolute-error(A) - absolute-error(B);
- direction task: correctness(A) - correctness(B);
- bootstrap block length is derived from overlap of forecast label windows at the evaluated horizon;
- fewer than 5 paired origins: `INSUFFICIENT_PAIRED_SAMPLE`, no CI;
- 5–29 paired origins: CI is computed but explicitly `EXPLORATORY_ONLY`;
- 30+ paired origins: `ESTIMATED`; this still does not imply predictive evidence or trading edge.

The CI, confidence level, block length, replicate count and uncertainty status are persisted in the pairwise DuckDB table, shown by the tournament compare CLI, and exposed through MCP `get_model_leaderboard.pairwise_uncertainty`.

## What was not adopted

### Jerry CPCV / purge / embargo

Not copied. Jerry's implementation purges by row-position day counts around held-out slices. MARKET_AI_HUB already has stricter forecast-origin / label-window / available-at governance. A direct transplant could weaken temporal correctness for heterogeneous horizons or irregular calendars.

### PBO / DSR / Holm

Not added in this package. They are useful when a clearly defined family of strategy/model trials and selection history exists. MARKET_AI_HUB currently needs a canonical trial-family ledger before these statistics can be interpreted without undercounting prior experimentation. Adding formulas before that ledger would create false precision.

### Fixed-bps trading-cost engine / Nautilus replay

Not added to forecast ranking. MARKET_AI_HUB's tournament is primarily forecast-error evaluation, not an executable trading-strategy backtest. Trading cost, spread, slippage, liquidity and fill assumptions remain a separate economic-value layer and must not be used to manufacture predictive evidence.

## Validation

- focused offline regression: `90 passed, 4 deselected`;
- full offline first pass: `1976 passed, 1 skipped, 34 deselected, 1 failed`; the only failure was the existing Windows global SPARK owner mutex test while the live quote recorder held the single-owner lock;
- final offline profile excluding only that live-owner-conflicting test: `1976 passed, 1 skipped, 35 deselected, 110 warnings in 185.06s`, exit 0;
- no broker login/logout/restart/order/account action was performed;
- no new dependency was added.

## Interpretation

This change does **not** make the current JNU models more accurate by itself. It improves the system's ability to judge whether an observed model-vs-baseline difference is robust enough to take seriously. In particular, the current 10-origin JNU historical OOS comparison remains exploratory rather than being promoted because a point estimate happens to favor one model.
