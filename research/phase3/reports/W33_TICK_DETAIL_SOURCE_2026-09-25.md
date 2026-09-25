# W3.3 Yuanta SPARK Tick-Detail Source — 2026-09-25

## Result

W3.3 source/query foundation is **PASS**. C2 later added the reviewed materializer and a same-owner
controlled measurement path, both offline-verified. Runtime OSE timestamp-basis measurement is still
**PENDING**, so no real terminal-close input is DATA READY.

Historical W3.3 source-foundation commit: `b56723357e7538309aba096013804781eb0a520c`
Historical build_id: `976bf15b1d5df88f`
C2 correctness commit: `92e178e4ea6cad632d071747efe1c273bcc79efc`
C2 controlled-measurement-path commit: `ed3e63360faca93f6a5a6b0af89fc1ecb51702bf`
C2 correlation-hardening commit: `9496eb9afa65e647b5fceca86610247ff24e258e`
C2 review-hardening commits: `30d32754ff284a6b32370b236ed1fc40283304e9`, `0203e9becf0f0894c3d9f33cfdc2aece448db921`, latest source `873e6bd9697efe1bc2c67d1767c708b23af2df10`
Current source/config build_id: `d0f179c3460497e7`

## Source findings

The existing recorder exposes ordinary `DealPrice`, `SettlementPrice`, OHLC-style quote fields and
source time-of-day. It does not expose a separate `ClosePrice`. The stream therefore cannot be
renamed into W3.2 terminal-close data.

Official SPARK documentation and the locally installed `FunctionList.xlsx` identify
`GetStkTickDetail` as the read-only "當日分時明細查詢" quote request. The result has a full
`TimeStamp` and trade-level fields. However, the reviewed documentation does not establish the OSE
`TimeStamp` timezone basis strongly enough for a UTC conversion.

## Implementation

- added `tick_detail_source.py` schema W3.3;
- parses official-like `StickDetailResult` / row shapes;
- preserves result `TimeStamp` as timezone-naive until verification;
- creates deterministic source snapshot IDs with canonical sorted JSON + SHA256;
- enforces OSE post-close/pre-night query window (15:45 <= JST < 17:00);
- exposes metadata-only candidate/readiness with no prices;
- blocks materialization while timestamp basis is unverified;
- added typed bounded `SparkRuntime.request_tick_detail_last()`;
- `LastCount` is capped at 20; response must arrive through the dedicated
  `GetStkTickDetail` callback;
- no generic invoke and no order/account/balance methods were added.

## Validation

- focused after parser fix: `103 passed`;
- Yuanta/W2/W3 broader: `219 passed, 1 deselected`;
- final canonical-hash focused: `38 passed`;
- final default profile: **1789 passed, 23 deselected, 132 warnings in 178.19s**, exit 0;
- changed implementation/test secret scan: 0 findings;
- `git diff --check`: PASS.

The first focused run had four failures caused by reconstructing nested dataclasses through
`asdict()`; it converted rows to dictionaries. This was corrected with immutable `replace()` and
the focused suite then passed.


## C2 controlled same-owner measurement addendum

The persistent recorder control path now supports an explicit `tick_detail_measurement` action, but
`config/yuanta_live_recorder.yaml` keeps it disabled by default. The action can only execute on the
existing SPARK owner, accepts OSE market 207 + exact `JNU\d{4}` contract + `LastCount<=20`, requires
both request and callback inside 15:45–17:00 JST, blocks outstanding ambiguous requests, rejects a
second same-contract attempt in the same recorder process, validates all evidence paths before touching
the API, and caps the callback wait at five seconds.

The recorder freezes `runtime_build_id` at startup. If disk source/config changes after the recorder
starts, the action returns `TICK_DETAIL_MEASUREMENT_RUNTIME_BUILD_STALE` before a broker query. This
prevents a stale process from attributing evidence to code it did not load.

Historical C2.2 runtime evidence schema `W3.3-C2.2` includes that frozen build ID. The evidence boundary recomputes the OSE-local timestamp-basis cross-check from the canonical raw batch and bound request/callback times, so caller-asserted verified flags cannot promote an invalid batch. Raw tick values are persisted only in the local raw evidence artifact; typed evidence/control results expose metadata and IDs, not prices. Persisted artifacts are reloaded and canonical IDs/bindings are checked again before terminal-close materialization.

Offline validation for this addendum:
- initial controlled-path focused: `70 passed, 2 deselected`;
- review-round focused after final hardening: `74 passed, 1 deselected`;
- related W2/W3/C1/quote regression: `199 passed, 2 deselected`;
- final offline profile, excluding only the live-owner global-mutex test:
  `1854 passed, 24 deselected, 132 warnings in 124.53s`, exit 0;
- targeted changed-file secret scan: 0 hits;
- `git diff --check`: PASS.

No `request_yuanta_tick_detail_measurement.ps1` request was queued in this package.

## C2.3 live-evidence addendum

The 2026-09-25 foreground maintenance path kept the single logical recorder owner alive and produced fresh W1/W2 provenance. Exactly one JNU2612 / LastCount=20 measurement was issued. It persisted canonical raw snapshot `w33_tick_cbce3cba39291cd1f14e`; C2.2 blocked the batch as `RAW_TRADE_AFTER_DAY_CLOSE` because its terminal raw clock was 15:45:01.

Typed reload of that raw artifact passed. The 20 raw timestamps span 15:39:47–15:45:01, with the last regular-session row at 15:40:00 and the terminal row at 15:45:01. JPX documents continuous trading through 15:40 and a closing auction at 15:45; Yuanta documents `StickDetail.TimeStamp` as a DateTime/time field but does not document an OSE auction-second convention. C2.3 therefore adds an evidence-bounded one-second closing-auction grace only. `15:45:02` and later remain fail-closed, and the derived session event timestamp remains exactly 15:45:00 while the provider timestamp is preserved separately.

Current runtime evidence schema is `W3.3-C2.3`; timestamp-basis method is `OSE_SESSION_LOCAL_CLOCK_CROSSCHECK_V2`; current build is `afd52f88a351541a`. Final validation: focused `59 passed`; broader `154 passed, 2 deselected`; full offline `1861 passed, 24 deselected, 132 warnings in 133.26s`, exit 0. The C2.2 blocked result did not persist a complete typed verification artifact, so it is not retroactively upgraded: `RUNTIME_TIMESTAMP_VERIFIED=NONE_YET`, eligible DAILY terminal close=`NONE_YET`, and actual forward evidence=`NONE_YET`.

## Runtime boundary

Historical C2.2 engineering performed no live query in that package; the C2.3 addendum above records the later authorized live measurement. Current truth after C2.3 offline hardening: the foreground Runner path, broker login, fresh W1/W2 provenance, exact-contract request/callback plumbing and canonical raw persistence are all demonstrated. The recorder was gracefully stopped after the one measurement and is currently not running.

The C2.2 measurement cannot be retroactively promoted because its blocked path did not persist a complete typed verification artifact. A future valid OSE maintenance measurement must run the published C2.3 build, persist typed evidence, reload it successfully, and only then permit exact-contract DAILY terminal-close materialization. Until that measurement exists:

```text
W3.3 ENGINE PASS
!= OSE TIMESTAMP BASIS VERIFIED
!= W3.2 DAILY DATA READY
!= FORWARD EVIDENCE
!= CALIBRATED
!= TRADING EDGE
```
