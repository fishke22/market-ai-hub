# MARKET_AI_HUB — PROJECT STATUS

- Current phase: **RESEARCH_DECISION_SUPPORT_LOCAL_PASS / W3.2-EP1 MERGED / W5.1 FIRST_PASSAGE_MERGED / W4.1 CALIBRATION_ENGINE_MERGED / C2.3 AUTOMATION_ADOPTED / ACTUAL_FORWARD_EVIDENCE=NONE_YET / ACTUAL_EVENT_PROBABILITY_EVIDENCE=NONE_YET**
- Gate: **Research stance/conditional research action is now allowed and machine-generated separately from formal validated direction/probability/edge. NO ORDER, personalized size, exact entry/stop/target, and CALIBRATED claims remain gated. Real W3/W4 evidence gates remain closed until eligible samples accumulate.**
- build_id：**e8dc080886d0b5a2**（research decision-support source/config fingerprint；LOCAL_PASS，publication/post-merge live-owner verification pending）
- Schemas：PPM **3A.2.3**；V2 daily label **2C.2**；prediction audit **2H.4**；evaluation governance **W3.1**；forward cycle **W3.2**；raw event producer **W3.2-EP1**；calibration evaluation **2I.1**；calibration fitting **W4.1**；daily first-passage **W5.1**
- Session routing：venue registry（XTAI/XTKS/XNAS/XNYS/CBOE/OSE/TAIFEX/CME/FX/CRYPTO）；no unknown→TWSE fallback
- Factor routing：representation_relation + temporal_role → resolved_role；cross-representation return BLOCKED
- Live quote capability：before this new source package, PR #64 runtime was single-owner and adopted on build **72c6f533e5ae2341**. This branch changes source build to **e8dc080886d0b5a2**; post-merge owner verification/handover is required before claiming runtime=disk for the new package. Measurement gates remain false; no second owner is permitted.
- CUSUM/Page-Hinkley/BOCPD：**NOT_IMPLEMENTED_RESEARCH_CHALLENGER**
- Probability velocity/acceleration：**NOT_AVAILABLE**
- Actual market V2-G sequence：**NOT_AVAILABLE**

## 2026-09-26 research decision-support correction

- Root cause of the CherryStudio refusal: public packet/prompt collapsed `formal validated direction` and `research advice` into one prohibition. `strategy_research_state=WAIT` is still a research gate, but it no longer suppresses a separate qualitative stance.
- Added public `research_decision_support`: `research_stance`, strength, evidence scope, price-ensemble tilt, raw-classifier qualitative tilt, model disagreement, and conditional action framework. Raw classifier scores remain hidden; probability remains unavailable unless calibrated.
- Osaka research stance is PROXY_ONLY and compares model evidence only within ^N225 scope; it never subtracts stale Micro settlement from proxy forecasts. Actual smoke: formal direction unavailable, research stance=`SLIGHT_BULLISH_LEAN`, strength=`WEAK_UNVALIDATED`, current action=`WAIT_FOR_FRESH_DIRECT_CONFIRMATION`.
- Position policy is now `RESEARCH_DECISION_SUPPORT / NO_ORDER`: scenario priority, hypothesis invalidation, wait/refresh, exposure and PnL sensitivity are allowed; placing orders, personalized size, and exact entry/stop/take-profit remain prohibited by system contract.
- Validation: focused=`37 passed`; actual Osaka public smoke PASS; build-freeze=`3 passed`; full offline=`1966 passed, 1 skipped, 35 deselected, 110 warnings`, exit 0.

## 2026-09-26 W3.2-EP1 raw event-probability + MCP/analysis closeout

- Build `72c6f533e5ae2341` locally passes the new W3.2-EP1 producer. Event=`TERMINAL_CLOSE_GT_SOURCE_CLOSE_1D`; first raw sample is Beta(1,1) prior=0.5; subsequent prior counts use only settled outcomes available before forecast origin and only the same exact contract code/month. Every artifact remains `UNCALIBRATED`; `is_public_probability=false`.
- 2H.4 adds optional immutable `event_threshold_value` while preserving legacy artifact hashes when the field is absent. C2.3/W3.2 automatically settles and precommits both POINT and raw EVENT_PROBABILITY scopes from the verified DAILY exact-contract close.
- Feature Store on this machine was non-destructively migrated to schema 2; 547 legacy feature rows were preserved and `factor_observations` exists. Direct Osaka model input now reports `NO_ELIGIBLE_ROWS`, not schema failure.
- FinMind request logging no longer emits token-bearing URLs. Existing local `mcp.log` was scrubbed at 22 occurrences without rotating/changing the credential. Branch-wide changed-file secret scan=0.
- CherryStudio `market-ai` MCP stdio entry remains valid; MCP E2E passed 21 tools / 24 calls / 0 errors. `get_forward_test_status` now exposes W3.2-EP1 registered/settled/pending counts without exposing raw probabilities.
- Validation after exact-contract hardening: event focused `6 passed`; W3/W4/MCP cross `158 passed`; local CI-equivalent `1965 passed / 1 skipped / 35 deselected / 110 warnings`, exit 0. Real samples remain NONE_YET because 2026-09-26 is not an OSE session.
- W7 clean-new-Windows/full-install/WinCred/certificate/COM validation is deferred by user intent and recorded in `FUTURE_RELOCATION_VALIDATION_MEMO.md`; it is not a current financial-analysis gate.

## 2026-09-26 W4.1 + W5.1 final engineering closure

- W4.1: implementation `5ec760a`; PR #61; CI `36240929664` PASS; merged `54542a1443eee9a8a73a130b602abeba0fca941b`. Governed sigmoid fitting consumes only homogeneous W3.1 `FORWARD_PRECOMMITTED EVENT_PROBABILITY` evidence. Validation freezes `EVALUATED_UNCALIBRATED`; a distinct one-use `FINAL_OOS` dataset is required before `CALIBRATED`. Local CI-equivalent `1942 passed / 7 skipped / 35 deselected`; post-merge smoke `61 passed`.
- W5.1: implementation `906a164`; PR #62; CI `36241924593` PASS; merged `37abd2574e59443d6079e24ebc0a639d3713c51e`. Added daily first-passage `UPPER_FIRST / LOWER_FIRST / NEITHER / AMBIGUOUS_WITHIN_DAILY_BAR` and independent FIRST_PASSAGE audit/calibration semantics. Cross-regression `187 passed`; local CI-equivalent `1950 passed / 7 skipped / 35 deselected`; post-merge smoke `187 passed`.
- Runtime: `D:\MARKET_AI_HUB` main equals origin/main; safe-default owner adopted on build `d92e85fec3660b93`. C2.3 Scheduled Task is Enabled, polls every 5 minutes, Last Result=0 on this non-session date.
- Evidence truth at the W4/W5 merge checkpoint: no new real DAILY terminal-close evidence was created on the weekend and W3.2 was POINT-only at that time. W3.2-EP1 now supersedes the producer limitation, but `ACTUAL_FORWARD_EVIDENCE=NONE_YET`; `ACTUAL_EVENT_PROBABILITY_EVIDENCE=NONE_YET`; market `CALIBRATED=FALSE`; trading edge is still not claimed.

## 2026-09-26 C2.3 terminal-close automation + W3.2 exact-JNU operational cycle

- Implementation commit: `b0a26f3`; build remains `35669ded63f487ed`.
- RDC resolved the private-runtime uncertainty: no running owner; one old raw artifact `w33_tick_cbce3cba39291cd1f14e.json`; no typed `verification/` evidence. The old raw file is not promotable.
- Added close-window orchestrator: only an OSE session date and 15:45–17:00 JST can reach broker maintenance. It performs controlled single-owner handover, exact-JNU request, typed-evidence requirement, DAILY materialization, W3.2 settlement/precommit, then restores safe-default quote-only runtime. Automated attempts are capped at three per trading date.
- Added broker-free W3.2 operator to settle pending exact-JNU forward predictions from canonical Feature Store and precommit the next one-session `last_price_naive` baseline. It accepts contract identity only; market values come only from the gated Feature Store.
- The 5-minute timezone-aware C2.3 Scheduled Task is now registered/Enabled and has non-session Last Result=0. The persistent safe-default owner is also adopted; runtime was subsequently handed over through W4 and W5 to build `d92e85fec3660b93`.
- Validation: focused `96 passed, 1 deselected`; broader `198 passed, 2 deselected`; CI-equivalent full `1939 passed, 1 skipped, 34 deselected, 110 warnings in 113.70s`, exit 0; compile/dry-run/diff/secret checks PASS.
- Non-session date today: no tick-detail measurement was sent. Therefore eligible new real DAILY evidence and ACTUAL_FORWARD_EVIDENCE remain NONE_YET.

## 2026-09-26 W3.2 persisted-artifact DAILY terminal-close ingestion

- Implementation commit: `4decd79`; final feature head `262729b`; build `35669ded63f487ed`. PR #58 CI `36234063403` PASS; merged to main as `da73dd288971520e2c765f6660b7d329b89ac79e`; post-merge tree matched and operator smoke `6 passed`.
- Existing verified-tick materializer remains the only source of `terminal_close / w3.2-contract-daily-close-1`; it requires C2.3 typed evidence, OSE near-close timestamp cross-check, exact JNU contract/month, PIT `available_at`, source snapshots, `series_semantics=CONTRACT`, and `source_frequency=DAILY`.
- Added artifact-pair API + offline CLI. No caller-supplied close value is accepted. Canonical IDs/bindings are revalidated; expected-contract mismatch and recorder-root path escape fail closed. CLI output is metadata-only and omits the close value.
- Validation: focused `50 passed`; related `103 passed`; full isolated offline `1924 passed, 7 skipped, 35 deselected, 110 warnings in 81.50s`, exit 0; final operator-only `6 passed`; diff check PASS; changed/untracked secret scan 0.
- No broker action occurred. Private runtime-artifact availability was not reverified because WebCodex blocked that read-only probe; therefore REAL_DAILY_INPUT=NOT_REVERIFIED and no new forward sample/evidence is claimed.
- Next action is evidence-dependent: use an already-existing valid persisted raw/evidence pair offline if available; otherwise a new pair requires separately authorized C2.3 maintenance measurement. Continuous bars/TICK remain ineligible substitutes.

## 2026-09-26 W1 bounded quote reconnect lifecycle

- Reconnect `feeefe3` + JNU base `23504cf` reconciled at `4978f59`; PR #55 merged to main as `a9ab3e55185860c1cc80923d8e9970f37e385d1c`. Build `1037d45ff8e65884`; final docs-only CI `36231436018` PASS; post-merge smoke `29 passed, 21 deselected`.
- No hidden reconnect API is assumed. Recovery is bounded full-runtime replacement: durable flush -> local retire -> fresh Open -> official Connect -> Login result -> full quote re-subscribe.
- Cleanup/re-subscribe failure fails closed; retry/backoff is bounded. Tick-detail maintenance and auto reconnect are mutually exclusive.
- Tracked `auto_reconnect.enabled=false`; JNU microstructure capture remains enabled per its own config. OFFLINE PASS != LIVE ADOPTION.
- Merged validation: focused `29 passed, 21 deselected`; related `150 passed, 2 deselected`; full offline `1918 passed, 7 skipped, 35 deselected, 110 warnings in 84.89s`, exit 0.
- Base PR #55 CI run `36229125508` failed only three stale build-freeze assertions (actual base build `44de914d7d625eb5` vs old expected `b7c1f3d08a383d65`). The merged branch updates frozen assertions to its observed build `1037d45ff8e65884`.
- Next non-live package: W3.2 dedicated contract DAILY terminal-close source/ingestion/aggregation. Preserve PIT/source/contract/month/roll provenance and available_at <= cutoff; continuous series and TICK cannot be silently promoted. Live enablement/restart remains separately authorized.

## 2026-09-26 W1 durable crash spool/WAL

- Implementation commit: `e6bfb35b9b5700bbbb34f845fd059e1870aa2be1`; build `b7c1f3d08a383d65`.
- Tracked config enables bounded fsync-before-accept WAL (`100000` records / `268435456` bytes). Restart validates checksums, contiguous sequence, partial/final recovery, quota and checksummed ack before credentials/runtime construction.
- Deterministic WAL batch IDs + `_wal_seq`/record hash + COMMITTED manifest make Parquet replay idempotent across publish-before-ack crashes. W2 reader rejects durable batches with missing/invalid manifests.
- Ack is an atomic oldest-prefix watermark with checksum; corruption/tampering fails closed. Windows atomic replace has a bounded five-attempt sharing-violation retry.
- Validation: focused `21 passed, 40 deselected`; related `138 passed, 2 deselected`; full isolated offline `1912 passed, 1 skipped, 35 deselected, 110 warnings in 115.04s`, exit 0; diff check PASS; changed-file secret scan 0.
- Boundary: this is disk/offline correctness only. Existing owner runtime remains `afd52f88a351541a`, so live recorder durability is not yet upgraded.
- Exact next offline W1 package: verify and specify automatic reconnect/re-login/resubscribe lifecycle as a bounded single-owner state machine; do not guess unsupported SDK behavior.

## 2026-09-26 W1 SPARK connection-event fail-closed

- Implementation commit: `223ddd88e3a308a21c95176992001041d1eefeb0`; build `1ff1c2adb6bc21bf`.
- Official system-event semantics are explicit: only `intMark=0,dwIndex=1` is Connect. Codes 2/3/4/5 latch DISCONNECTED/NETWORK_ERROR/UPDATE_REQUIRED/NOT_CONNECTED fault state; announcement/other events do not unblock startup.
- Startup connection failure now blocks before Login. A RUNNING fault exits fail-closed as `RUNTIME_FAILED`, records safe connection event metadata, then performs the existing pending-buffer flush attempt and closes/disposes the API.
- Fault remains latched if a later Connect arrives within the same Open because subscription continuity is unknown; a new explicit Open resets state. No automatic reconnect/login/resubscribe loop is implemented or claimed.
- Validation: focused `5 passed`; related `119 passed, 2 deselected`; full isolated offline `1893 passed, 1 skipped, 35 deselected, 110 warnings in 118.83s`, exit 0; diff check PASS; changed-file secret scan 0.
- At this connection-event checkpoint there was no broker action and the live owner was still prior build `afd52f88a351541a`; durable spool was not yet present at that checkpoint. Current durability truth is the newer W1 durable-spool section above.
- Durable crash spool/WAL is now offline PASS in the section above; automatic reconnect remains a separate unadopted lifecycle package.

## 2026-09-26 W1 runtime subscription revalidation

- Implementation commit: `d6d443a1d18989e4826c81ed0fcff835f5295386`.
- Revalidation is periodic (tracked config 300 seconds) and resolves contract expiry against venue-local dates; UTC midnight is no longer used as a session/roll proxy. Failure remains DEGRADED and retries on the next interval.
- Default subscription routing and dynamic ownership are tracked separately. Dynamic overlap survives default roll/removal without duplicate provider calls or accidental unsubscribe; partial provider failures preserve truthful local union state.
- Safe add-before-remove refresh fail-closes before any transient unique-subscription count can exceed 2000.
- Installed DLL reflection: WatchlistAll subscribe/unsubscribe have a third optional `Lng` parameter (default `NORMAL`); bundled vendor Python sample omits it. Explicit `UTF8` remains valid and unchanged. Shared 0.2-second subscribe/unsubscribe throttle remains below the documented rate ceiling.
- Validation: broader `96 passed, 2 deselected`; full isolated offline `1888 passed, 1 skipped, 35 deselected, 110 warnings in 107.43s`, exit 0; `git diff --check` PASS; changed-file secret scan 0. Three build-freeze assertions were updated only after the new fingerprint was observed.
- Boundaries: no broker call in this package; auto reconnect is still not implemented/verified; crash durability remains `BUFFERED_NOT_ZERO_LOSS` without a WAL/durable spool. ENGINE PASS is not DATA READY/CALIBRATED/PREDICTIVE EVIDENCE/TRADING EDGE.
- V2-H：**2H.3 OUTCOME_MATURITY_PASS**；W3.1：**OUTCOME_EVALUATION_GOVERNANCE_PASS**；W3.2：**PRECOMMITTED_FORWARD_CYCLE_ENGINE_PASS / ACTUAL_FORWARD_EVIDENCE=NONE_YET**
- Manual Cherry UAT：**RETEST_REQUIRED**（6 cases）
- Research truth：OSAKA frozen；TAIWAN_STOCK/TAIWAN_INDEX = NOT_YET_VALIDATED（不繼承 Osaka）
- Probability availability：全部 NOT_AVAILABLE（CalibrationEvidence typed gate；無 calibration fitting）
- V2-I：**EVALUATION_FOUNDATION_PASS**（evaluation engine only；CALIBRATION FITTING NOT STARTED）
- Yuanta SPARK securities profile：PR #53 had no callbacks; later local 2026-09-24 matrix records matching TAIFEX/OSE/CME/CBOT/CBOE/NYBOT callbacks. Preserve account_profile=SECURITIES. Source hardening does not re-certify those live observations.
- Yuanta SPARK futures profile：0112 → **SPARK_FUTURES_ACCOUNT_ENTITLEMENT_BLOCKED**（不 retry）

## 2026-09-25 C2 same-owner controlled measurement path

- Initial implementation: `ed3e63360faca93f6a5a6b0af89fc1ecb51702bf`; correlation hardening: `9496eb9afa65e647b5fceca86610247ff24e258e`; review fixes: `30d32754ff284a6b32370b236ed1fc40283304e9`, `0203e9becf0f0894c3d9f33cfdc2aece448db921`, `873e6bd9697efe1bc2c67d1767c708b23af2df10`; maintenance control `4cca09117ffda0fb2ead12de737ffcaf8b92ad9c`; request-script repair `1452a45cf0c4de631d213eaa8648c3eae3b90211`; startup observability `b9cfcb0e302e1520027d2c69adf363d15baf00c4`; C2.3-era build_id at that checkpoint `afd52f88a351541a`.
- New recorder control action `tick_detail_measurement` runs only inside the existing owner. Config default remains `enabled: false`; the queue script does not login/logout.
- OSE market 207 + exact JNU contract + LastCount<=20 only. Actual request and callback must both be inside 15:45–17:00 JST; ambiguous outstanding requests and unsafe evidence paths block before a broker call.
- Recorder freezes `runtime_build_id` at startup and compares it to current disk fingerprint before measurement. Stale process/disk mismatch returns `TICK_DETAIL_MEASUREMENT_RUNTIME_BUILD_STALE`.
- Runtime evidence schema `W3.3-C2.3` binds process build, request/callback identity and canonical raw snapshot. UTC-like/Taipei-like alternatives fail closed. C2.3 permits only `15:45:01` as an evidence-bounded closing-auction print; `15:45:02+` remains blocked and session event time remains 15:45.
- Raw tick values stay in local evidence storage. Control/evidence metadata expose IDs/paths/status, not prices. Persisted artifacts are reloadable and canonical IDs/bindings are checked again before terminal-close materialization.
- Review hardening also makes optional Feature Store provenance queries return [] on DuckDB/IO failure and prevents `LEGACY_TOP_LEVEL_RECEIPT_ONLY` rows from being presented as FRESH in public packet freshness.
- Maintenance-control commit `4cca09117ffda0fb2ead12de737ffcaf8b92ad9c` adds runtime-only tick-detail enable and control-inbox graceful shutdown while keeping tracked `enabled: false`. Startup-observability commit `b9cfcb0e302e1520027d2c69adf363d15baf00c4` adds `startup_stage`, safe error-type/login-code status and start-script confirmation of a fresh running build.
- Validation: startup-observability focused `42 passed, 2 deselected`; broader regression `151 passed, 2 deselected`; final offline profile `1858 passed, 24 deselected, 132 warnings in 125.40s`, exit 0. Targeted secret scan 0; diff check PASS.
- First authorized live attempt: valid OSE session and in-window; FunctionList resolver selected `JNU2612`. Old owner was already absent. One runtime-only owner start exited before fresh status/log.
- Second new user continuation: one new runtime-only start reached `login_msg_code=0001`, `startup_stage=RUNNING`, build `ba7c0e1b9ca9d62c`, measurement gate=true, subscriptions=42 and zero pending/dropped records. The child disappeared after the one-shot Runner command returned, before any fresh callback/W1-W2 provenance. No `START_FAILED`, clean `STOPPED`, recorder stderr/stdout or crash dump was produced. Required measurement preconditions therefore failed; no GetStkTickDetail request and no second login retry occurred in that execution.
- WebCodex continuation rule: run `scripts/start_yuanta_live_recorder.ps1 -Foreground -EnableTickDetailMeasurements` as a long-running Runner Job and keep that exact execution alive while separate calls inspect status / queue the one measurement / send graceful shutdown. Do not use ad-hoc detachment to evade Runner lifecycle controls.
- Third attempt: foreground Runner Job PASS; fresh RUNNING/login `0001`/W1-W2 provenance. Exactly one JNU2612 request `tick-detail-01892509e2e742619eef0c0d07349d39` produced raw snapshot `w33_tick_cbce3cba39291cd1f14e`; C2.2 result = `TICK_DETAIL_TIMESTAMP_BASIS_BLOCKED / RAW_TRADE_AFTER_DAY_CLOSE`. Raw reload PASS; no typed evidence artifact was created.
- C2.3 offline validation: focused `59 passed`; broader `154 passed, 2 deselected`; full offline `1861 passed, 24 deselected, 132 warnings in 133.26s`, exit 0. Third-attempt foreground recorder graceful-shutdown PASS. A later same-build safe-default recorder invocation was then RUNNING with measurement gate=false; current 2026-09-26 runtime/disk truth is the W1 section above.
- C2.3 source commit `3e05af13762d430f875a35f2b288cf33188ce733`; source CI #162 SUCCESS. First C2.3 handoff publication commit `3f4dda90485cf1a86bc16114e2edec40e837eff8`.
- Post-publication regression commit `0d2693f` covers the complete valid C2.3 path for a `15:45:01` print: measurement → persisted raw/evidence → typed reload → exact-contract DAILY materializer. Regression: `38 passed`; broader `155 passed, 2 deselected`; full offline `1862 passed, 24 deselected, 132 warnings in 135.52s`, exit 0. Source/config build is unchanged at `afd52f88a351541a`.
- Bridge regression commit `3ce826817834b20d26d671cd24a0aec8c1821e4a` proves the cross-module offline chain: C2.3 DAILY materializer → Feature Store → W3.2 candidate/precommit; callback availability is enforced; a next-session C2.3 DAILY close then settles the exact-contract prediction and flows through W3.1 evaluation. Focused `45 passed`; broader `158 passed, 2 deselected`; full offline `1865 passed, 24 deselected, 132 warnings in 144.28s`, exit 0. Synthetic evaluation still reports `CALIBRATED=false`, `PREDICTIVE_EVIDENCE=NOT_ESTABLISHED`, `TRADING_EDGE=NOT_ESTABLISHED`; this does not create actual forward evidence.
- Owner-preflight commit `bef25d54ebea22bcb93d8466f657fe7d460496e9` adds a read-only `scripts/check_yuanta_recorder_owner.ps1` that treats the status PID and its matching parent/child chain as one invocation, reports only independent matching chains as duplicate risk, and verifies heartbeat/runtime-build/measurement-gate/tracked-safe-default state. Live classification=`SAFE_DEFAULT_OWNER_HEALTHY`; PowerShell parse PASS; focused `26 passed, 2 deselected`; broader `159 passed, 2 deselected`; full offline `1866 passed, 24 deselected, 132 warnings in 137.11s`, exit 0. No source/config change, so build remains `afd52f88a351541a`.
- Lifecycle-gating commit `639de5f3fe3fda1bcb0c4b31055c3bdf2ab4e930` wires preflight into start/stop before mutation. Healthy existing owner start is idempotent and did not change PIDs; duplicate/unverified/stale-build/tracked-gate states block before new start. Stop with `NO_RUNNING_OWNER` now exits before writing shutdown JSON, so a stale shutdown request cannot be left for a future recorder; duplicate/unverified states block. Focused `27 passed, 2 deselected`; broader `160 passed, 2 deselected`; full offline `1867 passed, 24 deselected, 132 warnings in 141.86s`, exit 0. Build remains `afd52f88a351541a`.
- Request-gating commit `ef59565ebb502957f8d1b9c8e77f39a7ddeaa3af` wires the same preflight into quote/tick-detail request scripts before inbox resolution/creation. Quote requests require a healthy verified RUNNING owner; tick-detail requests additionally require maintenance-owner classification, runtime measurement gate=true, tracked gate=false, runtime/disk build match and no health reasons. Static contract `15 passed, 1 deselected`; broader `158 passed, 2 deselected`; full offline `1868 passed, 24 deselected, 132 warnings in 126.74s`, exit 0. No broker request was queued in validation; build remains `afd52f88a351541a`.
- 2026-09-25 19:25 Asia/Taipei read-only continuation: owner preflight again=`SAFE_DEFAULT_OWNER_HEALTHY`, one parent/child invocation chain, fresh heartbeat, runtime/disk build=`afd52f88a351541a`, both measurement gates=false, no health reasons. PR #55 checks were SUCCESS at the request-gating head. `v2-tick-detail-source-contract.md` stale pre-C2 live-state bullets were reconciled; no broker mutation was performed.
- Actual runtime timestamp evidence = **NONE_YET**; eligible real DAILY terminal close = **NONE_YET**; ACTUAL_FORWARD_EVIDENCE = **NONE_YET**.
- W7.1 reconstruction verifier: reproduced non-repo-cwd FAIL from `%TEMP%` (relative config reads), then a second stale-contract FAIL because current `system_manifest.yaml` correctly uses `build_id: runtime_introspected`. Fixed `reconstruct_verify.ps1` to enter repo root, validate the sentinel, and separately verify runtime `build_fingerprint()`; `%TEMP%` rerun now `RESULT: PASS`. This is current-machine caller-cwd evidence, not new-venv/new-Windows/broker relocation acceptance.
- W7.2 Yuanta portability: removed tracked `D:\MARKET_AI_HUB` / named-user path assumptions from COM check, x86 sidecar setup and local SDK forensics. x86 Python is now launcher/override-driven and validated 32-bit before install; venv/pip failures stop immediately. Read-only COM smoke=`READY_FOR_AUTH`; external `MARKET_AI_DATA_ROOT` with Chinese+space path from non-repo cwd resolved `live\yuanta` correctly. Targeted=`15 passed, 1 deselected`; full offline=`1871 passed, 24 deselected, 132 warnings in 132.68s`, exit 0. Product build unchanged `afd52f88a351541a`; implementation commit=`86cea574927988e78793dd307af2e3351f73e59c`; PR #55 OPEN/MERGEABLE; CI `36133883630` SUCCESS. New-venv/new-Windows/WinCred/certificate relocation still unverified.
- W7.3 main-env relocation bootstrap: reproduced that PATH `python` is 3.11 **32-bit** while `platform.machine()` returns `AMD64`, so the old installer could silently build the wrong main venv. `setup_windows.ps1` now accepts only CPython 3.11/3.12 with actual 64-bit pointer width, prefers launcher-discovered 3.12/3.11, supports `-PythonExe`, disables automatic Python installation, and adds `-BootstrapOnly` with no pip/network activity. New reproducible `verify_source_relocation_bootstrap.ps1` copied 706 tracked files to a Chinese+space temp checkout, created a fresh 3.12.13 x64 venv from non-repo cwd, preserved build=`afd52f88a351541a`, resolved `source_root` to the new checkout and reported `old_repo_in_syspath=false`. Targeted=`4 passed, 14 deselected`; full offline=`1873 passed, 24 deselected, 132 warnings in 147.68s`, exit 0. Full dependency install/new Windows/private integration restore remain separate gates.
- W7.4 basic offline backup/restore: real drill first exposed unchecked robocopy/pip exits, PowerShell 5.1 long-path hashing failure, and a critical `/XD data models reports` bug that also removed nested runtime source (`src/market_ai_hub/data`, `src/market_ai_hub/models`, `config/data`), yielding restored build `bbef69fe330230ab` despite checksum completion. Backup exclusions are now absolute repo-root paths, SHA256 is long-path-safe, native failures are fatal, and new verifier/drill scripts validate hashes/inventory/path containment, restore source to another path and require restored import/build identity. Final drill verified 2191 files and restored build=`afd52f88a351541a`; targeted=`2 passed`; full offline=`1875 passed, 24 deselected, 132 warnings in 139.90s`, exit 0. Basic tier excludes wheels/models/private market data; private DB/Parquet/WAL-consistent restore remains unverified.
- W7.5 Scheduled Task relocation: fixed forward-shadow registration so an existing task does not silently preserve an old checkout path after relocation. Both registration scripts now have non-mutating `-DryRun`; forward-shadow refreshes by default and supports explicit `-PreserveExisting`. Regression copies scripts to a Chinese+space temp repo and runs from non-repo cwd, proving generated task paths bind only to the relocated checkout. No Scheduler mutation was performed. Targeted=`17 passed`; full offline=`1880 passed, 24 deselected, 132 warnings in 141.67s`, exit 0 (including three concurrent untracked research-snapshot tests not owned by this package). Commit=`95c34cedf21ba1dfa4e7a48b23ee8da53ad6677b`; CI `36142106665` SUCCESS. Build remains `afd52f88a351541a`.
- W7.6 MCP config relocation: added `scripts/render_mcp_config.py` so generic/Cherry client JSON is generated from the current/explicit project root instead of hand-editing `<PROJECT>`. Supports stdout-only default, explicit `--output`, and fail-closed `--require-command`. Chinese+space relocated-root/non-repo-cwd regression covers both clients and rejects old-root leakage; targeted reconstruction=`18 passed`; full offline=`1881 passed, 24 deselected, 132 warnings in 132.50s`, exit 0. Commit=`db9eeed6b9aaba540fcb2acef19de3ea2cd8e86c`; CI `36143262904` SUCCESS. No third-party client setting was modified; build remains `afd52f88a351541a`.
- W7.7 portability truth matrix: added `docs/development/W7_PORTABILITY_ACCEPTANCE.yaml`. W7.1–W7.6 current-machine cells are PASS, while full dependency install/new Windows/WinCred/certificate/COM remain `UNVERIFIED_EXTERNAL_GATE`, private research-data restore was still a separate workstream at W7.7 publication, and C2.3 live verification remained time-window-gated; W7.8 later closes the current-machine private research-data cell only. A first placement under `config/` correctly triggered build-id regressions (`c555afda8269c1cc`), proving engineering status must not contaminate runtime identity; moved to docs and build returned to `afd52f88a351541a`. Targeted matrix/build=`22 passed`; full offline=`1882 passed, 24 deselected, 132 warnings in 172.30s`, exit 0.
- W7.8 private research-data snapshot/restore: recovered and completed the interrupted local workstream with public scripts only; no private data is committed. DuckDB/SQLite/Parquet snapshot, verifier and restore enforce exact inventory, SHA256, row counts, optional `prediction_id` digests, source-consistency checks, no overwrite/overlap, symlink fail-closed, and explicit `live/**` + `backups/**` exclusion. Real temp drill: 8 DuckDB + 1 SQLite + 5 Parquet, 1686 live files excluded, 14 restored files, no restored `live/`, cleanup PASS. Targeted=`4 passed, 1 skipped`; full offline=`1884 passed, 1 skipped, 24 deselected, 132 warnings in 133.70s`, exit 0. Current-machine acceptance cell now PASS; clean-new-Windows and live recorder restore remain separate gates. Commit=`f3faf193b34bae714c547dddba525a93edd467fb`; CI `36209628743` SUCCESS. Build unchanged `afd52f88a351541a`.
- W8.1 Windows lock security: GitHub default-branch Dependabot reported high `GHSA-5rjg-fvgr-3xxf` and medium `GHSA-h35f-9h28-mq5c`, both caused by `setuptools==78.1.0`. The stricter advisory requires `>=83.0.0`, so `requirements-lock-windows-x64.txt` now pins `83.0.0` and records both advisory IDs; lock documentation no longer claims bit-identical V1 freeze after security patching. No dependency installation was performed. Targeted=`20 passed`; full offline=`1883 passed, 24 deselected, 132 warnings in 170.00s`, exit 0; build unchanged `afd52f88a351541a`. Commit=`c2d76febca2c994b3678391a5b484d15b1d77319`; CI `36208910703` SUCCESS. Status=`PATCH_IN_PR / REMOTE_ALERT_PENDING_MERGE` because Dependabot evaluates default branch.
- W8.2 CI runtime maintenance: GitHub latest releases are checkout `v7.0.1` and setup-python `v7.0.0`, both Node 24. Workflow now uses `actions/checkout@v7`, `actions/setup-python@v7`, and fixed `ubuntu-24.04` instead of `ubuntu-latest`, avoiding the observed Node-20 forced-runtime warning and the announced Ubuntu 26 migration. Static regression locks this contract. Targeted=`21 passed`; full offline=`1885 passed, 1 skipped, 24 deselected, 132 warnings in 166.54s`, exit 0. Commit=`ac40f88b377b09eca0d296e0232abc88f4bd13c2`; CI `36210103584` SUCCESS; PR #55 OPEN/MERGEABLE; build unchanged `afd52f88a351541a`.
- W8.3 external relocation preflight: added non-mutating `check_external_relocation_gates.ps1 -Json`; all full-install/new-Windows/WinCred/certificate/COM cells remain `UNVERIFIED_EXTERNAL_GATE` while local readiness can be inspected without secrets or broker mutation. Fixed certificate false-positive semantics: generic Windows store non-empty/unexpired is not Yuanta identity/signature verification. WebCodex also reproduced and fixed UTF-8 corruption for Chinese relocation paths in MCP config and Scheduled Task dry-run outputs. Targeted=`23 passed`; full offline=`1887 passed, 1 skipped, 24 deselected, 132 warnings in 148.29s`, exit 0; build unchanged `afd52f88a351541a`.

## 2026-09-25 C2 W3.3 runtime evidence / terminal-close correctness

- Implementation commit: `92e178e4ea6cad632d071747efe1c273bcc79efc`; build_id `b6cfc2ceae89d221`.
- Raw `TickDetailBatch` cannot self-assert runtime verification. Raw canonical snapshot identity is independent of verification state.
- SPARK runtime records bounded request/callback metadata without account/prices. Exact request time is separate from callback receipt. Identical concurrent outstanding requests are left uncorrelated rather than guessed.
- `TickDetailRuntimeVerificationEvidence` binds request id/time/acceptance, callback time/index/returned market+code, canonical raw snapshot id and timestamp-basis cross-check into a deterministic integrity id. The id is not a broker signature.
- Terminal-close materialization requires valid typed evidence. Request and callback must both fall in the controlled 15:45 <= JST < 17:00 window; request-before-close/callback-after-close is rejected.
- Derived DAILY Feature Store materialization is a separate strict gate. Exact contract/month, CONTRACT series, roll NONE, PIT-safe source IDs, session close equality and DAILY frequency are required; TICK does not silently impersonate DAILY.
- Validation: C2/W3.3 35 passed; related W2/W3/C1 134 passed; final offline profile 1834 passed / 24 deselected / 132 warnings in 140.87s, exit 0, excluding only the live-owner mutex test. Changed-file secret scan 0; diff check PASS.
- Actual runtime timestamp verification = **NONE_YET**. Eligible real DAILY terminal-close evidence = **NONE_YET**. ACTUAL_FORWARD_EVIDENCE = **NONE_YET**. No broker/login/restart/subscription/order/account action occurred.
- Pre-existing staged W3.3 contract/report files are not part of implementation commit `92e178e`. Full details: `research/phase3/reports/C2_W33_RUNTIME_EVIDENCE_TERMINAL_CLOSE_2026-09-25.md`.

## 2026-09-24 correctness hardening

Latest 2026-09-25 correction: code `ea29c12af8bdffb36bbaa1dd8275d445fc7135a0`.
Exact outcome labels, seasonal horizons, interval origin alignment/validity, trend confidence truth
and classifier forecast-origin inputs fixed. Offline profile 1785 passed / 34 deselected; focused
172 passed / 3 deselected. See `MODEL_CREDIBILITY_PLAN_2026-09-25.md` and
`MODEL_CREDIBILITY_VALIDATION_2026-09-25.md` in this directory for scope and limitations.
Prior tournament rankings affected by these changes require versioned re-evaluation.

## 2026-09-25 C1 evaluation comparison / abstention correctness

- Implementation commit: `50f209a095a151b6ae42c6db5d0d462d11fd2395`; build_id `c64b98bd4a09d576`.
- Tournament now counts VALID / FAILED / ABSTAINED / NONFINITE / INVALID_TARGET separately. Effective sample and coverage no longer treat refusals/failures as valid observations.
- Pairwise comparison uses common valid origins and simultaneously records each model's full coverage. CLI persists pairwise rows; `compare` no longer compares unmatched success subsets. Best-summary ranking requires full coverage.
- Performance Store C1.1 rejects NaN/Inf, missing/inconsistent accounting, isolates legacy leaderboard rows by schema, and keeps legacy data inspectable without rewriting history.
- Random walk now respects horizon steps; research majority-class baseline requires train labels; rates regime uses aligned 10Y/5Y observations and an actual 20-session lookback.
- Validation: initial C1 `11 passed, 4 failed`; final focused `198 passed, 6 deselected`, exit 0. Unfiltered full offline: `1802 passed, 34 deselected, 1 failed` only because Windows global quote-owner mutex reported `YUANTA_LIVE_ALREADY_RUNNING`. Final offline profile excluding that one live-owner-conflicting test: `1804 passed, 35 deselected, 110 warnings` in 129.47s, exit 0. Changed-file secret scan 0; diff check PASS.
- No broker/login/restart/subscription/order/account action; no calibration fitting; no new model; no real forward sample or market ranking rerun. ENGINE PASS remains distinct from DATA READY / CALIBRATED / PREDICTIVE EVIDENCE / TRADING EDGE.


Source fixes: durable-write acknowledgement, per-field freshness, bounded callbacks,
single-owner mutex, subscription request validation/limits, shared data-root resolution,
fail-closed audit probability helper, read-only readiness, fatal installer failures,
offline CI markers, complete runtime-config fingerprint. See
`research/phase3/reports/QUOTE_HUB_HARDENING_2026-09-24.md` for validation/publication state.
The previously running recorder has not been restarted by this repair; disk source
PASS does not mean that process loaded the new implementation.
Automatic reconnect/roll, durable crash spool, validated TICK→daily aggregation / broker DATA READY and calibration fitting remain future work. Reader → V2-A.2/V2-H lineage → canonical Feature Store provenance → packet/model-input boundary is offline-verified; research-only boundaries are unchanged.

## 2026-09-25 W2 field-aware reader/replay

- Implementation commit: `825c19e7c67922eb7779d768ccd8b4207aae98cf`; build_id `52837b5fc6444e3f`.
- `src/market_ai_hub/integrations/yuanta/quote_reader.py` reads trade/bid/ask with independent field provenance, keeps callback receipt separate from exchange event time, and routes through existing V2-A.2 session/factor definitions rather than a parallel registry.
- Source time-of-day without a date stays `event_timestamp=None` / `timestamp_precision=UNKNOWN`; old recorder schema degrades to `LEGACY_TOP_LEVEL_RECEIPT_ONLY`. Market/contract/session mismatches, missing field time in the new schema, out-of-order replay, partial files, persistence errors and overflow fail closed.
- V2-H `lineage_from_observation()` preserves source snapshot IDs, quality and contract identity. No probability gate was relaxed; 2I.1 remains evaluation-only.
- Read-only live inspection: running PID/status uses the old health schema and 0/22 latest quotes carry `field_provenance`; state = **RUNTIME_ADOPTION_PENDING**. Recorder was not stopped or restarted.
- Local validation: focused V2/Yuanta regression `153 passed, 1 deselected`; final default suite `1717 passed, 23 deselected, 132 warnings` in 135.55s, exit 0. Existing private Parquet read-only sample: 934 rows, 76 OSE rows; 5 valid trade observations adapted and explicitly degraded, 71 non-valid trade callbacks rejected. No raw private quote values were added to the repo.
- W2 is only partially complete: feature store/model/public packet end-to-end ingestion remains pending, as do reconnect/roll/WAL and controlled runtime adoption.

## 2026-09-25 W2 Feature Store / packet provenance wiring

- Implementation commit: `5fe8906bd1237f7f89cd96dbbfa9383b8763281f`; build_id `f09ff80765f94687`.
- Feature Store schema advances non-destructively from v1 to v2. Existing Phase-2C feature rows remain readable; V2-A.2 observation snapshots preserve V2-H lineage ID, venue/session/trading date, timestamp precision, quality, contract/roll semantics and source snapshot IDs.
- Quote features materialize only when the observation is AVAILABLE, dated, point-in-time safe, FRESH and a V2-A.2 live role; legacy receipt-only, unknown event time, stale, future-available, wrong roll/contract semantics stay provenance-only or fail closed.
- Replay is idempotent for both immutable observation snapshot and materialized feature. Read-only packet queries do not create/migrate a Feature Store.
- Canonical data-root use is now `MARKET_AI_DATA_ROOT` for runtime paths, Data Lake and default Feature Store; old `MARKET_AI_HUB_DATA_ROOT` remains only migration fallback in Data Lake.
- Analysis Packet exposes a bounded `factor_observation_summary` with lineage/source/quality/contract/freshness context. It does not turn those rows into probabilities and does not silently override existing target/reference price selection.
- Validation: focused integration `155 passed, 1 deselected`; broader contract regression `265 passed, 2 deselected`; final default suite `1726 passed, 23 deselected, 132 warnings` in 150.34s, exit 0. Changed-file secret scan: 0 hits; `git diff --check` PASS.
- Feature Store / packet provenance sub-step is complete; recorder runtime adoption remains separately pending.

## 2026-09-25 W2 gated model-input contract

- Implementation commit: `9a11ce309ef5159545cb64e4ed8fa81ca0bbacfd`; build_id `bed003b51f6d1f8b`.
- Read-only model-input construction consumes only materialized, point-in-time-safe, AVAILABLE Feature Store rows at/before cutoff and requires homogeneous representation, contract and source frequency. Missing schema/store, mixed contracts/frequency, duplicate event times and insufficient history produce typed abstention states.
- Lineage/source snapshot IDs remain attached. Public readiness exposes metadata only (`values_exposed=false`); later-available rows are excluded by test.
- Current broker features are `TICK`, while Chronos/TimesFM/classifiers are `1d`; Osaka direct readiness therefore reports `INCOMPATIBLE_FREQUENCY` rather than fake resampling. Taiwan index is checked per futures representation; Taiwan stock has no broker direct-target model-input mapping.
- Offline W2 engineering path = **W2_OFFLINE_CONTRACT_PASS**. This is not DATA READY: live recorder adoption is pending and there is no validated TICK→daily aggregation for the current daily models.
- Validation: focused `117 passed, 1 deselected`; packet regression `76 passed, 1 deselected`; V2 regression `146 passed`; final default suite `1735 passed, 23 deselected, 132 warnings` in 141.75s, exit 0. Changed-file secret scan 0 hits; `git diff --check` PASS.

## 2026-09-25 W3.1 outcome / evaluation governance

- Implementation commit: `95289de6722c1477c5183e172384a3fd196050fd`; build_id `98fe354dcc4fb275`.
- Prediction Audit advances to 2H.3. New predictions can seal `sample_origin`, `label_window_id`, `label_window_start`, and `label_window_end` into immutable identity. For a sealed window, outcomes before horizon maturity or with a mismatched target period are rejected at append time.
- New W3.1 governed evaluation requires timezone-aware `evaluation_as_of` and an exact target/instrument/horizon/model/model-version/artifact/label/sample-origin/event scope. Forward-precommitted and retrospective replay samples cannot mix; duplicate logical samples and selected superseded samples fail closed.
- W3.1 exposes coverage/missing-outcome/event/missing-day/overlapping-horizon metadata and only then delegates metrics to the unchanged 2I.1 engine. `READY_FOR_EVALUATION != CALIBRATED`; fitting remains NOT_STARTED.
- Default prediction-audit DB now follows canonical `MARKET_AI_DATA_ROOT`. Cross-prediction reuse of the same artifact identity is a typed binding rejection rather than a raw DuckDB constraint error.
- Validation: W3/V2-H/V2-I focused `85 passed`; W3 + PPM/packet broader `236 passed, 1 deselected`; final code/test default suite `1749 passed, 23 deselected, 132 warnings` in 172.00s, exit 0. Changed implementation/test secret scan: 0 hits; `git diff --check` PASS.
- Evidence boundary: the new W3 regression samples are synthetic temporary DB records and are **not** market predictive evidence. Real precommitted forward sample accumulation is still pending.


## 2026-09-25 W3.2 precommitted forward cycle

- Implementation commit: `2f374ad533a74e3647fdfdeb73d9ebb2f379631a`; build_id `81f02a25847b9e65`.
- First supported scope is OSAKA_MICRO / JNU / 1 verified OSE session / existing `last_price_naive`. Prediction is a POINT terminal-price baseline, not a probability.
- Precommit is accepted only from a contract-specific DAILY/PIT-safe/source-snapshotted close after 15:45 JST and before the target night session begins at 17:00 JST. No public backdate argument exists.
- Feature Store reader requires dedicated `terminal_close / w3.2-contract-daily-close-1` rows and reuses W2 read-only model-input gating. TICK cannot impersonate DAILY. Settlement requires the same contract/month and exact sealed target close before W3.1/2I.1 evaluation.
- Runtime read-only probe: legacy continuous Osaka parquet = 960 rows, latest 2026-09-01, blocked by missing available_at/source IDs/contract/month/roll provenance; canonical Feature Store existed but had 0 OSE observations at the probe cutoff. Eligible W3.2 candidate = none; real W3.2 prediction inserted = none.
- Validation: focused 101 passed; final Feature Store/operator focused 127 passed; broader 303 passed/2 deselected; default 1773 passed/23 deselected/132 warnings in 156.48s, exit 0; changed implementation/test secret scan 0 hits; diff check PASS.
- No scheduler was enabled, no recorder/broker action occurred, and CALIBRATION FITTING remains NOT_STARTED.

## Phase 2 全歷程 Gate

| Phase | 內容 | Gate |
|---|---|---|
| 2A~2G.2 | Registry/Providers/FeatureStore/Regime/Tournament/自動化/Strategy/Joint/官方資料 | PASS |
| 2H | Analysis Packet + MCP 8 tool + Cherry Skills + Archive | PASS |
| 2I-A / 2I-B | 效能/準確度硬化 + Reconstruction Pack | PASS |
| 2T | TradingView Optional Bridge 實機驗證 | PASS |
| 2Y-A~2Y-G.1 | Yuanta 盤點/憑證/Spark/COM/sidecar/ground-truth/語義修正 | PASS |
| 2Z / 2Z.1 | Final Acceptance + Yuanta API family disambiguation | **PASS** |
| 2V-A | Real-World E2E Validation + Yuanta OneAPI version audit | PHASE2VA_PASS |
| 2Y-H | Yuanta Local SDK Forensics + Quote symbol/login/version closure | PHASE2YH_PASS |
| **2V-B** | Historical OOS Walk-Forward + Statistical Evidence Audit | **PHASE2VB_PASS** |
| **2V-B.1** | Local Historical Data Discovery + Direct Target Recovery Audit | **PHASE2VB1_PASS** |
| **2V-B.2** | Local OSE Micro Data Provenance Validation + Safe Import + Direct OOS Decision | **PHASE2VB2_PASS** |
| **2V-B.3** | Direct OSE Micro Continuous Bar Historical OOS Exam | **PHASE2VB3_PASS** |
| **2V-C** | Execution-Aware Strategy Validation + Cost Stress Test | **PHASE2VC_PASS** |
| **2V-C.1** | Gap Edge Causality + Pre-Close Executability Validation | **PHASE2VC1_PASS** |
| **2V-D** | Forward Shadow Validation + Drift Monitoring + Registry Hardening | **PHASE2VD_PASS** |
| **2V-E** | Forward Data Feed Readiness + Daily Operations + Phase 2 Research Freeze | **PHASE2VE_PASS** |
| **2V-F** | Compute Resource Governor + Safe Training Scheduler + Desktop Protection | **PHASE2VF_PASS** |
| **2P-A** | Final Publication Acceptance + Release Freeze + Clean Reconstruction Audit | **PHASE2PA_PASS** |
| **2P-B** | Beginner Ops Docs + Cherry Studio Guide + Final Publication | **PHASE2PB_BLOCKED**（remote mismatch） |
| **2P-C** | Remote Reconciliation + Client-Neutral Merge + GitHub Publication | **PHASE2PC_PUBLISHED** |
| **2P-D** | Agent Response Truthfulness Hotfix + Target Semantics Audit | **PHASE2PD_PUBLISHED** |
| **2P-E** | System Prompt Compaction + Skill Responsibility Cleanup | **PHASE2PE_PUBLISHED** |
| **2Q-A** | Runtime Truth Consolidation + Deterministic Direction + MCP Fast Path | **PHASE2QA_PASS** |
| **2Q-B** | Whole System Validation + Clean-Room Audit + Failure Injection + E2E MCP | **PHASE2QB_PASS** |
| **2Q-C** | Primary Market Parity + Historical Learning + OOS Validation Framework | **PHASE2QC_PASS** |
| **2Q-C.1** | Product Spec Truth + Local Data Root Hygiene + Filesystem Side-Effect Remediation | **PHASE2QC1_PASS** |
| **2Q-C.2** | Target-Family Runtime Isolation + Taiwan Packet Correctness + Historical OOS Metric Correctness | **PHASE2QC2_PASS** |
| **2Q-D** | Full Performance Engineering + Runtime Acceleration + MCP/Cherry Latency + Build Identity Correction | **PHASE2QD_PASS** |

## 2Q-D 本棒成果（Performance Engineering，不改 research truth）
- build identity 修正：`build_info` 現在 fingerprint 全部 `src/market_ai_hub/**/*.py` + runtime config（175 files）；docs/tests 不改 build_id。
- health/system_info/gates shallow（不 load 模型）：health 15.9s→0.706s（-95.6%）、system_info 16.5s→0.593s（-96.4%）、gates 0.139s。
- 新 `services/model_status.py`（find_spec+cache presence，不 import torch）+ `services/instrumentation.py`（真 counters）。
- classifier fit cache（`services/fit_cache.py`）：XGB/LGBM 不再每 request 重 fit；bounded n_jobs（`interactive_n_jobs()` 1~4，取代 -1）。
- provider shallow status：`status_all(deep=False)` 不 network probe（TWSE 3.4s probe 移除）。
- benchmark 修掉 hardcode `model_inference_count=0`。新增 PERFORMANCE_2QD_{BEFORE,AFTER}.json + DIFF + 報告。
- 新增 `test_phase2qd.py`（13 tests）；全 suite **778 passed**（765→778）。build_id → `badba314b7e119c0`。
- 禁區未動：不改 research truth / 不 leakage / 不 AUTO_TRAIN / 不 broker。PR #11 merged；版本仍 v2.0.0-rc1。

## 2Q-C.2 本棒成果（Target-Family Isolation + Taiwan Packet + MASE metric，correctness hotfix）
- 修 HIGH cross-market contamination：taiwan packet 不再引用 OSE Micro settlement（root cause = reference routing 二分法）。
- 新 `resolve_market_family()`（OSAKA_MICRO / TAIWAN_STOCK / TAIWAN_INDEX，未知 market fail clearly）。
- reference/regime/coverage/archive 全按 family 隔離；`_taiwan_stock_reference()`（FinMind→TWSE→yfinance）；TAIEX = ^TWII proxy + DIRECT_NOT_IMPLEMENTED。
- 修 MASE：每 fold scale 只用 TRAINING naive in-sample（不跨 fold、不含 future）；新增 baseline_scores + fold-level metrics。
- 修 yfinance tz-naive timestamp 雙重解讀（先 localize 到 local tz 再 convert UTC）。
- 新增 `test_phase2qc2.py`（22 tests）；全 suite **765 passed**（743→765）。MCP E2E 驗證三 market 無污染。
- build_id 未變（`1afb6888eec3fbdc`）。禁區未動：不 performance / 不新模型 / 不 training / 不 broker。PR #10 merged；版本仍 v2.0.0-rc1。

## 2Q-C.1 本棒成果（Product Spec Truth + Data Root Hygiene + Filesystem Side-Effect，correctness/hygiene hotfix）
- 修 OSE Micro multiplier 100→10（JPX official：Contract Unit = Nikkei 225 × JPY 10，tick 5）。TX/MTX/TMF = 200/50/10 authoritative verified。
- 新 `config/runtime_paths.py`：MARKET_AI_DATA_ROOT env override，預設 `<ProjectRoot>\data`；private inbox = `<DATA_ROOT>\private\inbox\225labo`。
- 移除 hardcode `D:\MARKET_AI_HUB_PRIVATE_INBOX`（empty legacy folder 已安全刪除）；import/health/status 不再產生 filesystem side effect（lazy path + FileHandler delay）。
- `scripts/import_latest_225labo_micro.ps1` 改從 Python resolver 取 path。`.env.example` 加 MARKET_AI_DATA_ROOT。
- 新增 PRODUCT_SPEC_AUDIT.md / LOCAL_RUNTIME_ARTIFACT_AUDIT.md / 報告。225LABO license boundary 不變（LOCAL_ONLY，manual only）。
- 新增 `test_phase2qc1.py`（16 tests）；全 suite **740 passed**（724→740）。build_id → `1afb6888eec3fbdc`。
- 禁區未動：不 training / 不 broker / 不 mega-restructure。PR #9 merged；版本仍 v2.0.0-rc1。

## 2Q-C 本棒成果（Primary Market Parity + Historical Learning + OOS Validation，architecture/framework）
- 三大 first-class families 正式定義：OSAKA_MICRO / TAIWAN_STOCK / TAIWAN_INDEX（防止 Osaka-only）。
- TAIWAN_INDEX 語義：TAIEX=cash index forecast/reference（非可成交）；TX/MTX/TMF=execution。
- 新模組 `research/historical_learning.py`：HistoricalWalkForwardProtocol（expanding/rolling、three_zone_split、protocol hash、leakage invariant）。
- 新 `services/primary_targets.py`（registry loader）+ `config/primary_targets.yaml`（不 hardcode 私人路徑）。
- `research_truth` 新增 `evidence_by_target()`（§21 按市場隔離）；`get_analysis_packet` 支援 `market=taiwan_index`。
- 新增 YAML/docs：PRIMARY_MARKET_MISSION / UNIFIED_RESEARCH_EVIDENCE_SCHEMA / TAIWAN_INDEX_CAPABILITY_AUDIT / HISTORICAL_LEARNING_PROTOCOL / OUT_OF_SAMPLE_VALIDATION_STANDARD / 報告。
- 新增 `test_phase2qc.py`（15 tests）；全 suite **724 passed**（712→724）。build_id → `026a18a9d46832f8`。
- TAIWAN_STOCK / TAIWAN_INDEX 目前 NO_EVIDENCE / NOT_YET_VALIDATED（誠實）。禁區未動：不 broker / 不 auto promotion。PR #8 merged；版本仍 v2.0.0-rc1。

## 2Q-B 本棒成果（Whole System Validation + Clean-Room + Failure Injection + E2E MCP，correctness-only）
- 0 Critical / 0 High defect；修 1 個 MEDIUM：`mcp/server.py` 硬編碼 `project_path` → `str(project_root())`（clean-room 違反）。
- 新增 tests：`test_phase2qb.py`（16）+ `test_phase2qb_failure.py`（5）；全 suite **712 passed**（691→712）。
- 新增 scripts：`mcp_e2e_stability.py`（實際啟動 MCP stdio，24 calls no crash，RSS 67.3MB）+ `secret_scan.py`（0 真實 secret）。
- 新增 `SYSTEM_VALIDATION_BASELINE.json` + `PHASE2QB_WHOLE_SYSTEM_VALIDATION_REPORT.md` + `docs/reference/KNOWN_LIMITATIONS.md`。
- Clean clone PASS（project_root 正確解析、21 tools、3 skills、data/ 僅 .gitkeep）；restart deterministic（multi-seed subprocess）；research truth 一致；仍 RESEARCH_ONLY。
- build_id → `440d9273c9bb39f5`。禁區未動：不 performance optimization / 不重組目錄 / 不新模型 / 不 broker / 不 auto promotion。PR #7 merged；版本仍 v2.0.0-rc1（不 tag）。

## 2Q-A 本棒成果（Runtime Truth Consolidation + Deterministic Direction + MCP Fast Path）
- 修正 Cherry Studio 驗收問題 A–G：direction 只收 eligible vote（0 票 → NO_VALIDATED_MODEL_CONSENSUS）；deterministic tie（平手 → NO_CONSENSUS，cross-process 一致）；uncalibrated 不稱 probability；direct/proxy calendar 分離；research truth 單一來源；forward count 統一；fast path + forecast cache。
- 新模組：`services/research_truth.py`（讀 PHASE2_RESEARCH_FREEZE）、`services/forecast_cache.py`、`services/perf_trace.py`（MCP_PERF_TRACE）。
- packet 加 target_semantics / calendar 分離 / support_resistance_status / validation_truth / market_environment / driver_panel。
- gate wording 修正（MODEL_PREDICTIVE_GATE=GENERAL_PRODUCTION_MODEL_GATE_UNPROVEN；TRADING_EDGE_GATE.result=NO_ECONOMIC_EDGE）。
- build_info 加 release_version / runtime_build_id。benchmark `scripts/benchmark_mcp_fastpath.py`（fastpath_acceptance=true，warm QUICK 1 call + 0 dup inference ~3ms）。
- 新增 `tests/test_phase2qa.py`（22 tests，含 subprocess cross-process determinism）；全 suite **691 passed**。
- build_id → `cd33ef1c14839b7d`（source runtime 修正，fingerprinted files 變更）。禁區未動：不新增模型 / 不重訓 / 不 strategy optimization / 不 broker / 不 live trading。PR #6 merged；版本仍 v2.0.0-rc1。

## 2P-E 本棒成果（System Prompt Compaction + Skill Responsibility Cleanup，doc-only）
- 新增 `docs/prompts/SYSTEM_PROMPT_V4_1_COMPACT.md`（~260 行，RECOMMENDED FOR CHERRY STUDIO AND NORMAL MCP CLIENT USE）。
- 保留 critical safeguards；移除 hardcode dynamic facts（Forward N / build_id 作 authoritative / leaderboard）；詳細規則 delegate 到 3 Skills。
- V4.0 標 FULL REFERENCE / EXTENDED POLICY（不刪）。
- README / CHERRY_STUDIO_BEGINNER_GUIDE / CHERRY_STUDIO_SETUP / MCP_CLIENT_SETUP 推薦改指 compact。
- 新增 `tests/test_phase2pe.py`（12 tests）；全 suite 669 passed。
- 不改 runtime / models / research evidence / MCP tools / training defaults。PR #5 merged；版本仍 v2.0.0-rc1。

## 2P-D 本棒成果（Agent Response Truthfulness Hotfix，documentation/prompt only）
- 新增 `docs/prompts/SYSTEM_PROMPT_V4_PHASE2_RC1.md`（Phase 2 / v2.0.0-rc1 對齊，含 0A 語意保護 10 條）。
- 10 條語意保護：continuous vs contract / settlement vs model target / direction eligibility（NO_VALIDATED_MODEL_CONSENSUS）/ uncalibrated probability / economic validation truth / support-resistance evidence / P10-P90 / holiday trading（2026-09-21~23 祝日交易）/ model-specific validation / forward registry（registered≠validated）。
- V3.3 標 DEPRECATED AS PRIMARY / HISTORICAL COMPATIBILITY REFERENCE。
- README / MCP_CLIENT_SETUP / CHERRY_STUDIO_SETUP / START_HERE_BEGINNER 推薦 System Prompt 改指 V4。
- 新增 `tests/test_phase2pd.py`（8 tests）；全 suite 657 passed。
- 不改 runtime / MCP tools / models / research conclusions / training defaults。
- PR #4 merged；版本仍 v2.0.0-rc1。

## 2P-C 本棒成果（Remote Reconciliation + GitHub Publication）
- Remote client-neutral 改寫（3922365）與 local Phase 2 工作**兩者全保留**（不二選一）。
- release/v2.0.0-rc1 建於 origin/main，cherry-pick Phase 2 work，reconcile README/HANDOFF/ARCHITECTURE。
- remote stale V1 docs 更新（13→21 tools，build_id→ccabe1e1552d9ae7）。
- **已發布 GitHub**：PR #3 merged（6b6d58e）→ tag v2.0.0-rc1 → release（truthful notes）。
- 全 suite 649 passed；MCP 21 tools；Skills 3；research state 誠實。
- URL：https://github.com/fishke22/market-ai-hub/releases/tag/v2.0.0-rc1
- 產物：`REMOTE_RECONCILIATION_REPORT.md`、`PHASE2PC_REMOTE_RECONCILIATION_PUBLICATION_REPORT.md`。

## 2P-B 本棒成果（Beginner docs + 嘗試 final publication）
- 建立 9 份繁體中文 beginner docs（START_HERE / HOW_WORKS / CHERRY_STUDIO_GUIDE / DATA_UPDATE / AUTO_LEARNING / SAFE_TRAINING / TRADING_READINESS / DAILY_WORKFLOW / FAQ）+ README「第一次使用」links。
- 全部誠實揭露：RESEARCH_ONLY / NON_EXECUTABLE / NO_ECONOMIC_EDGE / AUTO_*=FALSE / Forward NONE_YET。
- .gitignore 補 runtime/private artifacts（data/*.json、Yuanta auth/diagnostic、machine inventory、runtime status）。
- 全 suite 649 passed（新增 6 beginner doc tests + 9 publication tests）。
- **🔴 BLOCKED：remote mismatch**。git fetch 發現 origin/main 已前進至 3922365（使用者 Sep-19 的 client-neutral docs 改寫，重寫 README/HANDOFF/ARCHITECTURE），本地仍 f707fdf 落後 1 commit，且與 beginner docs 重疊將產生 merge conflict。
- **未 commit / push / tag / release**。需人工決定 merge 方向（見 PHASE2PB_BEGINNER_PUBLICATION_REPORT.md 選項 A/B/C）。
- 產物：`PHASE2PB_BEGINNER_PUBLICATION_REPORT.md`、`tests/test_phase2pb.py`（6 tests）、9 份 beginner docs。

## 2P-A 本棒成果（Final Publication Acceptance + Crash Recovery）
- Crash recovery：無 stale git lock / truncated 檔案 / partial writes（HEAD f707fdf intact）。
- 保留已完成的 README Research State + evidence docs + publication manifests；補建 RELEASE_MANIFEST / DIFF_SUMMARY / GIT_PLAN / acceptance report。
- Clean clone **PASS**（Python 3.12，core import + MCP 21 tools + reconstruct_verify PASS）。
- MCP runtime 21 tools；model registry chronos/timesfm/fincast/xgb/lgbm PASS、NHITS/NBEATSx blocked。
- Secret scan 無 hardcoded credential；private data（data/ 僅 .gitkeep）；Yuanta/225LABO 全排除。
- Release v2.0.0-rc1（Phase 2 Research Release Candidate）。**publication-ready，但本棒未 commit/push/tag**。
- 產物：`RELEASE_MANIFEST.yaml`、`PUBLICATION_DIFF_SUMMARY.md`、`PRE_PUBLICATION_GIT_PLAN.md`、
  `PHASE2PA_FINAL_PUBLICATION_ACCEPTANCE_REPORT.md`、`PHASE2PA_CRASH_RECOVERY_AUDIT.md`、
  `PHASE2PA_CRASH_RECOVERY_REPORT.md`、`PHASE2PA_RECOVERY_CHECKLIST.json`、`tests/test_phase2pa.py`（9 tests）；全 suite 643 passed。

## 2V-F 本棒成果（Compute Resource Governor，保護桌面多工）
- 建立 resource governor：`config/resource_profiles.yaml`（DESKTOP_SAFE 預設）+ `config/model_resource_requirements.yaml`。
- `src/market_ai_hub/services/resource_governor.py`：preflight / request_resource_slot / release / status / log。
- 預設限制：GPU VRAM ≤65%/75%（保留≥4GB）、CPU 保留 25%、RAM ≤65%/75%、priority BelowNormal、Optuna n_jobs=1。
- **AUTO_TRAIN=false / AUTO_FINE_TUNE=false / AUTO_PROMOTE=false**；single heavy GPU job；fail closed。
- `scripts/resource_status.ps1` + `scripts/run_training_safe.ps1`；RESOURCE_GOVERNOR_STATUS.json。
- 產物：`PHASE2VF_RESOURCE_GOVERNOR_REPORT.md`、`tests/test_phase2vf.py`（15 tests）；全 suite 634 passed。

## 2V-E 本棒成果（Forward Data Feed Readiness + Phase 2 Research Freeze）
- 建立 225LABO manual ingest workflow（無 auto-scrape，source immutable，incremental idempotent）。
- `src/market_ai_hub/data/ylab225_ingest.py`：build_daily_bars / validate / ingest_from_inbox / coverage_summary / run_daily_cycle。
- `scripts/import_latest_225labo_micro.ps1` + `scripts/run_daily_forward_cycle.ps1` + `scripts/register_forward_shadow_task.ps1`（opt-in only）。
- 資料 freshness gate：FRESH/STALE/MISSING_CURRENT_SESSION；stale → FORECAST_SKIPPED_DATA_QUALITY（實測）。
- **PHASE2_RESEARCH_FREEZE.yaml**：Phase 2 最終誠實結論凍結（VAR=STATISTICAL_FORECAST_EVIDENCE 但 NON_EXECUTABLE；NO_ECONOMIC_EDGE；無 candidate）。
- 產物：`FORWARD_DATA_SOURCE_POLICY.yaml`、`PHASE2_RESEARCH_FREEZE.yaml`、`FORWARD_DAILY_SUMMARY.md`、
  `tests/test_phase2ve.py`（14 tests）；全 suite 619 passed。

## 2V-D 本棒成果（Forward Shadow infrastructure，research-only，非 trading）
- 建立 forward shadow infrastructure：protocol frozen + activation timestamp（2026-09-20）+ core module + scripts。
- `src/market_ai_hub/research/forward_shadow.py`：create_daily_forecasts / settle_pending / build_status / init_activation。
- `scripts/run_forward_shadow.ps1` + `scripts/settle_forward_predictions.ps1`（research forecast + registry write，無 Yuanta login/order）。
- registry append-only + immutable 驗證；資料 freshness gate（stale → FORECAST_SKIPPED_DATA_QUALITY）。
- **Forward evidence = NONE_YET**（225LABO data 19 天 stale，最後 bar 2026-09-01；不能 backfill，需 fresh data + 每日執行）。
- **歷史結論維持**：VAR = STATISTICAL FORECAST EVIDENCE 但 NON_EXECUTABLE_FORECAST_EDGE；無 strategy/production candidate。
- Label 全程：RESEARCH_FORECAST_ONLY / NON_EXECUTABLE_FORECAST_EDGE；AUTO_PROMOTE=false；scheduler default DISABLED。
- 產物：`FORWARD_SHADOW_PROTOCOL.yaml`、`FORWARD_SHADOW_ACTIVATION.yaml`、`FORWARD_SHADOW_STATUS.json`、
  `FORWARD_SHADOW_REPORT.md`、`FORWARD_VALIDATION_MANIFEST.yaml`、`PHASE2VD_FORWARD_SHADOW_SETUP_REPORT.md`、
  `tests/test_phase2vd.py`（15 tests）；全 suite 605 passed。

## 2V-C.1 本棒成果（Gap Edge Causality + Pre-Close Executability，非 trading）
- **最終結論：NON_EXECUTABLE_FORECAST_EDGE**。VAR(1) 的 gap edge 無法轉成可執行策略。
- 因果發現：VAR 62.2% close-to-close edge 有 **85.2% 在 gap**（corr +0.726 sign / +0.896 return），intraday 反向 -0.378。
- **關鍵**：corr(r_t, gap) = **-0.919**（當日 return 與 gap 強烈反向 mean reversion）。gap edge 需「當日完整 return r_t」才能算，但 r_t 只在 close[T]（15:15）才完整 = gap 開始時刻 → **non-causal**。
- Pre-close causal signal（用 r_{t-1}）：gap 準確率崩潰到 **41.3%**（比隨機 50% 差），close-to-close 47.5%。
- Full-close signal = STATISTICAL_ONLY_EDGE（85.2% 真實但 non-causal）；pre-close = NO_EDGE。
- VAR 不升 strategy candidate，保留研究結果。2V-D 不得追 production strategy。
- 產物：`GAP_EXECUTION_PROTOCOL.yaml`（v1 frozen）、`GAP_RETURN_DECOMPOSITION.csv`、
  `PRECLOSE_SIGNAL_RESULTS.csv`、`PHASE2VC1_GAP_CAUSALITY_REPORT.md`、`tests/test_phase2vc1.py`（14 tests）；全 suite 590 passed。

## 2V-C 本棒成果（Execution-Aware Strategy Validation，非 live trading）
- 對 VAR(1) candidate 做簡單 strategy mapping（signal at T close → enter T+1 open → exit T+1 close, fixed 1 unit）。
- **Strategy 分類：NO_ECONOMIC_EDGE**。VAR strategy 零成本即虧損（gross -259.4 pts/trade, win 32.1%）。
- **關鍵發現**：VAR forecast 對 close-to-close 準 62.2%（真實 edge），但 tradable 的 open-to-close 方向**反向相關 -0.378**（只準 32.4%）。**edge 在 overnight gap，不在 intraday open-to-close**。
- Cost scenarios C0-C3 全負（-259 至 -301 pts/trade）；break-even = 0 ticks。
- LONG/SHORT 皆負（LONG -153, SHORT -408）；所有 regime/subperiod 皆負，隨時間惡化。
- **Forecast edge 保留 CHAMPION_CANDIDATE（close-to-close 62.2%）**，但 strategy 無可執行 edge。
- 產物：`STRATEGY_VALIDATION_PROTOCOL.yaml`（v1 frozen）、`STRATEGY_COST_ASSUMPTIONS.yaml`、
  `VAR_STRATEGY_RESULTS.csv`、`STRATEGY_REGIME_RESULTS.csv`、`STRATEGY_SUBPERIOD_RESULTS.csv`、
  `BREAK_EVEN_COST_TABLE.csv`、`STRATEGY_VALIDATION_MANIFEST.yaml`、
  `PHASE2VC_STRATEGY_VALIDATION_REPORT.md`、`tests/test_phase2vc.py`（17 tests）；全 suite 576 passed。

## 2V-B.3 本棒成果（Direct Micro Bar Historical OOS Exam，正式模型考試）
- 驗證 225LABO minute OHLCV → OSE 交易日 bar（960 days，832 origins），point-in-time expanding walk-forward。
- **BREAKTHROUGH: VAR(1) beats LAST_VALUE (h=1)**：MASE=0.958, 95% CI=[0.00018, 0.00080] (不跨 0), dir_acc=62.2%, MCC=0.241。
- **本專案首次有模型統計上顯著擊敗 baseline**。timesfm-3.0 也接近 (MASE=0.995)，但其他模型未 beat。
- 方向模型：XGBoost (56.4%), LightGBM (55.7%) — 皆優於簡單方向 baseline。
- Foundation models: chronos MASE=1.012, timesfm MASE=0.995 — timesfm 邊際 beat 需進一步驗證。
- Ensembles: equal-weight MASE=1.099, dynamic MASE=1.019 — ensemble 稀釋 VAR 訊號。
- **Proxy vs Direct 差異顯著**：^N225 proxy 全模型 NO_EVIDENCE，但 verified Micro 有 VAR 顯著 beat。
- **CHAMPION_CANDIDATE: VAR(1)**。AUTO_PROMOTE=false，需 2V-C strategy + 2V-D forward。
- 產物：`DIRECT_MICRO_BAR_OOS_PROTOCOL.yaml`（v1 frozen）、`DIRECT_MICRO_BAR_OOS_RESULTS.csv`、
  `DIRECT_MICRO_BAR_DATASET_MANIFEST.yaml`、`DIRECT_MICRO_BAR_EXAM_MANIFEST.yaml`、
  `PHASE2VB3_DIRECT_MICRO_BAR_OOS_REPORT.md`、`tests/test_phase2vb3.py`（14 tests）；全 suite 559 passed。

## 2V-B.2 本棒成果（資料鑑識與驗證，READ-ONLY，未修改原始檔）
- 驗證 `D:\data\N225microf_2023-2026` = **真實 OSE Micro 分鐘 trade OHLCV**（225LABO vendor，非官方交易所）。
- **796 個 verified 交易日**（2023-07-24 → 2026-08-31），**0 筆上市前資料**（上市日 2023-05-29）。
- tick size = 5 點（PASS）；時區 = JST（Asia/Tokyo，session 缺口吻合 OSE）；volume = per-minute contract。
- **Micro ≠ Mini**：重疊 137,839 筆，volume 吻合率僅 1.18%（差異 21,243 口）→ 獨立契約，非 duplicate。
- close = **BAR_CLOSE**（非 settlement）；settlement 歷史仍僅 1 日（QROS 的 53 個 JPX_SETTLEMENT manifest 全是 33 位元組失敗下載）。
- 決策：**DIRECT_MICRO_BAR_OOS_POSSIBLE** + **SUBSTANTIAL_DIRECT_BAR_SAMPLE_AVAILABLE**（796 天 ≥ 250）。
- **DIRECT_SETTLEMENT_INSUFFICIENT 維持不變**（未偽造 settlement）。
- 產物：`LOCAL_OSE_DATA_PROVENANCE_MANIFEST.yaml`、`PHASE2VB2_LOCAL_MICRO_PROVENANCE_REPORT.md`、
  `DIRECT_MICRO_BAR_OOS_PROTOCOL_DRAFT.yaml`（draft，未 pre-register）；tests 545 passed。

## 2V-B.1 本棒成果（READ-ONLY 鑑識，無登入/下單/訂閱/SDK 修改）
- Pre-registered `HISTORICAL_OOS_PROTOCOL.yaml`（v1，凍結）；`DIRECT_TARGET_COVERAGE.json`。
- **DIRECT OSE Micro settlement 歷史僅 1 交易日**（JPX 公開源當日-only，歷史 404）→ **INSUFFICIENT_EVIDENCE**（未用 proxy 補）。
- PROXY ^N225（1223 bars，~1090 origins）walk-forward（點-in-time、expanding、無 random split、test 未用於 tuning）。
- 模型：LAST_VALUE/SEASONAL_NAIVE/DRIFT/MA/RIDGE/VAR/KALMAN + XGB/LGBM + Chronos-2/TimesFM-3.0 + equal/dynamic ensemble。
- 統計：moving-block bootstrap 95% CI + Diebold-Mariano（Newey-West HAC）+ Benjamini-Hochberg FDR。
- **結論：所有模型 NO_EVIDENCE**（無一打敗 LAST_VALUE/DRIFT；direction ~50%；dynamic ensemble NO_EVIDENCE_OF_ENSEMBLE_EDGE）。
- 最大失效條件 = HIGH_VOL/TREND_DOWN。NHITS/NBEATSx = RUNTIME_BLOCKED（training-only）。
- 產物：`PHASE2VB_HISTORICAL_OOS_REPORT.md`、`MODEL_FAILURE_ANALYSIS.md`、
  `PROXY_REFERENCE_OOS_RESULTS.csv`、`DIRECT_OSE_MICRO_OOS_RESULTS.csv`、`REGIME_OOS_RESULTS.csv`、
  `OOS_EXAM_MANIFEST.yaml`；tests 533 passed。

## 發布前狀態（RELEASE CANDIDATE）
- build_id `ccabe1e1552d9ae7`；test **509 passed**；MCP **21 tools**；Skills **3**。
- Primary target `OSE_NIKKEI225_MICRO_FUTURES`（^N225=PROXY）。
- clean-clone reconstruction PASS（新 venv → import/MCP 21 tools）。
- `RELEASE_CANDIDATE_CHECKLIST.md` / `RELEASE_CANDIDATE_MANIFEST.yaml` 已建立。
- Provider request instrumentation（`services/provider_metrics.py`）關閉 observability gap。
- **Yuanta 四條 API family**：SPARK / Futures Legacy Quote / Futures Legacy Trading /
  Leveraged Trading（槓桿全球贏家 Web API，DOCUMENTED_ONLY）。

## 已知限制（不阻塞，誠實保留）
- **OSE Micro settlement 歷史資料缺口**：JPX 公開源僅當日（歷史 404）；完整歷史需 J-Quants API key（NEEDS_CONFIG）。
- **所有模型 historical OOS NO_EVIDENCE**（不 beat baseline；direction ~50%）；Dynamic Ensemble NO_EVIDENCE_OF_ENSEMBLE_EDGE。
- Dynamic Ensemble UNVALIDATED_FORWARD；BEA/e-Stat/EIA/EDINET NEEDS_CONFIG。
- TradingView 免費 15 分鐘延遲；SPARK Futures 0112 未解。
- **OSE Micro SPARK StkCode 已 VERIFIED**（`JNU<合約月>`；下單代碼 JNU；FunctionList SHA256 已存）。
- **Legacy Quote OSE/EASYWIN 實際 symbol：UNRESOLVED**（需 EasyWin 匯出對照表）。
- NHITS/NBEATSx RUNTIME_BLOCKED（training-only，無 runtime adapter）。
- Yuanta Legacy Quote T 盤 retest = DEFERRED。

## 下一步（下一棒）
- 本棒**未** git commit / push / release / tag；**未**選 Champion（無 candidate）。
- 下一棒候選：2V-C / 2V-D forward validation（若有 CHAMPION_CANDIDATE）或取 J-Quants key 補 settlement 歷史。

## SAFETY
NO LIVE TRADING / NO ORDER / NO BROKER CREDENTIAL / AUTO_PROMOTE_CHAMPION=false /
Yuanta quote-only、Trading API 未接 runtime、OrderApiExposureGuard PASS、secret scan 無真實 PII。

## Historical stop point (superseded by later user-authorized quote work)
- Historical phase prohibited commit/push/recorder. Later user authorization permits quote recorder engineering and publication. Live Trading and Yuanta order remain prohibited.
