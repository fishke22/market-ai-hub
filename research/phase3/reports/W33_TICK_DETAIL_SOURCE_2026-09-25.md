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

Runtime evidence schema `W3.3-C2.2` includes that frozen build ID. The evidence boundary recomputes the OSE-local timestamp-basis cross-check from the canonical raw batch and bound request/callback times, so caller-asserted verified flags cannot promote an invalid batch. Raw tick values are persisted only in the local raw evidence artifact; typed evidence/control results expose metadata and IDs, not prices. Persisted artifacts are reloaded and canonical IDs/bindings are checked again before terminal-close materialization.

Offline validation for this addendum:
- initial controlled-path focused: `70 passed, 2 deselected`;
- review-round focused after final hardening: `74 passed, 1 deselected`;
- related W2/W3/C1/quote regression: `199 passed, 2 deselected`;
- final offline profile, excluding only the live-owner global-mutex test:
  `1854 passed, 24 deselected, 132 warnings in 124.53s`, exit 0;
- targeted changed-file secret scan: 0 hits;
- `git diff --check`: PASS.

No `request_yuanta_tick_detail_measurement.ps1` request was queued in this package.

## Runtime boundary

No broker login/logout, subscription change, live query, recorder restart, order, account, position or
balance action was performed. No scheduler was enabled.

The next live step still requires an explicitly authorized controlled maintenance window. The live
recorder currently has W1/W2 per-field provenance active, but the process was started before the C2
controlled-measurement commit and therefore has not loaded this action. Adoption requires a controlled
restart into the current build plus explicit enablement of `tick_detail_measurements`; the probe must
remain on the same single-owner login. Until that authorization and measurement exist:

```text
W3.3 ENGINE PASS
!= OSE TIMESTAMP BASIS VERIFIED
!= W3.2 DAILY DATA READY
!= FORWARD EVIDENCE
!= CALIBRATED
!= TRADING EDGE
```
