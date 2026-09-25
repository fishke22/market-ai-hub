# C2 W3.3 Runtime Evidence / Terminal-Close Correctness — 2026-09-25

## 結論

C2 離線 correctness gate **PASS**。Implementation commit: `92e178e4ea6cad632d071747efe1c273bcc79efc`; source build_id: `b6cfc2ceae89d221`.

這個 PASS 只表示：raw `GetStkTickDetail` snapshot、SPARK request/callback trace、typed runtime verification evidence、contract-specific DAILY terminal-close materializer、Feature Store derived-Daily gate 與 W3.2 model-input boundary在離線反例下能 fail closed。它**不是** OSE timestamp basis 已實機驗證、DATA READY、actual forward evidence、CALIBRATED、PREDICTIVE EVIDENCE 或 TRADING EDGE。

本棒沒有 broker login/logout/restart/subscription/order/account/position/balance 操作；現場 recorder owner 未被打斷。Actual runtime timestamp verification = **NONE_YET**；ACTUAL_FORWARD_EVIDENCE = **NONE_YET**。

## 已修正的 correctness 缺口

1. Raw `TickDetailBatch` 永遠保持 `UNVERIFIED_OSE_TIMESTAMP_BASIS`；caller 不再能把 raw batch 自行升級為 verified。
2. Raw snapshot canonical identity 排除 verification state；驗證狀態改變不再造成 snapshot identity 自相矛盾。
3. SPARK runtime 保留 actual request time、bounded request id、market/code/count/acceptance 與 callback receive time/returned market/code；account 不進 trace。
4. 相同 market/code 有多個 outstanding requests 時 callback 不猜 request id；保持 uncorrelated，不能產生有效 evidence。
5. 新 `TickDetailRuntimeVerificationEvidence` 綁定 runtime request id、request/callback times、requested/returned market/code、raw snapshot id、timestamp-basis method/crosscheck，並用 deterministic evidence id 做完整性檢查。該 hash 是 integrity id，不是 broker signature。
6. Materializer 不再信任 status 字串；必須取得與 raw batch canonical snapshot 完全匹配的 typed evidence。
7. controlled window 以**實際 request time**驗證 15:45 <= JST < 17:00；callback 也必須在 controlled window 內。15:44:59 request / 15:45:01 callback 會 BLOCK。
8. source trade timestamp 與 session close boundary 分離：provider timestamp 保留最後有效成交時間，DAILY feature event timestamp 使用已驗證 session close boundary。
9. Feature Store 新增明確 `DERIVED_DAILY` gate；TICK 不能藉此默認成 DAILY，future contract 必須 CONTRACT / roll NONE / exact contract identity / PIT-safe / session-close timestamp matching。
10. derived DAILY lineage 同時包含 raw source snapshot id 與 runtime verification evidence id。

## 反例

已覆蓋：
- raw batch 自行宣告 runtime verified → constructor reject；
- 缺 runtime evidence → BLOCK；
- evidence source snapshot mismatch → BLOCK；
- noncanonical raw snapshot id → BLOCK；
- requested/callback market/code mismatch → BLOCK；
- evidence id tamper → BLOCK；
- request 在 15:45 前、callback 在 15:45 後 → BLOCK；
- callback >= 17:00 → BLOCK；
- uncorrelated request/callback → evidence builder reject；
- duplicate outstanding identical tick-detail requests → callback 不猜 correlation；
- after-close tick / wrong contract month / zero-volume terminal row / conflicting close → fail closed；
- valid path → DAILY terminal_close 可進既有 Feature Store/model-input contract，trade time 與 close boundary 分開。

## 驗證

- C2/W3.3 focused: `35 passed`.
- Related W2/W3/C1 regression: `134 passed`.
- 首輪完整 offline profile：`1831 passed, 24 deselected, 3 failed`；三個 failure 全為 stale build-id snapshot，實際 source fingerprint 已從 C1 `c64b...` 變為 C2 `b6c...`。只更新三個既有 freeze assertions，沒有刪除或放寬測試。
- 最終 offline profile（明確排除現場 recorder 已持有的 `test_single_instance_lock_releases_after_error`）：`1834 passed, 24 deselected, 132 warnings in 140.87s`，exit 0。
- changed-file secret scan: 0 hits。
- `git diff --check`: PASS。

## 尚未完成

- OSE `StickDetail.TimeStamp` basis 尚未做 controlled live cross-check。
- 尚無真實 runtime evidence artifact。
- 尚無真實 contract DAILY terminal-close row 可宣稱 DATA READY。
- W3.2 actual forward prediction/outcome sample 仍為 NONE_YET。
- calibration fitting 未開始。
- C2 controlled-measurement runtime adoption / recorder restart 仍需明確 maintenance-window 授權；W1/W2 per-field recorder adoption 已另行觀測成立。

## 發布與工作樹邊界

Implementation commit 只包含 C2 code/tests。開工前已 staged 的：
- `docs/architecture/v2-tick-detail-source-contract.md`
- `research/phase3/reports/W33_TICK_DETAIL_SOURCE_2026-09-25.md`

在 `92e178e` implementation checkpoint 時仍屬 pre-existing staged W3.3 work，沒有被偷偷帶入 implementation commit；後續 controlled-path handoff 已逐段重新核對並將它們更新到 C2.2 現況。

下一個 bounded package 是 **C2 runtime measurement**：只在使用者明確允許安全維護窗口後，透過既有單一 owner 路徑收集 matched request/callback + timestamp-basis cross-check evidence，再由本次 materializer 產生第一筆 eligible DAILY terminal close。沒有授權就保持 offline，不 restart/login。


## 後續 C2 controlled-measurement path（同日追加）

後續 initial control-path commit `ed3e63360faca93f6a5a6b0af89fc1ecb51702bf` 把「未來如何在不建立第二個
broker owner 的前提下取得真實證據」做成正式 control path；correlation-hardening commit = `9496eb9afa65e647b5fceca86610247ff24e258e`；review corrections = `30d32754ff284a6b32370b236ed1fc40283304e9`、`0203e9becf0f0894c3d9f33cfdc2aece448db921`、latest source `873e6bd9697efe1bc2c67d1767c708b23af2df10`；current source/config build_id = `d0f179c3460497e7`。
`tick_detail_measurements.enabled` 預設仍為 `false`，因此發布程式本身不會
自動觸發 broker query。

新增控制包括：exact OSE/JNU contract、actual request/callback 15:45–17:00 JST window、
outstanding-request ambiguity block、同 process 同 contract 禁止二次 attempt、evidence path containment、
五秒 callback cap、startup-frozen `runtime_build_id` 與 disk fingerprint mismatch fail-closed、
raw/evidence 持久化與重載驗證。
timestamp-basis cross-check 也明確拒絕 UTC-like 與 Taipei-like raw clock 反例；review hardening 之後 evidence validation 會重新計算 cross-check，不再信 caller-supplied verified flags。另修正 optional Feature Store provenance query 遇 DuckDB/IO failure 時 fail closed，以及 legacy receipt-only packet freshness 不再標 FRESH。

驗證：review-round focused `74 passed, 1 deselected`；related regression `199 passed, 2 deselected`；final offline profile `1854 passed, 24 deselected, 132 warnings in 124.53s`，exit 0；targeted changed-file secret scan 0；diff check PASS。

現場 recorder 雖已有 W1/W2 `PER_FIELD_ONLY` provenance，但其啟動時間早於目前 C2 measurement/review commits through `873e6bd`，所以
**C2_CONTROL_PATH_RUNTIME_ADOPTION_PENDING**。本棒沒有 restart/login/logout，也沒有 queue
`request_yuanta_tick_detail_measurement.ps1`。真實 timestamp-basis evidence 仍為 `NONE_YET`。

## 第一次已授權 maintenance attempt（2026-09-25）

- Maintenance-control commit: `4cca09117ffda0fb2ead12de737ffcaf8b92ad9c`；request-script repair: `1452a45cf0c4de631d213eaa8648c3eae3b90211`。
- 15:56 JST 時 calendar 判定 2026-09-25 為有效 OSE derivatives session；FunctionList resolver 以 2026-09-25 as-of 唯一解析 active/nearest OSE micro quote contract = `JNU2612`（market 207, verified=true）。舊 recorder 配置同時訂閱兩個月份，所以 `JNU2703` 的舊 callback 不代表它是主合約。
- Maintenance 開始前舊 owner PID `6432/14952` 已不存在。最後 stale status heartbeat = `2026-09-25T06:46:17.888693Z`，status=`DEGRADED`，`pending_records=772`，`dropped_records=0`；因此可能有 buffered-data gap，不能宣稱零損失。
- Control/evidence 目錄沒有當日 tick-detail measurement request/result/raw/evidence，故尚未消耗唯一 measurement。
- 只做一次 current-build runtime-only owner start。launcher 顯示 `YUANTA_LIVE_STARTING pid=9060`，之後 PID/recorder child 均消失，沒有 fresh `status.json`，`recorder.out.log` / `recorder.err.log` 都是 0 bytes。依預先承諾的 fail-closed 規則，本次**沒有 retry broker login，也沒有送 GetStkTickDetail**。
- 後續只做 non-login diagnostics：build fingerprint、OrderApiExposureGuard、WinCred credential/password existence、FunctionList/default 42 subscriptions、JNU 2612/2703 + PM variants、SparkRuntime constructor、Start-Process + CLI argument mechanics 全部 PASS。這能排除多個 pre-login 問題，但舊 code 沒有 startup stage telemetry，所以不能誠實宣稱失敗發生在 instantiate/open/connect/login 的哪一個精確步驟。
- 因此狀態 = **FAIL_CLOSED_STARTUP_UNOBSERVED / RECORDER_NOT_RUNNING / RUNTIME_TIMESTAMP_VERIFIED=NONE_YET / ELIGIBLE_DAILY_CLOSE=NONE_YET / ACTUAL_FORWARD_EVIDENCE=NONE_YET**。

為避免下一次再發生「背景 process 被建立就誤報成功」，source commit `b9cfcb0e302e1520027d2c69adf363d15baf00c4`（build_id `ba7c0e1b9ca9d62c`）新增 startup stage telemetry 與 start-script fresh-status gate。可觀測 stage 包含 `PRE_BROKER_READY / INSTANTIATE / OPEN_PROD / WAIT_CONNECTED / LOGIN_REQUEST / WAIT_LOGIN / SUBSCRIBE / RUNNING`；失敗只落地安全的 error type、login msg code、build/gate/status，不保存 credential。Start script 只有看到 fresh RUNNING/DEGRADED、build matching，且 maintenance gate 符合要求時才回報成功。

該修補驗證：focused `42 passed, 2 deselected`；broader regression `151 passed, 2 deselected`；final offline profile `1858 passed, 24 deselected, 132 warnings in 125.40s`，exit 0；targeted secret scan 0；`git diff --check` PASS。
