# MARKET_AI_HUB — AGENT HANDOFF (durable)

Facts below are verified against the repo, not chat memory. If they disagree with the repo, the repo
wins. Refresh with `scripts/agent_bootstrap.ps1`. Last updated: 2026-09-25 W7.2 Yuanta portability hardening PASS; current-build safe-default recorder observed RUNNING; C2.3 runtime re-verification still pending.

## Current repair checkpoint

2026-09-25 C2 controlled-measurement-path initial implementation is `ed3e63360faca93f6a5a6b0af89fc1ecb51702bf`; correlation hardening is `9496eb9afa65e647b5fceca86610247ff24e258e`; review follow-ups are `30d32754ff284a6b32370b236ed1fc40283304e9`, `0203e9becf0f0894c3d9f33cfdc2aece448db921`, `873e6bd9697efe1bc2c67d1767c708b23af2df10`; maintenance-control source is `4cca09117ffda0fb2ead12de737ffcaf8b92ad9c`; request-script repair is `1452a45cf0c4de631d213eaa8648c3eae3b90211`; startup-observability source is `b9cfcb0e302e1520027d2c69adf363d15baf00c4`; current source/config build is `afd52f88a351541a`. Tracked `tick_detail_measurements.enabled=false` remains the safe default. Maintenance-only enable is a runtime start flag, graceful shutdown is a control-inbox action, and startup now records safe stage/error metadata so a failed owner start cannot be mistaken for a healthy recorder.

Runtime evidence schema is now `W3.3-C2.3` and carries the frozen process `runtime_build_id`. The OSE timestamp-basis cross-check is fail-closed against UTC-like and Taipei-like clock alternatives, and the evidence validation boundary now recomputes that cross-check from the bound raw batch plus request/callback times instead of trusting caller-supplied success flags. Feature Store provenance reads fail closed to an empty optional view on DuckDB/IO errors, and packet freshness never labels `LEGACY_TOP_LEVEL_RECEIPT_ONLY` data as FRESH. Local raw artifacts may contain tick prices; control-result and verification metadata do not expose prices.

Validation for the latest C2.3 source: focused `59 passed`; broader W2/W3/C1/quote regression `154 passed, 2 deselected`; final offline profile `1861 passed, 24 deselected, 132 warnings in 133.26s`, exit 0, excluding only `test_single_instance_lock_releases_after_error`. C2.3 accepts only the observed `15:45:01` closing-auction print and keeps `15:45:02+` fail-closed.
C2.3 source commit = `3e05af13762d430f875a35f2b288cf33188ce733`; GitHub source CI #162 = SUCCESS. The first C2.3 handoff publication commit is `3f4dda90485cf1a86bc16114e2edec40e837eff8`; this reconciliation commit supersedes that handoff text only.
Post-publication regression hardening commit `0d2693f` adds an end-to-end C2.3 positive case using a `15:45:01` closing-auction print: same-owner measurement persists raw + typed evidence, reload validation passes, and exact-contract terminal-close materialization keeps provider trade time at 15:45:01 while the session event remains 15:45:00. Focused measurement/materializer = `38 passed`; broader W2/W3/C1/quote = `155 passed, 2 deselected`; full offline = `1862 passed, 24 deselected, 132 warnings in 135.52s`, exit 0. Product source/build remains `afd52f88a351541a`.
Bridge regression commit `3ce826817834b20d26d671cd24a0aec8c1821e4a` connects the existing modules without changing product source: verified C2.3 DAILY materialization → canonical Feature Store → W3.2 candidate/precommit, enforces callback `available_at` visibility, then exercises a second-session C2.3 DAILY close → exact-contract settlement → W3.1 evaluation. Focused materializer/W3.2 = `45 passed`; broader W2/W3/C1/quote = `158 passed, 2 deselected`; full offline = `1865 passed, 24 deselected, 132 warnings in 144.28s`, exit 0. The synthetic evaluation explicitly remains `CALIBRATED=false`, `PREDICTIVE_EVIDENCE=NOT_ESTABLISHED`, `TRADING_EDGE=NOT_ESTABLISHED`; this is engineering evidence only. Product source/build remains `afd52f88a351541a`.

Live truth changed during the first authorized maintenance attempt. At 15:56 JST the date was a valid OSE derivatives session. Before any new owner was started, both old recorder PIDs `6432/14952` were already absent; the last stale status had heartbeat `2026-09-25T06:46:17.888693Z`, `DEGRADED`, `pending_records=772`, `dropped_records=0`, so a buffered-data gap is possible and must not be hidden. No same-day tick-detail control/evidence artifact existed. FunctionList resolver uniquely selected the nearest valid OSE micro contract `JNU2612` (market 207, verified=true); old runtime subscriptions also contained next `JNU2703`, which was not treated as the active contract.

The first current-build owner start used runtime-only measurement enable. The launcher printed `YUANTA_LIVE_STARTING pid=9060`, but that process and any recorder child disappeared before a fresh status or log was written; the old status remained stale and both recorder stdout/stderr files were zero-length. Per the maintenance contract, no GetStkTickDetail request was made. Subsequent non-login diagnostics passed, so the first live attempt was **FAIL_CLOSED_STARTUP_UNOBSERVED**.

The next user continuation performed exactly one new start attempt at about 16:32 JST using build `ba7c0e1b9ca9d62c`. Startup telemetry proved SPARK securities login success (`login_msg_code=0001`), `startup_stage=RUNNING`, runtime measurement gate=true, subscriptions=42, pending/dropped=0, and the start script returned `YUANTA_LIVE_RUNNING pid=33448 status=DEGRADED build=ba7c0e1b9ca9d62c`. About 12 seconds later PID `33448` was absent and its heartbeat remained frozen at `2026-09-25T07:32:13.645637Z`; there was no callback/W1-W2 provenance, clean STOPPED status, stderr/stdout, or crash dump. Because fresh-heartbeat + W1/W2 provenance failed, **no GetStkTickDetail request was queued and no second login retry was made in that execution**. This is **SECOND_ATTEMPT_FAIL_CLOSED_AFTER_LOGIN / RUNNER_CHILD_LIFETIME_BLOCKER**. The evidence is consistent with one-shot Runner child cleanup; it is not evidence of broker login failure. **At the end of that attempt the recorder was NOT RUNNING.** Actual runtime timestamp evidence, eligible real DAILY terminal close, and W3.2 ACTUAL_FORWARD_EVIDENCE remain **NONE_YET**.

Third maintenance attempt proved the foreground Runner Job path. Recorder PID `11448` stayed RUNNING with login `0001`, fresh callbacks/W1-W2 `PER_FIELD_ONLY` provenance, runtime measurement gate=true and exact FunctionList contract `JNU2612`. Exactly one request `tick-detail-01892509e2e742619eef0c0d07349d39` produced canonical raw snapshot `w33_tick_cbce3cba39291cd1f14e`. C2.2 correctly returned `TICK_DETAIL_TIMESTAMP_BASIS_BLOCKED / RAW_TRADE_AFTER_DAY_CLOSE`; raw typed reload PASS and its clock range is 15:39:47–15:45:01. No second measurement was issued. Foreground recorder then graceful-shutdown cleanly and the Runner Job exited 0.

C2.3 (`afd52f88a351541a`) changes the evidence schema to `W3.3-C2.3` and timestamp method to `OSE_SESSION_LOCAL_CLOCK_CROSSCHECK_V2`. It permits only the observed one-second closing-auction print grace; `15:45:02+` remains blocked and the session event timestamp remains 15:45. Because the C2.2 blocked result did not persist a complete typed verification artifact, **RUNTIME_TIMESTAMP_VERIFIED remains NONE_YET**; do not retroactively manufacture evidence.

Read-only inspection at 2026-09-25 17:30 Asia/Taipei found a current-build safe-default recorder invocation running: venv Python parent PID `25480` spawned interpreter child/status PID `26476`; status=`RUNNING`, login=`0001`, subscriptions=42, fresh quote heartbeat, health_reasons=[], dropped_records=0, persistence_error=null, runtime_build_id=`afd52f88a351541a`, and `tick_detail_measurements_runtime_enabled=false`. Treat the parent/child process pair as one invocation; do not start a second broker owner. No broker action was performed by this inspection.

Read-only owner-preflight commit `bef25d54ebea22bcb93d8466f657fe7d460496e9` adds `scripts/check_yuanta_recorder_owner.ps1` without changing runtime source/config build. It uses `status.json` PID as owner truth, collapses parent/child matching Python processes into one invocation chain, reports independent matching chains separately, and checks heartbeat freshness, runtime/disk build identity, runtime measurement gate, tracked safe default, and health reasons. Live preflight classified the current process tree as `SAFE_DEFAULT_OWNER_HEALTHY` with owner invocation PIDs `[25480,26476]`, no independent matching PID, both measurement gates false, and broker_action_performed=false. Validation: PowerShell parse PASS; focused `26 passed, 2 deselected`; broader `159 passed, 2 deselected`; full offline `1866 passed, 24 deselected, 132 warnings in 137.11s`, exit 0. Product build remains `afd52f88a351541a`.
Start/stop preflight-gating commit `639de5f3fe3fda1bcb0c4b31055c3bdf2ab4e930` then makes both lifecycle scripts consume that classification before mutation. `start_yuanta_live_recorder.ps1` remains idempotent for a healthy existing owner and blocks duplicate/unverified/stale-build/tracked-gate hazards before any new process; live validation returned `YUANTA_LIVE_ALREADY_RUNNING` and preserved owner chain `[25480,26476]`. `stop_yuanta_live_recorder.ps1` now returns `YUANTA_LIVE_NOT_RUNNING` before creating a shutdown request when there is no verified owner, preventing a stale shutdown JSON from killing a future recorder; duplicate/unverified owner states block fail-closed. Validation: PowerShell parse PASS; focused `27 passed, 2 deselected`; broader `160 passed, 2 deselected`; full offline `1867 passed, 24 deselected, 132 warnings in 141.86s`, exit 0. Product build still `afd52f88a351541a`.
Request-gating commit `ef59565ebb502957f8d1b9c8e77f39a7ddeaa3af` closes the remaining mutation entrances. `request_yuanta_quote.ps1` now requires a healthy verified running owner (`SAFE_DEFAULT_OWNER_HEALTHY` or `MAINTENANCE_OWNER_RUNNING`) before resolving/creating the inbox; `request_yuanta_tick_detail_measurement.ps1` requires `MAINTENANCE_OWNER_RUNNING`, runtime measurement gate=true, tracked gate=false, runtime/disk build match, RUNNING status and no health reasons before it can queue anything. PowerShell parse PASS; static contract `15 passed, 1 deselected`; broader lifecycle/C2/W3/quote `158 passed, 2 deselected`; full offline `1868 passed, 24 deselected, 132 warnings in 126.74s`, exit 0; diff check PASS; targeted secret scan 0. No request script was executed against the broker during this validation. Scripts/tests do not change product build, which remains `afd52f88a351541a`.

Read-only continuation at 2026-09-25 19:25 Asia/Taipei again classified the live recorder as `SAFE_DEFAULT_OWNER_HEALTHY`, with a single parent/child invocation chain, fresh heartbeat, runtime/disk build both `afd52f88a351541a`, runtime/tracked measurement gates both false, and no health reasons. PR #55 checks were SUCCESS at the then-current request-gating head. The W3.3 source contract's stale pre-C2 live-state bullets were reconciled to this current evidence boundary. No broker mutation was performed.

Next C2 live gate is one new C2.3 maintenance measurement in a valid 15:45–17:00 JST window using the proven foreground Runner Job pattern. Because the safe-default owner is currently running, preserve it outside the maintenance window; at the authorized live step, hand over the single owner safely rather than starting a duplicate. Typed evidence must persist and reload successfully before any exact-contract DAILY close is materialized. Once that real DAILY row exists, the C2.3→Feature Store→W3.2 precommit/settlement/evaluation path is now regression-covered and requires no manual glue.

W7.1 reconstruction-verifier correctness was advanced independently while that live gate was unavailable. A real non-repo-cwd run from `%TEMP%` first reproduced two false failures: the verifier read relative `config/...` paths from the caller cwd, and after fixing that it still rejected the current manifest sentinel `system.build_id=runtime_introspected` as if it had to be a frozen 16-hex build. `scripts/reconstruct_verify.ps1` now enters its own repo root before relative operations, validates the manifest sentinel, and separately checks `build_fingerprint()['build_id']` as the runtime identity. The same `%TEMP%` execution now returns `RESULT: PASS`; `tests/test_phase2ib.py` carries a regression contract. This proves caller-cwd independence on the current machine only; it is not yet a clean-new-venv/new-Windows/COM/WinCred relocation certification.

W7.2 Yuanta portability hardening removed remaining machine-specific maintenance paths from tracked scripts. `check_yuanta_futures_com.ps1` no longer inserts `D:\MARKET_AI_HUB\src`; it relies on the script-derived repo root. `setup_yuanta_futures_x86.ps1` no longer searches a named user's Python path, accepts `MARKET_AI_PYTHON_X86` / `-PythonX86`, verifies the interpreter is 32-bit before any install, and fail-closes on venv/pip exit codes. `yuanta_sdk_forensics.py` now resolves the current user's Documents/Downloads or an explicit `MARKET_AI_YUANTA_SDK_ROOTS`. Read-only COM smoke remained `READY_FOR_AUTH`; `%TEMP%` + an external `MARKET_AI_DATA_ROOT` containing Chinese characters and spaces resolved the recorder root correctly; targeted portability tests=`15 passed, 1 deselected`; full offline=`1871 passed, 24 deselected, 132 warnings in 132.68s`, exit 0, still excluding only the live-owner mutex test. Product build remains `afd52f88a351541a`. Implementation/publish commit=`86cea574927988e78793dd307af2e3351f73e59c`; PR #55 remains OPEN/MERGEABLE and CI run `36133883630` is SUCCESS. This does not certify a new venv/new Windows/WinCred/certificate migration.

W7.3 main-environment relocation bootstrap closes a separate false-positive risk in `scripts/setup_windows.ps1`: the prior installer trusted PATH `python` and `platform.machine()`, which on this machine points to Python 3.11 32-bit while still reporting `AMD64`. The installer now resolves/accepts only CPython 3.11/3.12 with a real 64-bit pointer width, prefers 3.12 then 3.11 from Windows Python Launcher, supports explicit `-PythonExe`, and never auto-installs Python. New `-BootstrapOnly` creates/verifies `.venv` without pip/network activity. `scripts/verify_source_relocation_bootstrap.ps1` copies only tracked source to a new temp checkout, launches bootstrap from non-repo cwd, and verifies new venv/source identity does not reference the original checkout. Real smoke used a Chinese+space destination, selected Python 3.12.13 64-bit, returned `SOURCE_RELOCATION_BOOTSTRAP_PASS`, preserved build `afd52f88a351541a`, and `old_repo_in_syspath=false`. Targeted installer tests=`4 passed, 14 deselected`; full offline=`1873 passed, 24 deselected, 132 warnings in 147.68s`, exit 0. This proves source relocation + fresh no-download venv bootstrap on the current Windows machine; full dependency install/new Windows/WinCred/certificate/COM registration are still separate gates.

W7.4 offline-backup restore correctness found three real defects by running an actual restore drill rather than trusting the existence of `SHA256SUMS.txt`. First, `create_offline_backup.ps1` ignored robocopy/pip native exit codes. Second, PowerShell 5.1 `Get-FileHash` failed on deep Yuanta vendor paths. Third and most important, `/XD data models reports ...` excluded nested runtime source directories such as `src/market_ai_hub/data`, `src/market_ai_hub/models`, and `config/data`, so a checksum-complete backup restored to a different runtime build (`bbef69fe330230ab`). The script now fail-closes native commands, uses long-path-safe SHA256, and excludes only absolute repo-root runtime/data directories (with `__pycache__` remaining a global name exclusion). New `verify_offline_backup.ps1` validates all manifest hashes, rejects missing/duplicate/path-escape/tampered/unchecksummed files, and `verify_offline_backup_restore_drill.ps1` performs a real basic backup, verification, restore to another path, excluded-directory check, restored-source import, and build-id equality check. Final drill verified 2191 files and restored build=`afd52f88a351541a`; targeted regression=`2 passed`; full offline=`1875 passed, 24 deselected, 132 warnings in 139.90s`, exit 0. No wheels/models/private market data were downloaded or copied; this validates the basic source/offline-manifest backup tier, not private data/WAL-consistent database restore.

W7.5 Scheduled Task relocation closes a stale-path defect in `register_forward_shadow_task.ps1`: the old script left an existing task unchanged, so a relocated checkout could continue executing the old source path. Both research-task and forward-shadow registration scripts now expose `-DryRun` plans derived from their current repo root. Forward-shadow registration refreshes an existing task by default (`-Force`) and only preserves it when explicitly requested via `-PreserveExisting`. A regression copies the scripts to a Chinese+space temp checkout, invokes both from non-repo cwd, and verifies generated actions contain the relocated repo and no original checkout. No Scheduled Task was registered or modified during validation. Targeted reconstruction tests=`17 passed`; full offline=`1880 passed, 24 deselected, 132 warnings in 141.67s`, exit 0; that total also included three concurrent untracked research-snapshot tests from another workstream, which were not owned or committed by this package. Implementation commit=`95c34cedf21ba1dfa4e7a48b23ee8da53ad6677b`; CI run `36142106665` SUCCESS. Product build remains `afd52f88a351541a`.

W7.6 MCP client-config relocation removes the remaining manual `<PROJECT>` substitution requirement. New `scripts/render_mcp_config.py` reads the tracked generic/Cherry templates and renders the `market-ai` command from an explicit or current project root, with correct JSON escaping for Chinese/space paths. It prints to stdout by default and writes only when `--output` is explicitly supplied; `--require-command` fail-closes if the generated MCP executable path does not exist. Regression runs both clients from non-repo cwd against a Chinese+space relocated root and confirms the generated JSON contains no placeholder or original checkout path. Real current-root render also passed. No external MCP client configuration was modified. Targeted reconstruction tests=`18 passed`; full offline=`1881 passed, 24 deselected, 132 warnings in 132.50s`, exit 0. Implementation commit=`db9eeed6b9aaba540fcb2acef19de3ea2cd8e86c`; CI `36143262904` SUCCESS. Product build remains `afd52f88a351541a`.

W7.7 adds machine-readable `docs/development/W7_PORTABILITY_ACCEPTANCE.yaml` so current-machine PASS evidence cannot be collapsed into a false all-up portability claim. At the W7.7 publication point PASS was limited to W7.1–W7.6 cells; full dependency installation, clean new Windows, WinCred recreation, certificate reimport, and Yuanta COM registration were explicitly `UNVERIFIED_EXTERNAL_GATE`; private research-data restore was still a separate workstream; C2.3 runtime re-verification remained `WAITING_TIME_WINDOW`. W7.8 below subsequently closes the current-machine private research-data cell only. The matrix intentionally lives under docs rather than config: an initial config placement changed runtime build to `c555afda8269c1cc` and failed three frozen-build regressions, so it was moved out of the product fingerprint surface. Build returned to `afd52f88a351541a`; targeted matrix/build regressions=`22 passed`; final full offline=`1882 passed, 24 deselected, 132 warnings in 172.30s`, exit 0.

W7.8 private research-data consistency completes the previously interrupted local snapshot workstream without adding any private data to Git. New `create_research_data_snapshot.py`, `verify_research_data_snapshot.py`, and `restore_research_data_snapshot.py` handle DuckDB/SQLite/Parquet only, explicitly exclude `live/**` and `backups/**`, reject snapshot destinations inside DATA_ROOT, reject restore overwrite/path overlap, verify SHA256 + exact file inventory + table row counts + `prediction_id` digest when present, use DuckDB/SQLite consistent copy paths, and require stable Parquet source hashes. Snapshot discovery and verification also fail closed on symlinks. Real current-machine temp drill copied/verified/restored 8 DuckDB + 1 SQLite + 5 Parquet, excluded 1686 live files, restored 14 files with no `live/`, then removed all temp artifacts. Targeted=`4 passed, 1 skipped` (Windows symlink creation unavailable); full offline=`1884 passed, 1 skipped, 24 deselected, 132 warnings in 133.70s`, exit 0. This closes only the current-machine `private_research_data_consistent_restore` cell; it is not a live-recorder backup and not clean-new-Windows certification. Implementation commit=`f3faf193b34bae714c547dddba525a93edd467fb`; CI `36209628743` SUCCESS. Product build remains `afd52f88a351541a`.

W8.1 dependency-lock security repair addresses both open GitHub Dependabot alerts visible on the default branch for `requirements-lock-windows-x64.txt`. Both were `setuptools==78.1.0`: high `GHSA-5rjg-fvgr-3xxf` requires `>=78.1.1`, while medium `GHSA-h35f-9h28-mq5c` requires `>=83.0.0`; therefore the Windows lock security floor is now exactly `setuptools==83.0.0`, with both advisory IDs recorded beside the pin. The lock header now states that security-patched reconstruction is no longer bit-for-bit identical to the original freeze. No package installation was performed in this work package; fresh-install compatibility remains an external installation gate. Targeted reconstruction=`20 passed`; full offline=`1883 passed, 24 deselected, 132 warnings in 170.00s`, exit 0; runtime build remains `afd52f88a351541a`. Implementation commit=`c2d76febca2c994b3678391a5b484d15b1d77319`; CI `36208910703` SUCCESS. GitHub alerts are default-branch state, so until PR #55 is merged this package is `PATCH_IN_PR / REMOTE_ALERT_PENDING_MERGE`, not "alert resolved".

2026-09-25 C2 offline correctness implementation is commit `92e178e4ea6cad632d071747efe1c273bcc79efc`; source build is `b6cfc2ceae89d221`. Raw W3.3 tick-detail batches now remain permanently UNVERIFIED, canonical raw snapshot identity excludes verification state, SPARK records bounded request/callback correlation metadata, and terminal-close materialization requires a separate typed runtime verification artifact bound to the exact request, callback, returned market/code and canonical source snapshot. Ambiguous duplicate outstanding requests do not guess correlation. The controlled window is checked from actual request time (and callback time), not callback receipt substituted for request time.

C2 also adds a reviewed `DERIVED_DAILY` Feature Store gate for exact contract-specific OSE terminal closes. Trade timestamp remains provider timestamp; the event timestamp is the verified 15:45 JST session-close boundary. TICK does not silently become DAILY. Focused C2/W3.3 = 35 passed; related W2/W3/C1 = 134 passed; final offline profile = 1834 passed / 24 deselected / 132 warnings in 140.87s, exit 0, excluding only the live-owner-conflicting `test_single_instance_lock_releases_after_error`. Changed-file secret scan = 0; diff check PASS. Three stale build-id freeze assertions were updated to the new source fingerprint; no safety gate or test was removed.

Evidence boundary: **C2_OFFLINE_CORRECTNESS_PASS != RUNTIME_TIMESTAMP_VERIFIED != DATA READY != ACTUAL_FORWARD_EVIDENCE != CALIBRATED != TRADING EDGE**. No broker login/logout/restart/subscription/order/account action occurred. Actual runtime timestamp evidence remains **NONE_YET** and W3.2 actual forward evidence remains **NONE_YET**. Read `research/phase3/reports/C2_W33_RUNTIME_EVIDENCE_TERMINAL_CLOSE_2026-09-25.md`.

The pre-existing W3.3 contract/report files were deliberately excluded from C2 implementation commits until ownership was clear; this handoff reconciles them to the current C2.2 contract without changing the historical source-foundation evidence. The 2026-09-25 first maintenance window was explicitly authorized and attempted; it ended fail-closed before measurement.

2026-09-25 C1 evaluation-comparison package is implemented in commit `50f209a095a151b6ae42c6db5d0d462d11fd2395`; runtime build is `c64b98bd4a09d576`. It adds explicit VALID/FAILED/ABSTAINED/NONFINITE/INVALID_TARGET accounting, common-origin pairwise metrics plus each model's full coverage, fail-closed finite/accounting persistence, C1.1 leaderboard version isolation, horizon-aware random walk, train-only classification majority baseline, and aligned 20-session rates lookback. CLI run now persists pairwise rows and compare reads those rows instead of comparing different success subsets.

Validation: initial C1 regression was 11 passed / 4 failed; final focused is 198 passed / 6 deselected, exit 0. Final offline profile is 1804 passed / 35 deselected / 110 warnings, exit 0, explicitly excluding only `test_single_instance_lock_releases_after_error` because the Windows global quote-owner mutex is already held by the live recorder. The unfiltered run was 1802 passed / 34 deselected / 1 failed at that mutex. The recorder was not stopped/restarted to make the test pass. Changed-file secret scan = 0; diff check PASS.

The earlier `ea29c12...` credibility correction and W3.2 checkpoint remain historical evidence; read `MODEL_CREDIBILITY_PLAN_2026-09-25.md`, `MODEL_CREDIBILITY_VALIDATION_2026-09-25.md`, and `research/phase3/reports/C1_MODEL_EVALUATION_CORRECTNESS_2026-09-25.md` before using old tournament results. Old rankings require versioned re-evaluation and cannot be carried forward.

W3.3 tick-detail source code already exists; OSE timestamp basis and terminal-close materialization still require runtime evidence. Pre-existing staged W3.3 contract/report files were preserved and are not part of commit `50f209a`. Do not redo W3.1/W3.2/W3.3 engines. No live broker action was taken.

Historical C1 handoff named C2 as the next package. Its offline correctness portion is now complete as recorded above. The maintenance authorization that was pending at that historical checkpoint was granted on 2026-09-25; the first live attempt then failed closed before measurement, as recorded in the current section. C3/C4 remain gated on real C1/C2 inputs.

The W3.2 checkpoint below is historical, including its runtime build, not the latest source identity.

Read `research/phase3/reports/W32_PRECOMMITTED_FORWARD_CYCLE_2026-09-25.md` first, then the W3.1 governance and W2 reports. W3.2 implementation commit is `2f374ad533a74e3647fdfdeb73d9ebb2f379631a`; runtime build_id is `81f02a25847b9e65`.

Historical W2 handoff recorded recorder adoption as pending. That historical observation later became stale. The latest 2026-09-25 read-only inspection is the current truth: a current-build safe-default recorder is RUNNING with `PER_FIELD_ONLY` provenance, runtime build `afd52f88a351541a`, and tick-detail measurement runtime gate=false. C2.3 typed runtime re-verification is separately pending. Do not infer process build from disk alone; use the recorder's own `runtime_build_id`.

Offline W2 reader/replay now maps trade/bid/ask independently from per-field provenance into the existing V2-A.2 `FactorRepresentationObservation`, preserves V2-H lineage/source IDs, rejects market/contract/session mismatches, out-of-order receipts, partial files and persistence/overflow truth, and never combines source time-of-day with a fabricated date. Old schema without per-field provenance is explicitly downgraded to `LEGACY_TOP_LEVEL_RECEIPT_ONLY` and cannot become DIRECT_LIVE.

W2 offline contract and W3.1 governance remain **PASS**. W3.2 now adds a minimal OSAKA_MICRO/JNU 1-session `last_price_naive` forward cycle: only contract-specific DAILY/PIT-safe/source-snapshotted closes can precommit between the verified 15:45 JST source close and 17:00 JST target night open; settlement must use the same contract and exact sealed target close, then W3.1/2I.1 evaluate it. Current runtime evidence still has no eligible C2.3 typed DAILY Feature Store candidate, so **actual forward evidence remains NONE_YET and no real prediction was inserted**. A current-build safe-default recorder is now running with measurement gate=false; preserve the single owner until the next authorized maintenance handover.

## Read first (order)

1. `AGENTS.md` (repo root)
2. `scripts/agent_bootstrap.ps1` output (actual branch/HEAD/build_id/schemas/phase/providers)
3. this file
4. `docs/development/project-status.md`
5. the current phase contract under `docs/architecture/` (see map below)

## Architecture contracts (current)

| Track | Schema | Contract |
|---|---|---|
| V2-A As-Of / timestamp truth | 2A.2 | `docs/architecture/v2-asof-data-contract.md` |
| V2-A.2 Session + factor routing | 2A.2 | `docs/architecture/v2-session-factor-routing-contract.md` |
| V2-B Gap / session | 2B.1 | `research/v2/gap_session.py` |
| V2-C Daily labels | 2C.2 | `research/v2/labels.py` |
| V2-D State machine | 2D.4 | `docs/architecture/v2-state-machine-contract.md` |
| V2-E Extension / exhaustion | 2E.3 | `docs/architecture/v2-extension-exhaustion-contract.md` |
| V2-F Catalyst response | 2F.3 | `docs/architecture/v2-catalyst-response-contract.md` |
| V2-G Sequential updating | 2G.2 | `docs/architecture/v2-sequential-update-contract.md` |
| V2-H Prediction audit DB | 2H.3 | `docs/architecture/v2-prediction-audit-contract.md` |
| W3 Evaluation governance | W3.1 | `docs/architecture/v2-evaluation-governance-contract.md` |
| W3 Forward cycle | W3.2 | `docs/architecture/v2-forward-cycle-contract.md` |
| V2-I Calibration evaluation | 2I.1 | `docs/architecture/v2-calibration-evaluation-contract.md` |
| Price/Probability Map | 3A.2.3 | `research/price_probability_map.py` |

Closed foundations (do not redo): V2-A.2, V2-B.1, V2-C.2, V2-D.4, V2-E.3, V2-F.3, V2-G.2, V2-H 2H.3,
V2-I 2I.1; W3.1 governance and W3.2 forward-cycle engines are closed. Real W3 forward sample accumulation remains evidence/data work, not an engine gap.
V2-I 2I.1 closed = **evaluation engine only**. CALIBRATION FITTING and probability publication are
**NOT STARTED**; `ACTUAL_CALIBRATION_EVIDENCE = NONE_YET`; `CALIBRATED` stays FORBIDDEN until real
settled probabilistic samples exist.

## Yuanta — three separate API families (do not mix)

```
SECURITIES API
= Yuanta SPARK / 元大證券API
= SPARK API supports securities + futures MARKETS by official contract
= securities profile login SERVER_VERIFIED MsgCode=0001
= measured quote identity must state account_profile=SECURITIES and market=TAIFEX / market=OSE / CME / CBOT / CBOE / NYBOT as applicable
= 2026-09-24 PROD matching callbacks VERIFIED on TAIFEX/OSE/CME/CBOT/CBOE/NYBOT
= night-session quote codes are API-specific (e.g. TMFPM*/JNUPM*); resolve dynamically from FunctionList
= primary cross-market live quote provider
= API_SUPPORT != FUTURES_ACCOUNT_ENTITLEMENT: separate futures-profile login still returns 0112

FUTURES QUOTE API
= YuantaQuote ActiveX/COM (ProgID YUANTAQUOTE.YuantaQuoteCtrl.1, x86 sidecar)
= independent quote API
= T / T+1 login SERVER_VERIFIED LogonOK (Status=2, code=0)
= 2026-09-24 T+1 TX/MX/TMF/UNF matching OnGetMktData VERIFIED
= domestic TAIFEX live backup; current overseas AddMktReg path is NOT verified

FUTURES TRADING API
= YuantaOrd (Yuanta.YuantaOrdCtrl.1)
= separate product, NOT connected to runtime
= NO ORDER (quote-only policy)
```

Official evidence now confirms SPARK supports futures markets, and securities-profile live callbacks
have been measured across multiple futures venues. Keep the claim precise: **SPARK securities profile
quote success != SPARK futures-account entitlement**. The futures profile still returns 0112.
The independent YuantaQuote COM API remains the separate FUTURES QUOTE API family and is a verified
domestic TAIFEX backup. Full method/evidence: `docs/integrations/yuanta/YUANTA_LIVE_MULTIFACTOR_GUIDE_ZH_TW.md`
and `config/yuanta_live_factor_matrix.yaml`. Rebuild/setup rules are in `docs/integrations/yuanta/YUANTA_FROM_SCRATCH_SETUP_ZH_TW.md`, product-code/session rules in `docs/integrations/yuanta/YUANTA_PRODUCT_CODE_AND_SESSION_RULES_ZH_TW.md`, and official download/source URLs in `config/yuanta_source_manifest.yaml`.

## System principles (Yuanta)

```
Yuanta futures unavailable != system blocked

Taiwan stock : use verified securities data where it is actually usable
TAIEX / TX / MTX / TMF : cash and futures identities stay separate forever
  no fresh futures feed -> persist NOT_AVAILABLE
  never let cash impersonate a future; never let a future overwrite cash
```

## Provider status truth (machine-readable: `integrations.yuanta.capabilities.PROVIDER_STATUS`)

```
legacy_futures_auth    : VERIFIED
legacy_domestic_quote  : LIVE_CALLBACK_VERIFIED
spark_securities_taifex_quote : LIVE_CALLBACK_VERIFIED
spark_securities_ose_quote    : LIVE_CALLBACK_VERIFIED
spark_securities_cme_quote    : LIVE_CALLBACK_VERIFIED
spark_securities_cbot_quote   : LIVE_CALLBACK_VERIFIED
spark_securities_cboe_quote   : LIVE_CALLBACK_VERIFIED
spark_securities_nybot_quote  : LIVE_CALLBACK_VERIFIED
spark_futures          : SPARK_FUTURES_ACCOUNT_ENTITLEMENT_BLOCKED (futures-profile login measured 0112)
ose_micro_live         : LIVE_CALLBACK_VERIFIED_SPARK_SECURITIES
taifex_live            : LIVE_CALLBACK_VERIFIED_SPARK_AND_LEGACY
```

## Legacy quote (EASYWIN) — canonical API facts

```
AddMktReg(symbol, UpdateMode, ReqType, SetMap)
  ReqType 1 = T 盤 ; ReqType 2 = T+1 盤        (official sample / reg_Ses2.log evidence: TXFL7, not TXFL7PM)
  UpdateMode default = 4 (SnapshotUpd)         (official Python sample)
  SetMap = 0
Legacy canonical API symbol = BASE symbol (e.g. TMFJ6) for BOTH T and T+1.
  `xxxPM` symbols stay as EasyWin UI/alias metadata only; never the AddMktReg canonical symbol.
```
Source of truth: `<yeswin>\AGENT\YSTrader\Data\List\M.TFX.TXT` (read-only, `easwin_resolver.py`).

## Truthfulness rules

- `ENGINE PASS != DATA READY != CALIBRATED != PREDICTIVE EVIDENCE != TRADING EDGE`.
- No fabricated timestamps, prices, probabilities, or provider status.
- Keep cutoff / leakage gates machine-enforced; report `NOT_AVAILABLE` instead of guessing.
- Never persist secrets; Windows Credential Manager only, masked output only.
- Quote-only: no order, no account query, no position/balance。即時行情由單一常駐 `live_quote_recorder` 負責；agent 必須讀 `data/live/yuanta/latest.json` 或透過 `scripts/request_yuanta_quote.ps1` 追加訂閱，不得自行重複登入/登出。

## Current gates

```
V2-A.2  PREV2H_V2A2_SESSION_FACTOR_ROUTING_FOUNDATION_PASS
V2-G.2  PHASEV2G_SEQUENTIAL_UPDATING_SCAFFOLD_PASS
V2-H.3  PREDICTION_AUDIT_OUTCOME_MATURITY_PASS
W3.1    OUTCOME_EVALUATION_GOVERNANCE_PASS
        evaluation_as_of + homogeneous scope + duplicate/supersession gates
W3.2    PRECOMMITTED_FORWARD_CYCLE_ENGINE_PASS
        ACTUAL_FORWARD_EVIDENCE = NONE_YET; eligible DAILY contract-close input absent
V2-I.1  PHASEV2I_CALIBRATION_EVALUATION_FOUNDATION_PASS
        YUANTA_SPARK_SECURITIES_FUTURES_QUOTE_PROBE_COMPLETE
V2-I    evaluation engine only — CALIBRATION FITTING NOT STARTED. ACTUAL_CALIBRATION_EVIDENCE =
        NONE_YET; CALIBRATED is FORBIDDEN until real settled probabilistic samples exist in the DB.
```
