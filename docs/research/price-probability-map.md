# Price Map + Probability Map — Research Foundation

> Phase 3A research architecture. **Not a live strategy.** All states/zones/probabilities are
> research semantics; `state_is_trade_instruction = false`.

## Purpose

Upgrade from a single `point forecast` + `p10/p50/p90` to a structured research view:

```
Price Map + Probability Map + Regime + Market State + Model Failure Detection
```

The underlying models compute; the LLM interprets in plain language. The LLM must **not** invent
probabilities that the backend did not compute.

## 1. Six research market states

`BUY_ZONE` · `NEUTRAL_ZONE` · `PROFIT_ZONE` · `BREAKOUT` · `BREAKDOWN` · `MODEL_FAILURE`

- `BUY_ZONE` is **not** a buy order; `PROFIT_ZONE` is **not** a sell order.
- `state_is_trade_instruction = false` (machine field).

## 2. Position + behavior

A state engine must not rely on price position alone. It supports:

- `price_position` (which zone)
- `price_behavior_confirmation`

Entering the lower zone ≠ long. Without confirmation evidence:
`confirmation_status = NOT_ESTABLISHED`.

## 3. Regime layer

`RANGE_LOW_VOL` · `BULL_TREND` · `BEAR_TREND` · `HIGH_VOL_EVENT` · `ABNORMAL_MODEL_FAILURE`

Regime influences state interpretation but never becomes a trade order.

## 4. Stock vs futures profiles

Distinct, versioned, OOS-tested parameter profiles:

- `TAIWAN_STOCK_PROFILE` — structural asymmetry research allowed.
- `OSAKA_MICRO_PROFILE` — long/short more symmetric research assumption allowed.

## 5. OSE session features

Osaka futures research must distinguish: day session, night session, TSE cash open/closed,
US close relation, holiday trading, contract roll, SQ, liquidity, spread/slippage regime.
Not all bars are one regime.

## 6. Center semantics

Do not just say "center". Output `predictive_mean`, `predictive_median`, `predictive_mode` when
available. Default graphical center prefers **median**. Under multimodal distributions, mean must
not be presented as the most likely price.

## 7. Probability map

`ZoneProbability` contains: `terminal_probability`, `touch_probability`,
`first_passage_probability`, `availability_status`, `method`, `calibration_status`, `sample_count`,
uncertainty metadata.

- **Terminal** = `P(S_T in Zone)` — needs enough predictive samples / calibrated distribution.
  From `p10/p50/p90` alone, a full zone probability **cannot** be derived →
  `NOT_AVAILABLE_INSUFFICIENT_DISTRIBUTION`.
- **Touch** = `P(price touches zone during horizon)` — different from terminal; needs path
  distribution / validated simulation, else `NOT_AVAILABLE`.
- **First passage** = `P(upper zone first)` vs `P(lower zone first)` — needs a path model meeting
  methodology, else `NOT_AVAILABLE`.

## 8. No fake normal distribution

Gaussian is **never** assumed. Gaussian may only be a `GAUSSIAN_BASELINE_DIAGNOSTIC`. Real
predictive distributions must be empirical/model distributions when available.

## 9. Distribution diagnostics

`skewness`, `excess_kurtosis`, `left_tail_mass`, `right_tail_mass`, `tail_asymmetry`, `mode_count`,
`multimodality_status`, `sample_size`, `method`. Insufficient sample → `INSUFFICIENT_EVIDENCE`.

## 10. Multimodality

Single or multiple modes both allowed; the system must not force a unimodal bell. If multimodal,
the interpreter should say the mean/median cannot fully represent split scenarios.

## 11. Calibration

Any percentage (18% / 42% / 61%) must carry `calibration_status`:
`UNCALIBRATED` · `CALIBRATING` · `CALIBRATED` · `INSUFFICIENT_EVIDENCE`.
If uncalibrated, the public view must not call it a probability.

## 12. Model failure

Model failure is not "price fell below X". It considers: realized outcome outside calibrated
distribution, coverage failure, PIT/calibration drift, forecast-error regime shift, persistent
distribution miss. Versioned rule.

## 13. Price map schema (versioned)

`instrument`, `target_family`, `horizon`, `reference_price`, `distribution_center`, `zones`,
`zone_boundaries`, `market_state`, `regime`, `model_failure_status`, `data_provenance`,
`evidence_status`.

## 14. Zone boundaries

Do **not** declare `q10 = Buy Zone` / `q90 = Profit Zone` as truth. Use a versioned `ZonePolicy`
(configuration); boundaries are research parameters subject to OOS comparison.

## 15. Reward / risk

Research-only `reward_risk_reference`. Current research truth is `NO_ECONOMIC_EDGE`, so public
`actionability_status = NOT_VALIDATED`. It must not become a personalized entry/stop/target.

## 16. Strategy switching (candidate, not instruction)

`RANGE → mean-reversion candidate`; `TREND → breakout/momentum candidate`;
`HIGH_VOL_EVENT → risk-reduction candidate`; `MODEL_FAILURE → suspend-model candidate`.

## 17. Strategy competition framework (versioned, no "best")

Benchmarks: A Buy & Hold · B Moving Average · C Breakout · D Mean Reversion · E Momentum ·
F Price Forecast Only · G Six-State Regime Strategy. Metrics: net return, Sharpe, Sortino,
max drawdown, Calmar, profit factor, win rate, expectancy, tail risk, turnover, costs, slippage.
This phase builds protocol/interfaces/metrics/dataset requirements only — **not** a "G is best" claim.

## 18. Walk-forward + multiple testing

Strategy research is chronological walk-forward, no random shuffle. Train / Validation / Final OOS
strictly separated; final OOS must not be reused for tuning. Because many zone/regime/parameter
variants will be tested, the protocol requires multiple-testing correction (White Reality Check /
SPA test or project-approved equivalent). Never test 5000 variants and claim the best as edge.

## 19. Plain-language LLM contract

The interpreter answers: current zone, current regime, which side has more distribution mass,
whether tail risk is asymmetric, whether multimodal, whether probabilities are calibrated, and what
conditions represent model failure. It must not dump only JSON / raw numbers.

## 20. No "best" claims

Docs and UI must not say `BEST STRATEGY` / `OPTIMAL STRATEGY` / `PROVEN PROFITABLE`. Only
`RESEARCH HYPOTHESIS` / `OOS VALIDATION REQUIRED`.
