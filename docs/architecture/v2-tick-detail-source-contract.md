# W3.3 Yuanta SPARK Tick-Detail Source Contract

- **Schema**: `W3_TICK_DETAIL_SOURCE_SCHEMA_VERSION = "W3.3"`
- **Parser / readiness**: `src/market_ai_hub/research/v2/tick_detail_source.py`
- **Typed SPARK query**: `SparkRuntime.request_tick_detail_last()`
- **Downstream consumer**: W3.2 dedicated contract DAILY terminal-close feature
- **Current state**: source/materializer/controlled-measurement path offline PASS; one authorized real raw measurement was captured; C2.3 typed runtime re-verification is still **REQUIRED** before DAILY materialization.
- **Research only**: quote query only; no order, account balance, position, trading or calibration fitting.

## Why this source exists

W3.2 needs an exact contract-level terminal close with a complete event timestamp. The current streaming
recorder persists `DealPrice`, `SettlementPrice` and source time-of-day, but it has no separate
`ClosePrice` field and its streaming payload does not provide a full source event date. W2 correctly
refuses to combine a receipt date with a source time-of-day.

The vendor contract distinguishes ordinary deal price from settlement price. Neither is silently
renamed to terminal close.

The official SPARK quote API also exposes `GetStkTickDetail` ("當日分時明細查詢"). Its response
contains market, contract code and per-trade `TimeStamp`, `DealPrice`, `DealVol`, bid/ask,
sequence number and in/out flag. Local vendor `FunctionList.xlsx` confirms that this is a quote-class
request. It is not an order/account method.

## Query contract

W3.3 adds one explicit bounded method; there is still no generic method invoker:

```text
GetStkTickDetail(
  Account,
  MarketType,
  StkCode,
  SelectType = LAST_COUNT (1),
  Stime = 00:00:00,
  Etime = 23:59:59,
  LastCount <= 20,
  Language = UTF8
)
```

A synchronous boolean means only request acceptance. A matching
`OnResponse(..., strIndex="GetStkTickDetail", ...)` callback is required to prove a result.

Input validation rejects an empty account, malformed/oversized contract code and `LastCount` outside
1..20. The runtime exposes a separate typed tick-detail callback. No order/account/balance method was
added.

## Timestamp rule: fail closed

`StickDetail.TimeStamp` is parsed as a complete calendar/date-time value but intentionally remains
timezone-naive. The available official documentation and local `FunctionList.xlsx` do not document
the timezone basis of the OSE result strongly enough to convert it to UTC without a runtime check.

Therefore:

```text
current timestamp basis = UNVERIFIED_OSE_TIMESTAMP_BASIS
terminal_close materialization = FORBIDDEN
```

No code path in W3.3 turns an unverified timestamp into the W3.2
`terminal_close / w3.2-contract-daily-close-1` feature.

## OSE verification window

The bounded runtime check is designed for the deterministic interval after the OSE day session has
closed but before the next night session starts:

- 15:45 Asia/Tokyo: day-session close;
- 17:00 Asia/Tokyo: night-session open;
- request window: **15:45 <= local time < 17:00** on a verified OSE derivatives session date.

This avoids inferring a session date from an arbitrary intraday callback.

## Required runtime evidence

Before timestamp basis can change to `RUNTIME_VERIFIED_OSE_LOCAL`, a controlled maintenance-window
probe must establish all of the following on the existing single-owner quote connection:

1. same OSE contract query is accepted;
2. matching `GetStkTickDetail` response arrives;
3. returned market number and contract code match the request;
4. `StickDetail.TimeStamp` basis is cross-checked against verified OSE session/local clock semantics;
5. the probe occurs after 15:45 JST and before 17:00 JST;
6. no second broker owner/login is created.

The reviewed C2 materializer now exists in `terminal_close_materializer.py`. It still cannot promote
a real row until a persisted, valid `W3.3-C2.3` runtime evidence artifact is present. The raw
`TickDetailBatch` never self-upgrades its verification status.


## Same-owner controlled measurement path

C2 adds a control-inbox action that can run `GetStkTickDetail` only inside the already-running
`live_quote_recorder` owner. It does **not** create a second login.

- config block: `tick_detail_measurements`;
- default: `enabled: false`;
- operator queue script: `scripts/request_yuanta_tick_detail_measurement.ps1`;
- only market 207 and exact `JNU\d{4}` contracts are accepted;
- `LastCount` remains capped at 20;
- request and callback must both be inside `15:45 <= JST < 17:00`;
- any unmatched prior tick-detail request blocks a new measurement;\n- the same market/code cannot be retried in the same recorder process, avoiding delayed duplicate callback mis-correlation;
- evidence/raw paths must remain under the recorder root;
- the recorder freezes its `runtime_build_id` at process startup and refuses measurement if the
  current disk build differs, preventing a stale process from claiming newer code provenance;
- raw trade values remain local in a canonical raw artifact; control results and typed verification
  evidence are metadata-only and expose no prices.

The runtime-basis cross-check is deliberately conservative. A valid same-day near-close trade must
be causal when interpreted as `Asia/Tokyo`, while interpreting the same raw clock as UTC must be
inconsistent with the callback time. UTC-like and Taipei-like clock examples are rejected in
offline adversarial tests.

`W3.3-C2.3` adds one narrowly bounded closing-auction print rule. JPX documents Nikkei 225 micro
continuous trading through 15:40 and the closing auction at 15:45. Yuanta's official
`GetStkTickDetail` documentation exposes `StickDetail.TimeStamp` as a `DateTime` but does not
document an OSE timezone/auction-second convention. The first real 2026-09-25 JNU2612 C2 probe
returned a canonical batch whose last regular-session row was 15:40:00 and terminal row was
15:45:01. Therefore C2.3 permits **only one second** after the 15:45 session boundary as an
evidence-bounded closing-auction print. `15:45:02` or later remains blocked. The session event
timestamp remains exactly 15:45:00; provider trade timestamp is preserved separately.

References:
- JPX OSE derivatives trading hours: https://www.jpx.co.jp/english/derivatives/rules/trading-hours/
- Yuanta Spark API `GetStkTickDetail`: https://www.yuanta.com.tw/file-repository/content/sparkapi_docs/%E8%A1%8C%E6%83%85/%E7%95%B6%E6%97%A5%E5%88%86%E6%99%82%E6%98%8E%E7%B4%B0%E6%9F%A5%E8%A9%A2/index.html

Persisted raw/evidence artifacts are reloadable. On reload, canonical raw snapshot identity,
evidence integrity ID, exact request/callback binding, build provenance, market/code and controlled
window are checked again before the terminal-close materializer can consume them.

## Evidence boundary

Synthetic CLR-like tests prove parsing, request bounds and fail-closed behavior only. They are not
market evidence and do not prove current account entitlement for `GetStkTickDetail`.

Current evidence state after C2 controlled-path engineering:

- API contract support: documented;
- typed runtime request/callback tracing: implemented;
- raw/evidence persistence + reload validation: implemented; evidence validation recomputes timestamp-basis truth from canonical batch + bound request/callback rather than trusting asserted verification flags;
- reviewed terminal-close materializer + derived DAILY gate: offline PASS;
- same-owner control-inbox measurement path: offline PASS, **default disabled**;
- the mutation entry scripts (start/stop/quote/tick-detail request) now consume the read-only owner preflight before mutation; duplicate/unverified owners, stale build identity, or an invalid measurement gate fail closed;
- one authorized live OSE `GetStkTickDetail` measurement was run through the same-owner foreground path for `JNU2612`; canonical raw snapshot `w33_tick_cbce3cba39291cd1f14e` was captured, and the then-current C2.2 rule correctly blocked its observed `15:45:01` terminal print as `RAW_TRADE_AFTER_DAY_CLOSE`;
- C2.3 now permits only that evidence-bounded one-second closing-auction grace in offline validation, but the blocked C2.2 run did not persist a complete C2.3 typed verification artifact, so **RUNTIME_TIMESTAMP_VERIFIED remains NONE_YET** and evidence must not be retroactively manufactured;
- the current-build safe-default recorder has been observed healthy with W1/W2 per-field provenance and measurement runtime gate=false; outside an authorized maintenance handover it must remain the single owner;
- real eligible W3.2 terminal-close input: **NONE_YET**;
- actual forward prediction evidence: **NONE_YET**.
