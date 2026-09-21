# Price Map + Probability Map — Research Foundation

> Phase 3A research architecture. **Not a live strategy.** All states/zones/probabilities are
> research semantics; `state_is_trade_instruction = false`.

## Semantic invariants (fail-closed)

1. **Unknown is not Neutral.** No state evidence → `market_state = null`,
   `market_state_status = NOT_EVALUATED` (never `NEUTRAL_ZONE`).
2. **No regime evidence is not Range.** → `regime = null`, `regime_status = NOT_EVALUATED`
   (never `RANGE_LOW_VOL`).
3. **No failure evaluation is not Normal.** → `model_failure_state = null`,
   `model_failure_evaluation_status = NOT_EVALUATED` (never `NORMAL`).
4. **No samples is not Empirical distribution.** `sample_size = 0` → `method = NOT_ESTABLISHED`
   (never `EMPIRICAL`); calibration `INSUFFICIENT_EVIDENCE` (never `UNCALIBRATED` when no
   distribution exists).

Target families are isolated: `TAIWAN_STOCK` / `TAIWAN_INDEX` / `OSAKA_MICRO` have distinct
profiles; unknown family fails closed (no cross-family fallback).

## Typed evidence invariants (3A.2)

1. **Available is not Validated.** `AVAILABLE` probability requires value validity + calibrated
   (map **and** zone) + sufficient sample + complete provenance + capability support.
2. **Map calibrated is not Zone calibrated.** Both must be `CALIBRATED`; otherwise no public %.
3. **Terminal calibrated is not Touch calibrated.** Each probability type has its own
   calibration status; one does not vouch for another.
4. **Enum input is not Evaluation Evidence.** `market_state="BUY_ZONE"` without a valid
   `EvaluationEvidence` is `UNVERIFIED`, never `EVALUATED`.
5. **Quantile boundary is not Zone Probability.** `buy_zone_upper_quantile=0.25` does **not** mean
   `P(BUY_ZONE)=25%`.
6. **1d calibration is not 5d calibration.** Calibration is instrument/family/horizon-scoped.

Capability matrix (`distribution_capability`):

| capability | terminal | touch | first_passage |
|------------|----------|-------|---------------|
| `NONE` | no | no | no |
| `QUANTILES_ONLY` | no | no | no |
| `TERMINAL_SAMPLES` | yes | no | no |
| `TERMINAL_DISTRIBUTION` | yes | no | no |
| `PATH_SAMPLES` | yes | yes | yes |
| `PATH_DISTRIBUTION` | yes | yes | yes |
| `FULL_DISTRIBUTION` | yes | no | no |

## Adversarial contract closure (3A.2.1)

Schema version `3A.2.1`. Closes the failure modes where a well-formed but out-of-scope or
unsupported probability could surface as a public number.

1. **Scope is enforced, not assumed.** A probability is public only when its
   `ProbabilityProvenance` matches the map on normalized `target_family` / `instrument` / `horizon`.
   Any mismatch → `NOT_AVAILABLE_SCOPE_MISMATCH` with `TARGET_/INSTRUMENT_/HORIZON_SCOPE_MISMATCH`
   reason codes. (`1D`≡`1d`, `3706`≡`3706.TW`.)
2. **Sample sufficiency is numeric.** `SUFFICIENT` requires `minimum_required_sample > 0` **and**
   `sample_count >= minimum` **and** `effective_sample_count >= minimum`. A zero-sample record
   labelled `SUFFICIENT` is rejected → `INSUFFICIENT_SAMPLE`.
3. **Public status is derived, never echoed.** `ProbabilityValue.status` is internal; the public
   status is computed from the gate chain (`NOT_AVAILABLE_<REASON>`). `AVAILABLE` in the internal
   record does not leak out.
4. **Reason codes are truthful.** Every failed gate appends its code; the public view carries the
   full accumulated list.
5. **Enums normalize or reject.** `VALID`/`ESTABLISHED` → `EVALUATED`; unknown values raise.
   `EvaluationEvidence.is_valid()` requires `method_version` + `data_version` + `evaluated_at` +
   `source` + `sample_count`.
6. **Method ↔ capability consistency.** A distribution method may only claim capabilities in
   `METHOD_CAPABILITY_RULES`; e.g. `QUANTILES_ONLY` cannot claim `PATH_SAMPLES`.
7. **Path is a hard gate.** `touch` / `first_passage` require a path-capable distribution **and**
   complete path metadata (`path_count`, `steps_per_path`, `bar_frequency`,
   `target_market_calendar`, `session_semantics`, `generation_method`). `FULL_DISTRIBUTION` is
   terminal-only and never implies path.
8. **Calibration is scoped.** `SINGLE_INSTRUMENT` / `PANEL` / `GLOBAL` each require their own
   evidence; a panel/global calibration without matching scope evidence grants nothing.
9. **Provenance is cross-checked.** `distribution_method` must match the distribution record;
   calibration method/version must be present.

## Distribution evidence closure (3A.2.2)

Schema version `3A.2.2`. Closes the case where the distribution record — the actual evidence
source — was not part of the public eligibility chain.

1. **Three-way scope contract.** Public probability requires
   `MAP == PROVENANCE == DISTRIBUTION` on canonicalized `target_family` / `instrument` / `horizon`.
   Distribution mismatch → `DISTRIBUTION_TARGET_/INSTRUMENT_/HORIZON_SCOPE_MISMATCH`.
2. **Distribution scope cannot be empty.** Any non-`NONE`/`QUANTILES_ONLY` distribution must carry
   non-empty scope, else `MISSING_DISTRIBUTION_SCOPE`.
3. **Distribution-level numeric sample gate.** `TERMINAL_SAMPLES` / `PATH_SAMPLES` require
   `minimum_required_sample > 0` and both counts ≥ minimum and `SUFFICIENT`; else
   `DISTRIBUTION_INSUFFICIENT_SAMPLE`. A `ProbabilityValue` can no longer self-declare sufficiency
   while the underlying distribution has zero evidence.
4. **Probability sample cannot exceed its source.** `TERMINAL_SAMPLES`: `pv.sample_count` ≤
   `distribution.sample_count` (same for effective). `PATH_SAMPLES`: path basis ≤ `path_count`.
   Violation → `PROBABILITY_SAMPLE_EXCEEDS_SOURCE`.
5. **Analytic vs sampled.** `TERMINAL_DISTRIBUTION` / `PATH_DISTRIBUTION` may be analytic/model-based
   and are not forced to carry Monte Carlo samples; their calibration evidence still must be real.
6. **Distribution identity.** `distribution_id` / `distribution_version` must be present for a
   public probability and must match the provenance (`MISSING_DISTRIBUTION_IDENTITY` /
   `DISTRIBUTION_IDENTITY_MISMATCH`). Two distributions sharing only a `method` are not the same
   evidence.
7. **Market calendar / session isolation.** A central validator maps
   (`target_family`, `instrument_role`) → (`target_market_calendar`, `session_semantics`):

   | family | role | calendar | session |
   |---|---|---|---|
   | `TAIWAN_STOCK` | DIRECT | `XTAI` | `day` |
   | `TAIWAN_INDEX` | DIRECT | `XTAI` | `day` |
   | `OSAKA_MICRO` | DIRECT | `OSE_DERIVATIVES` | `day+night` |
   | `OSAKA_MICRO` | PROXY | `XTKS` | `day` |

   Mismatch → `MARKET_CALENDAR_MISMATCH` / `SESSION_SEMANTICS_MISMATCH`. A Taiwan stock path can
   never use OSE day/night semantics; a direct Osaka Micro path can never use `XTKS`; an `^N225`
   proxy uses `XTKS` but must be `PROXY_MODEL_REFERENCE`.
8. **Typed calibration-scope reasons.** `PANEL` / `GLOBAL` scope failures report
   `CALIBRATION_SCOPE_EVIDENCE_MISSING`, `CALIBRATION_UNIVERSE_MISMATCH`, or
   `CALIBRATION_GLOBAL_SCOPE_MISMATCH` — never a bare `UNCALIBRATED`.
9. **Extended eligibility checks.** `ProbabilityEligibilityResult.checks` now exposes
   `capability`, `value`, `probability_sample`, `distribution_sample`, `provenance`,
   `provenance_scope`, `distribution_scope`, `distribution_identity`, `market_semantics`,
   `calibration`, `calibration_scope`, `path`. Any critical check false → `eligible=false`.



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
