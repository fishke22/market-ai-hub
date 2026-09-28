# JNU Settlement Forecast / Trading Path / Broker Advisory Architecture Contract

Status: Accuracy v2 closeout contract, 2026-09-27.

## 1. Product separation

MARKET_AI_HUB exposes two different research products. They must never be
silently merged.

### A. Settlement Forecast

- target: `NEXT_PUBLISHED_SETTLEMENT_OBSERVATION`
- instrument identity: exact JPX/OSE JNU contract settlement history
- evidence: Accuracy v2 P1-P5 governance
- governed point champion: zero-return / last official settlement until a
  challenger proves independent forward predictive gain
- output may include development intervals/quantiles but they are not
  calibrated probabilities or support/resistance levels

### B. Trading Path Decision Support

- target: descriptive session/path context, **not** the settlement target
- source: true OSE Nikkei 225 Micro quote observations only
- day/night quote identities are preserved separately
- live/session price, previous session close, observed range, price/volume
  profile, and acceptance are descriptive evidence
- output is qualitative/conditional and is never promoted to predictive gain,
  calibrated probability, or trading edge without a separate preregistered
  evaluation

The two products may be displayed together, but their targets, contracts,
timestamps, provenance, and evidence grades stay separate.

## 2. Price semantics

The following typed values are distinct:

- `TARGET_REFERENCE_SETTLEMENT`: official settlement used by Accuracy v2
  settlement forecasting.
- `TARGET_LATEST_LIVE_OR_SESSION_PRICE`: latest usable true-JNU Micro trade
  observed by the quote-only recorder.
- `TARGET_PREVIOUS_DAY_CLOSE`: verified JNU Micro day closing-auction print
  only when the source timestamp is at the verified OSE close boundary.
- `TARGET_PREVIOUS_NIGHT_CLOSE`: only when a true JNU Micro night observation
  reaches the verified 06:00 JST closing boundary.

A last observed night-session price before 06:00 is **not** a night close.

## 3. Contract identity

- Day `JNU<YYMM>` and night `JNUPM<YYMM>` are session-specific quote
  identities for the same contract month.
- Different contract months are different price series.
- If settlement contract month != decision-support contract month:
  - report `CONTRACT_MISMATCH`
  - do not compute settlement-to-live gap/basis
  - do not call the live price the target settlement contract
- ^N225, Nikkei Large/Mini, CME Nikkei, NQ/ES and all other representations are
  context/proxy only and can never replace the Micro execution state.

## 4. Time and provenance

Each quote observation retains:

- provider
- market_no
- quote code
- normalized contract month
- session identity
- received_at
- source_time_of_day when available
- timestamp quality
- source file provenance

A source time-of-day without date may use the local receive date only for
descriptive session reconstruction, and must be labelled as inferred-date
timestamp quality. It is not upgraded to an exchange-certified timestamp.

Current session state can be unavailable even when historical session data
exists. Closed-market stale observations are historical context, not live
quotes.

## 5. Market structure

The module is descriptive only.

### Trend / Box

A frozen deterministic rule may classify the observed session as:

- `UP_TREND_CANDIDATE`
- `DOWN_TREND_CANDIDATE`
- `BOX_CANDIDATE`
- `MIXED`
- `INSUFFICIENT_DATA`

This classification is not a directional probability and is not a validated
trading signal.

### Price / Volume Profile

- Price Activity Profile may be built from true Micro price observations and is
  explicitly labelled observation activity, not volume.
- Volume Profile requires durable `SubscribeStockTick` provenance with
  `TRADE_TICK + DealPrice + DealVol`.
- Watchlist `Vol` is not accepted as verified trade volume.
- Current archive without those fields => `VOLUME_PROFILE_NOT_AVAILABLE`.
- Price/volume concentration diagnostics are descriptive and are never silently
  relabelled as support/resistance.

### Acceptance

`Touch != Break != Acceptance`.

For an explicitly supplied typed level:

- touch: price range reaches the level
- break: price trades beyond the level
- acceptance: at least two consecutive fixed-frequency bar closes remain on
  the requested side
- retest-hold: a post-break bar revisits the level and still closes on the
  accepted side
- false-breakout: price broke the level but failed the acceptance rule and
  returned to the opposite side

The module does not invent a level. Without a user-supplied or separately typed
level, acceptance status is `LEVEL_REQUIRED`.

## 6. Session coverage

OSE session truth is authoritative:

- day: 08:45-15:45 JST
- night: 17:00-06:00 JST

A verified session close requires an observation at the closing boundary or at
most one second after it, matching the existing OSE close-print evidence
contract. A pre-close observation is never upgraded to a close. Coverage
completeness requires both an opening-boundary observation within one minute and
a verified closing-boundary print; otherwise coverage is partial. Partial night
data cannot be called a night close.

## 7. Event/news context

Immediately allowed:

- existing official event-provider/calendar framework
- dated official-event rows only when they are actually materialized and respect
  available_at/information cutoff
- scenario/risk/abstention annotations

Current local closeout evidence has no `data/events/events.duckdb`, so the
trading-path service reports
`PROVIDER_FRAMEWORK_ONLY_NO_DATED_EVENTS`; it must not imply a populated
event calendar.

Deferred:

- unrestricted live-news ingestion
- LLM/news sentiment as a predictor
- FinGPT/news fine-tuning
- any claim that news context increases predictive accuracy

Status: `LIVE_NEWS_FUSION_DEFERRED_P6`.

## 8. Ensemble wording

The direct settlement model must expose model availability.

- 2+ usable models: `MULTI_MODEL_AVAILABLE_ENSEMBLE`
- exactly 1 usable model: `SINGLE_MODEL_DEGRADED`
- 0 models with baseline fallback: `BASELINE_ONLY`

A single available model must never be described as multi-model consensus.

## 9. Broker advisory boundary

`ITRADER_SMART_ORDER_GUIDANCE` is a final text translation layer:

Market analysis -> suggested risk action -> broker UI guidance.

It is not part of model training or prediction.

Hard rules:

- NO ORDER
- NO TRADING
- NO ACCOUNT ACCESS
- NO POSITION QUERY
- NO BROKER LOGIN
- NO BROKER MUTATION
- no API order methods

Yuanta public material verifies condition-order concepts including stop
profit/loss, moving lock-profit and OCO/two-choice strategies, but current app
screen/menu wording is not treated as a stable API contract. UI mapping is
`PARTIALLY_VERIFIED`.

Personalized closing-side/quantity guidance is generated only from explicit
user-provided position side and quantity. Missing fields remain null/template;
they are never inferred from account state.

For JNU reference conversion:

- tick size = 5 index points
- contract multiplier = JPY10 per point
- 1 tick per contract = JPY50

Every advisory reminds the user to verify the active contract, side, quantity,
validity and strategy state in the broker application's strategy-query screen.
If the user manually reduces/closes a position, they must update/cancel the
standing smart order to avoid an unintended reverse position.

## 10. Evidence boundary

None of this contract changes P2/P5 outcomes or Accuracy v2 promotion gates.

Trading-path structure, event context and broker guidance are:
`DESCRIPTIVE_DECISION_SUPPORT_ONLY`.

They cannot set:
- `PREDICTIVE_GAIN=true`
- `CALIBRATED=true`
- `TRADING_EDGE=true`

without independent preregistered evidence.
