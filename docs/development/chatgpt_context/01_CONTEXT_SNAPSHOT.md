# MARKET_AI_HUB 跨對話上下文快照

快照日期：2026-09-26（Asia/Taipei）。用途：上傳 ChatGPT 專案資料來源。此檔是查核資料，不是新的執行授權。後續應替換此快照，避免多份「最新」並存。

## 1. 先讀這段

### 2026-09-26 最新 research decision-support 修正

新的 source/config build=`e8dc080886d0b5a2`。這一棒修正的是「主腦有資料卻只會拒答」的語義缺口，不是放寬校準/edge gate。formal validated direction、public probability、trading edge 仍照原 gate；另外新增獨立的 `research_decision_support`，允許主腦輸出 research stance（偏多/偏空/中性/混合）與 conditional research action。

大阪 public analysis 只在 ^N225 PROXY scope 內合成 stance，不拿 stale Micro settlement 與 proxy forecast 硬算報酬。實際 smoke：`direction_status=NO_VALIDATED_MODEL_CONSENSUS`、`direction_value=null`，但 research stance=`SLIGHT_BULLISH_LEAN`、strength=`WEAK_UNVALIDATED`、evidence_scope=`PROXY_ONLY`；目前行動是等待 fresh Direct confirmation，同向則優先偏多研究情境，反向則撤銷/重算。raw classifier 數值不再直接暴露，仍不能稱機率。

CherryStudio prompt 已要求：使用者問預測/看多看空/怎麼操作時，先讀 get_analysis_packet 的正式 gate，接著必須呼叫 analyze_osaka_nikkei 或 analyze_taiwan_stock 取得 `research_decision_support`；不得只因 WAIT/UNPROVEN 就整段拒答。系統仍禁止代替使用者下單、個人化口數、人工編造精確進場/停損/停利價。

驗證：focused=`37 passed`；actual Osaka public smoke PASS；build-freeze=`3 passed`；full offline=`1966 passed, 1 skipped, 35 deselected, 110 warnings in 210.45s`，exit 0。此 package 尚待 GitHub publication 與 merged-build live-owner verification。

### 2026-09-26 最新 W3.2-EP1 / MCP / analysis closeout

目前 source/config build=`72c6f533e5ae2341`。W3.2-EP1 raw EVENT_PROBABILITY producer 已完成：每個未來合格 C2.3 exact-contract DAILY close 會同時 precommit 原 POINT baseline 與 `TERMINAL_CLOSE_GT_SOURCE_CLOSE_1D` raw event probability。event threshold 在 forecast origin 凍結到 2H.4 immutable artifact；raw probability 使用 Beta(1,1)，只計入 forecast-origin 前已 available 且屬同一 exact contract code/month 的 settled outcomes，換月不混 prior。第一筆無歷史時是 UNCALIBRATED prior=0.5，永遠不能直接當公開已校準機率。

C2.3 task 已經會呼叫同一 W3.2 operator，所以交易日無需再加另一排程。`get_forward_test_status` 新增 `w32_event_probability_registered/settled/pending`；W4 tracked protocol 的 50 CALIBRATION + 50 VALIDATION + 50 FINAL_OOS 是最低 sequential sample 數，不代表滿 150 筆就自動 CALIBRATED。2026-09-26 非 OSE session，因此真實 raw event samples 仍是 NONE_YET。

實機 closeout：Feature Store 已 non-destructive migration 到 schema 2，保留 547 legacy feature rows；Osaka direct input 從錯誤 `SCHEMA_NOT_READY` 修成正確 `NO_ELIGIBLE_ROWS`。FinMind HTTP logging 已抑制 token-bearing URL，既有 local mcp.log 22 處已遮罩且 credential 未改。CherryStudio 現有 `market-ai` stdio MCP entry 不需改 command，實測 21 tools / 24 calls / 0 errors。最終 exact-contract producer regression=`6 passed`；W3/W4/MCP cross=`158 passed`；CI-equivalent=`1965 passed, 1 skipped, 35 deselected, 110 warnings`，exit 0。

搬移到新 Windows 目前不是阻塞條件；未驗證的 full install / WinCred / certificate / COM cells 已記錄在 `FUTURE_RELOCATION_VALIDATION_MEMO.md`，日後搬機再驗。

### 2026-09-26 最新 W4.1 / W5.1 / runtime 結果

W4.1 implementation=`5ec760a`，PR #61 CI=`36240929664` PASS，merged main=`54542a1443eee9a8a73a130b602abeba0fca941b`。W4 fitting 只接受 W3.1 governed、`FORWARD_PRECOMMITTED`、scope/model/event/distribution 同質的 `EVENT_PROBABILITY`。VALIDATION 只能產生 frozen `EVALUATED_UNCALIBRATED` candidate；獨立 `FINAL_OOS` 必須一次性消耗且不得重 fit，通過後才允許 `CALIBRATED` typed evidence。local CI-equivalent=`1942 passed, 7 skipped, 35 deselected`；post-merge smoke=`61 passed`。

W5.1 implementation=`906a164`，PR #62 CI=`36241924593` PASS，merged main=`37abd2574e59443d6079e24ebc0a639d3713c51e`。新增 daily first-passage label：`UPPER_FIRST / LOWER_FIRST / NEITHER / AMBIGUOUS_WITHIN_DAILY_BAR`；同一 daily bar 雙觸及、gap、missing/provenance 不足一律不猜。`FIRST_PASSAGE` 已是獨立 audit outcome kind / label scope / calibration family，不再借用 TOUCH。cross-regression=`187 passed`；local CI-equivalent=`1950 passed, 7 skipped, 35 deselected`；post-merge smoke=`187 passed`。

在 W5 merge checkpoint，`D:\MARKET_AI_HUB` main/product build=`d92e85fec3660b93` 且 persistent safe-default owner 已驗證唯一/heartbeat fresh/runtime=disk/measurement gates=false。此歷史 runtime 已被後續 source build `72c6f533e5ae2341` 超越，需在 merge 後做一次受控 owner handover。C2.3 task 仍 Enabled、每 5 分鐘；2026-09-26 非 OSE session，故仍未產生新 C2.3 DAILY evidence。

重要真值：ENGINE PASS != DATA READY != CALIBRATED。W3.2-EP1 raw event producer 現已存在，但截至 2026-09-26 尚無真實 settled event sample；`ACTUAL_FORWARD_EVIDENCE=NONE_YET`、`ACTUAL_EVENT_PROBABILITY_EVIDENCE=NONE_YET`、market `CALIBRATED=FALSE`，沒有 trading-edge claim。

### 2026-09-26 最新 C2.3 自動化 / W3.2 operational cycle 結果

Implementation commit=`b0a26f3`；PR #60 已通過 CI 並 merge。C2.3 task 已註冊且持續 Enabled；persistent safe-default owner 已完成 runtime adoption，後續並受控 handover 到 W5 build `d92e85fec3660b93`。舊 raw `w33_tick_cbce3cba39291cd1f14e.json` 仍不是可追溯升級的 typed verification evidence。

本棒新增 fail-closed close-window orchestrator、5 分鐘 timezone-aware task registration、JNU watchdog maintenance yield、以及 broker-free W3.2 exact-JNU settle/precommit operator。只有 OSE session date 且 15:45–17:00 JST 才能進 maintenance；exact JNU 由既有 FunctionList resolver 決定；每交易日最多三次自動嘗試；成功必須先取得 persisted C2.3 typed evidence，才 materialize DAILY close，再 settle 舊 forward prediction / precommit 下一筆。stdout/state 都不公開價格。

驗證：focused=`96 passed, 1 deselected`；broader=`198 passed, 2 deselected`；CI-equivalent full=`1939 passed, 1 skipped, 34 deselected, 110 warnings in 113.70s`，exit 0；compile、PowerShell dry-run/non-session、diff check、secret scan 全 PASS。今天非 OSE session，所以沒有送 measurement；ACTUAL_FORWARD_EVIDENCE 仍 NONE_YET。task 與 persistent safe-default owner 均已完成 runtime adoption。

### 2026-09-26 最新 W3.2 persisted-artifact 結果

Implementation commit=`4decd79`，final feature head=`262729b`，PR #58 CI=`36234063403` PASS，merged main=`da73dd288971520e2c765f6660b7d329b89ac79e`；post-merge tree 一致、operator smoke=`6 passed`；source/config build=`35669ded63f487ed`。W3.2 既有 verified-tick materializer 已具備 OSE near-close timestamp cross-check、C2.3 typed evidence binding、JNU contract/month、PIT `available_at`、source snapshot、`CONTRACT` series 與 `DAILY` frequency gate；本棒新增 persisted raw/evidence pair 的 operator API 與 offline CLI。CLI 不接受人工 close 值，只能從 canonical artifact pair 重建；路徑限制在 recorder root，tamper/expected-contract mismatch/path escape fail closed，stdout 不輸出 close。

驗證：focused=`50 passed`；related=`103 passed`；full isolated offline=`1924 passed, 7 skipped, 35 deselected, 110 warnings in 81.50s`，exit 0；最後 CLI/operator focused=`6 passed`；diff check PASS；secret scan=0。沒有 broker action。

先前 WebCodex 無法讀 private runtime artifact；本輪已依使用者指示改用 RDC 唯讀查核並確認：只有 historical raw、沒有可 retroactively promotion 的 typed verification evidence。今天不是 OSE session date，故仍不能合法產生新的 C2.3 typed evidence。`ACTUAL_FORWARD_EVIDENCE=NONE_YET / W4_ENGINE_READY / REAL_CALIBRATION_FIT_NOT_STARTED`，continuous bars/TICK 仍不得冒充 DAILY。


本專案已超過第一階段。公開 main 已有 Phase 2、多輪安全與資料語義修正、Price/Probability Map 基礎，以及 V2-A 至 V2-I 2I.1。不要把「第二階段施工」解讀成 V2-I 尚未存在，也不要重做它們。

實際施工 repo 是 `D:\MARKET_AI_HUB`；本次 Codex 的 `C:\Users\fishk\Documents\ChatGPT\MARKET_AI_HUB` 原先只是空 Git 倉庫，現在只存本交接包，不能混為同一 repo。

GitHub：https://github.com/fishke22/market-ai-hub

### 2026-09-26 最新 W1 接手結果

#### reconnect-only stacked checkpoint

Reconnect implementation `feeefe3` + JNU base `23504cf` were reconciled at `4978f59`; PR #55 merged to main as `a9ab3e55185860c1cc80923d8e9970f37e385d1c`. Merged build=`1037d45ff8e65884`; final docs-only CI `36231436018` PASS; post-merge reconnect+JNU smoke=`29 passed, 21 deselected`.

Merged recorder keeps JNU microstructure capture and bounded reconnect together. Reconnect remains full-runtime replacement only: durable pending flush -> local retire -> fresh Open -> official Connect -> fresh WinCred password -> Login OnResponse -> complete quote re-subscribe, then JNU microstructure subscriptions are restored. No hidden `Reconnect()` API is assumed. Tracked `auto_reconnect.enabled=false`.

Merged validation: focused reconnect+JNU=`29 passed, 21 deselected`; related=`150 passed, 2 deselected`; full offline=`1918 passed, 7 skipped, 35 deselected, 110 warnings in 84.89s`, exit 0. Read-only main-worktree preflight observed `NO_RUNNING_OWNER`/`STOPPED` with no broker action; that is not start authorization.


實際 repo=`D:\MARKET_AI_HUB`；remote main 已前進到 merge commit=`a9ab3e55185860c1cc80923d8e9970f37e385d1c`，tree 與 validated head `98ec76c` 完全一致；merged build=`1037d45ff8e65884`。

最新核心修正：durable spool/WAL、connection fail-closed、venue-local contract revalidation、JNU microstructure capture 與 bounded reconnect 已在 merged offline profile 共存。auto reconnect 實作存在但 tracked default=false；live restart/re-login 尚未 adoption。

前置保護仍有效：official Connect gate、2/3/4/5 fault semantics、300 秒 venue-local contract revalidation、durable spool/WAL 與 quote-only/order guard。JNU capture 與 reconnect 合併後 regression 已通過。

API signature 查核：bundled vendor `YSendOrder.py` 的 WatchlistAll sample 省略第三參數；本機 `2.2026.0918.0` DLL reflection 顯示第三個 `Lng` 是 optional、default=`NORMAL`，因此 recorder 保留既有 explicit `enumLangType.UTF8`。subscribe/unsubscribe 共用 0.2 秒 throttle。這個查核只載入本機 assembly，沒有 instantiate/login/broker call。

最新 merged 驗證：focused=`29 passed, 21 deselected`；related=`150 passed, 2 deselected`；full offline=`1918 passed, 7 skipped, 35 deselected, 110 warnings in 84.89s`，exit 0；merged fingerprint=`1037d45ff8e65884`。

目前 live adoption **仍未成立**。最新 read-only preflight=`NO_RUNNING_OWNER`、status=`STOPPED`、matching owner=0、broker_action_performed=false；這不是啟動授權。tracked auto reconnect=false，若要 live enable/restart 必須另有明確授權。

可信度邊界不變：`ENGINE PASS != DATA READY != CALIBRATED != PREDICTIVE EVIDENCE != TRADING EDGE`；actual C2.3 typed runtime verification、eligible real DAILY close、W3.2 actual forward evidence仍未成立。

2026-09-25 C2 W3.3 controlled-measurement path 最新交接：

controlled-path initial commit = `ed3e63360faca93f6a5a6b0af89fc1ecb51702bf`；correlation-hardening commit = `9496eb9afa65e647b5fceca86610247ff24e258e`；review fixes = `30d32754ff284a6b32370b236ed1fc40283304e9`、`0203e9becf0f0894c3d9f33cfdc2aece448db921`、`873e6bd9697efe1bc2c67d1767c708b23af2df10`；maintenance-control = `4cca09117ffda0fb2ead12de737ffcaf8b92ad9c`；request-script repair = `1452a45cf0c4de631d213eaa8648c3eae3b90211`；startup-observability source = `b9cfcb0e302e1520027d2c69adf363d15baf00c4`；C2.3-era source/config build_id at that checkpoint = `afd52f88a351541a`。
新增的 `tick_detail_measurement` 只會在既有 single-owner recorder 內執行，
而且 `tick_detail_measurements.enabled=false` 預設關閉。它只允許 OSE 207 + exact JNU contract
+ LastCount<=20，actual request/callback 都必須在 15:45–17:00 JST，遇到 outstanding ambiguity、
unsafe evidence path 或 running-process build 與 disk build 不一致，都會在 broker query 前 fail closed。

runtime evidence schema 現為 `W3.3-C2.3`，綁定 recorder 啟動時凍結的 `runtime_build_id`。
timestamp-basis cross-check 對 UTC-like / Taipei-like raw clock 都有反例拒絕，而且 evidence validation 會從 raw batch + request/callback times 重新計算，不接受 caller 自行宣稱成功。Feature Store optional provenance query 遇 DuckDB/IO 錯誤回空集合；`LEGACY_TOP_LEVEL_RECEIPT_ONLY` 不會再被 packet 標成 FRESH。raw tick 值只留本機 evidence raw artifact；control result / verification evidence 不公開價格。

maintenance-control 另外新增 runtime-only enable 與 graceful shutdown；tracked config 仍維持 `enabled:false`。startup-observability 再補 `startup_stage`、安全的 error type/login code 與 start script fresh-status confirmation。驗證：focused `42 passed, 2 deselected`；broader regression `151 passed, 2 deselected`；final offline profile `1858 passed, 24 deselected, 132 warnings in 125.40s`，exit 0；targeted secret scan 0；diff check PASS。沒有新增 dependency 或 license surface。

第一次已授權 maintenance 在有效 OSE session 的 15:56 JST 進行。當時舊 recorder PID `6432/14952` 已經消失；最後 stale status 為 `DEGRADED`、heartbeat `2026-09-25T06:46:17.888693Z`、`pending_records=772`，所以可能存在 buffered-data gap。FunctionList resolver 唯一選出目前最近有效 OSE micro contract = `JNU2612`；舊 runtime 同時訂閱的 `JNU2703` 只是下一月份，不拿來冒充 active contract。

第一次 current-build runtime-only owner start 的 launcher PID `9060` 隨即消失，沒有 fresh status/log，recorder stdout/stderr 為空；該次沒有 queue measurement。第二次由新的使用者 continuation 觸發，在約 16:32 JST 再做一次 start：startup telemetry 證明 SPARK login `0001`、`startup_stage=RUNNING`、runtime build=`ba7c0e1b9ca9d62c`、measurement gate=true、subscriptions=42、pending/dropped=0。可是 one-shot WebCodex launcher 結束後 recorder PID `33448` 也隨即消失，最後 heartbeat 停在 `2026-09-25T07:32:13.645637Z`，且沒有 callback / W1-W2 provenance / clean STOPPED / stderr/stdout / crash dump。量測前 gate 因此失敗，**沒有送 GetStkTickDetail，也沒有在同一 execution 做第二次 login retry**。目前狀態 = **SECOND_ATTEMPT_FAIL_CLOSED_AFTER_LOGIN / RUNNER_CHILD_LIFETIME_BLOCKER / RECORDER NOT RUNNING**。真實 OSE timestamp-basis evidence、eligible DAILY terminal close、W3.2 actual forward evidence均仍為 NONE_YET。

第三次 maintenance 已證明 foreground Runner Job 路徑可用：recorder RUNNING/login `0001`、fresh W1/W2 provenance、exact JNU2612，並只送出一筆 measurement。C2.2 取得 canonical raw snapshot `w33_tick_cbce3cba39291cd1f14e`，但因 raw terminal timestamp=`15:45:01` 被 `RAW_TRADE_AFTER_DAY_CLOSE` fail closed。raw typed reload PASS，未產生 verification artifact。C2.3 只新增 **1 秒** closing-auction grace；`15:45:02+` 仍拒絕，session event timestamp 仍為 15:45。C2.3 build=`afd52f88a351541a`；focused 59、broader 154/2 deselected、full offline 1861/24 deselected/132 warnings in 133.26s，全部 exit 0。舊 C2.2 failed result不事後補造 evidence，因此 runtime timestamp verification 仍 NONE_YET。
C2.3 source commit=`3e05af13762d430f875a35f2b288cf33188ce733`，GitHub source CI #162=SUCCESS；第一版 C2.3 handoff publication commit=`3f4dda90485cf1a86bc16114e2edec40e837eff8`。
後續 test-only hardening commit `0d2693f` 補上真正的 C2.3 正向端到端 regression：模擬 `15:45:01` closing-auction print，要求 measurement 落 raw/evidence、typed reload 通過，再 materialize exact-contract DAILY close，provider trade time 保持 15:45:01、session event 固定 15:45:00。focused measurement/materializer `38 passed`；broader `155 passed, 2 deselected`；full offline `1862 passed, 24 deselected, 132 warnings in 135.52s`，exit 0；product build 仍是 `afd52f88a351541a`。
bridge regression commit `3ce826817834b20d26d671cd24a0aec8c1821e4a` 再把既有模組真正串起來：C2.3 DAILY materializer → canonical Feature Store → W3.2 candidate/precommit，並驗證 callback `available_at` 之前不可見；下一交易日再以 C2.3 DAILY close 做 exact-contract settlement，最後進 W3.1 evaluation。focused=`45 passed`；broader=`158 passed, 2 deselected`；full offline=`1865 passed, 24 deselected, 132 warnings in 144.28s`，exit 0。這是 synthetic/offline engineering evidence；`CALIBRATED=false`、`PREDICTIVE_EVIDENCE=NOT_ESTABLISHED`、`TRADING_EDGE=NOT_ESTABLISHED`，且 product build 仍為 `afd52f88a351541a`。
17:30 Asia/Taipei read-only inspection 又確認 current-build safe-default recorder 已在運行：venv Python parent PID `25480` → actual interpreter/status PID `26476`，status=`RUNNING`、login=`0001`、subscriptions=42、quote fresh、health_reasons=[]、dropped=0、persistence_error=null、runtime build=`afd52f88a351541a`、`tick_detail_measurements_runtime_enabled=false`。這是同一啟動鏈，不可因看到兩個 Python PID 就再開第二 broker owner；本次檢查沒有執行 broker action。
owner-preflight commit `bef25d54ebea22bcb93d8466f657fe7d460496e9` 新增 `scripts/check_yuanta_recorder_owner.ps1`。它以 status PID 為 owner truth，合併同一 parent/child invocation，獨立第二 chain 才標 duplicate risk，並核對 heartbeat、runtime/disk build、runtime/tracked measurement gate。現場輸出=`SAFE_DEFAULT_OWNER_HEALTHY`；PowerShell parse PASS；focused=`26 passed, 2 deselected`；broader=`159 passed, 2 deselected`；full offline=`1866 passed, 24 deselected, 132 warnings in 137.11s`，exit 0。scripts/tests 不改 runtime build，仍為 `afd52f88a351541a`。
lifecycle-gating commit `639de5f3fe3fda1bcb0c4b31055c3bdf2ab4e930` 再讓 start/stop 在 mutation 前先吃 preflight。現場對健康 owner 執行 start 只回 `YUANTA_LIVE_ALREADY_RUNNING`，owner chain 前後皆 `25480,26476`，沒有第二 login。stop 在 `NO_RUNNING_OWNER` 時會在寫 shutdown request 前直接 `YUANTA_LIVE_NOT_RUNNING`；duplicate/unverified owner 則 fail closed，避免 stale shutdown JSON 被未來 recorder 誤吃。focused=`27 passed, 2 deselected`；broader=`160 passed, 2 deselected`；full offline=`1867 passed, 24 deselected, 132 warnings in 141.86s`，exit 0；build 仍為 `afd52f88a351541a`。
request-gating commit `ef59565ebb502957f8d1b9c8e77f39a7ddeaa3af` 再封住 quote/tick-detail 兩個 mutation 入口：quote request 只接受健康 verified RUNNING owner；tick-detail 更要求 `MAINTENANCE_OWNER_RUNNING`、runtime measurement gate=true、tracked gate=false、runtime/disk build一致、health 無異常，且所有檢查都發生在 inbox resolve/create 之前。PowerShell parse PASS；static contract=`15 passed, 1 deselected`；broader=`158 passed, 2 deselected`；full offline=`1868 passed, 24 deselected, 132 warnings in 126.74s`，exit 0。驗證期間沒有執行 broker request；scripts/tests 不改 build，仍為 `afd52f88a351541a`。
2026-09-25 19:25 Asia/Taipei read-only continuation 再次得到 `SAFE_DEFAULT_OWNER_HEALTHY`：只有一條 parent/child invocation chain、heartbeat fresh、runtime/disk build 都是 `afd52f88a351541a`、runtime/tracked measurement gate 都是 false、health 無異常。PR #55 在 request-gating head 的 CI 為 SUCCESS。`v2-tick-detail-source-contract.md` 先前仍寫「尚未採用 C2／measurement 未執行」的過期 live-state bullets，已依真實 C2.3 raw evidence 與目前 safe-default owner 狀態修正；沒有執行 broker mutation。
同一 continuation 在無法進行 OSE live gate 的時段推進 W7.1：從 `%TEMP%` 真實執行 `reconstruct_verify.ps1` 先重現 caller-cwd 相對路徑 FAIL；補 repo-root `Set-Location` 後又重現舊驗收把合法 `build_id: runtime_introspected` 誤判 FAIL。現在 verifier 先驗 manifest sentinel，再獨立驗 runtime `build_fingerprint()` 16-hex identity，且從 `%TEMP%` 已 `RESULT: PASS`。這只證明目前機器的 arbitrary-cwd 重建驗收，不代表新 venv、新 Windows、COM/WinCred 或券商移機已驗收。
W7.2 再清掉元大維護腳本的 machine-specific path：COM check 不再寫死 `D:\MARKET_AI_HUB\src`；x86 sidecar setup 不再搜尋特定 Windows 使用者路徑，改由 `py -3.11-32` 或 `MARKET_AI_PYTHON_X86` / `-PythonX86` 指定，且先驗 32-bit、venv/pip 每一步 fail closed；SDK forensics 改用目前使用者 Documents/Downloads 或 `MARKET_AI_YUANTA_SDK_ROOTS`。唯讀 COM smoke 仍 `READY_FOR_AUTH`；從 `%TEMP%` 使用含中文與空白的外部 `MARKET_AI_DATA_ROOT` 可正確解析 `live\yuanta`。targeted=`15 passed, 1 deselected`；full offline=`1871 passed, 24 deselected, 132 warnings in 132.68s`，exit 0；product build 仍 `afd52f88a351541a`。implementation commit=`86cea574927988e78793dd307af2e3351f73e59c`；PR #55 OPEN/MERGEABLE；CI `36133883630` SUCCESS。這仍不是新 venv / 新 Windows / WinCred / 憑證移機驗收。
W7.3 主環境 relocation bootstrap 再發現 PATH `python` 是 Python 3.11 32-bit，但 `platform.machine()` 仍回 `AMD64`，舊 installer 因此可能錯建主 venv。現在 `setup_windows.ps1` 只接受實測 pointer width=64 的 CPython 3.11/3.12，優先 launcher 的 3.12/3.11，支援 `-PythonExe`，且不會自動安裝 Python；新增 `-BootstrapOnly` 可在完全不跑 pip/網路下載下建立/驗證新 venv。`verify_source_relocation_bootstrap.ps1` 可重現把 706 個 tracked files 搬到含中文/空白的新 temp checkout、從非 repo cwd 建 3.12.13 x64 venv，驗證 `source_root` 指新 checkout、build=`afd52f88a351541a`、`old_repo_in_syspath=false`，結果=`SOURCE_RELOCATION_BOOTSTRAP_PASS`。targeted=`4 passed, 14 deselected`；full offline=`1873 passed, 24 deselected, 132 warnings in 147.68s`，exit 0。這是目前 Windows 的 source relocation + fresh bootstrap venv 證據，不是完整 dependency install / 新 Windows / WinCred / certificate / COM restore。
W7.4 basic offline backup/restore 真實 drill 再抓出三個缺陷：robocopy/pip exit code 未驗、PowerShell 5.1 `Get-FileHash` 深層長路徑失敗、以及 `/XD data models reports` 會誤排 `src/market_ai_hub/data`、`src/market_ai_hub/models`、`config/data`，造成 checksum 看似完整但 restored build 變成 `bbef69fe330230ab`。現在 exclusion 只排 repo-root 絕對路徑，SHA256/cleanup 支援長路徑，native failure fail closed；新增 `verify_offline_backup.ps1` 與 `verify_offline_backup_restore_drill.ps1`。最終 drill 驗證 2191 files，restored import 確實來自新路徑且 build=`afd52f88a351541a`；targeted=`2 passed`；full offline=`1875 passed, 24 deselected, 132 warnings in 139.90s`，exit 0。此 tier 未下載 wheels/models，也未備份 private market data；DuckDB/Parquet/WAL 一致性 restore 仍待獨立驗收。
W7.5 Scheduled Task relocation：`register_forward_shadow_task.ps1` 原本遇到既存 task 會保留舊 checkout 路徑；目前 research/forward registration 都支援 non-mutating `-DryRun`，forward 預設用目前 repo path refresh existing task，只有明確 `-PreserveExisting` 才保留。以中文+空白的 temp checkout、non-repo cwd 驗證 dry-run JSON，task execute/arguments/working_directory 只含新路徑，沒有修改 Windows Task Scheduler。targeted reconstruction=`17 passed`；full offline=`1880 passed, 24 deselected, 132 warnings in 141.67s`，exit 0；總數另包含 concurrent 的 3 個未追蹤 research-snapshot tests，該 workstream 不屬本包。commit=`95c34cedf21ba1dfa4e7a48b23ee8da53ad6677b`；CI `36142106665` SUCCESS；build 仍 `afd52f88a351541a`。
W7.6 MCP client-config relocation：新增 `scripts/render_mcp_config.py`，不再要求人工替換 template `<PROJECT>`。renderer 由目前或 `--project-root` 計算 `.venv` MCP executable，預設只 stdout；只有明確 `--output` 才寫檔，`--require-command` 會在 command 不存在時 fail closed。generic/cherry 都以中文+空白 relocated root、non-repo cwd 驗證沒有舊 checkout 洩漏；目前 repo 真實 render 亦 PASS。沒有修改任何外部 MCP client 設定。targeted reconstruction=`18 passed`；full offline=`1881 passed, 24 deselected, 132 warnings in 132.50s`，exit 0；commit=`db9eeed6b9aaba540fcb2acef19de3ea2cd8e86c`；CI `36143262904` SUCCESS；build 仍 `afd52f88a351541a`。
W7.7 新增 machine-readable `docs/development/W7_PORTABILITY_ACCEPTANCE.yaml`：只把 W7.1–W7.6 已實證格列 PASS；完整 dependency install、新 Windows、WinCred、certificate、COM registration 明確保持 `UNVERIFIED_EXTERNAL_GATE`，private research-data restore 在 W7.7 發布時仍是 separate workstream，C2.3 runtime verification 仍等 live window；W7.8 已只針對目前機器關閉 private research-data consistency cell。矩陣一度放在 `config/` 導致 runtime build 變 `c555afda8269c1cc` 並使 3 個 build-freeze regression 失敗，因此已移出 runtime fingerprint surface；修後 build 回 `afd52f88a351541a`。targeted matrix/build=`22 passed`；full offline=`1882 passed, 24 deselected, 132 warnings in 172.30s`，exit 0。
W7.8 private research-data consistency：接手昨晚中止但已通過初步 smoke 的 snapshot workstream，補齊 restore 到全新 data root、禁止 overwrite/路徑重疊、exact inventory/SHA256/row-count/`prediction_id` digest 驗證與 symlink fail-closed；`live/**`、`backups/**` 明確排除。真實 current-machine temp drill：8 DuckDB + 1 SQLite + 5 Parquet 建立/verify/restore PASS，1686 個 live files 排除，restore 14 files 且沒有 `live/`，temp cleanup PASS。targeted=`4 passed, 1 skipped`（Windows 無 symlink 建立權限）；full offline=`1884 passed, 1 skipped, 24 deselected, 132 warnings in 133.70s`，exit 0。只關閉目前機器 `private_research_data_consistent_restore`；不是 live recorder backup，也不是 clean-new-Windows certification；commit=`f3faf193b34bae714c547dddba525a93edd467fb`；CI `36209628743` SUCCESS；build 仍 `afd52f88a351541a`。
W8.1 dependency lock security：GitHub default branch 的兩個 open Dependabot alerts 都來自 `requirements-lock-windows-x64.txt` 的 `setuptools==78.1.0`。high `GHSA-5rjg-fvgr-3xxf` 需 >=78.1.1；medium `GHSA-h35f-9h28-mq5c` 需 >=83.0.0，因此 lock 直接提升安全 floor 到 `83.0.0`，並在檔內記錄兩個 advisory。未執行實際 dependency install；fresh-install 仍是外部 gate。targeted=`20 passed`；full offline=`1883 passed, 24 deselected, 132 warnings in 170.00s`，exit 0；build 仍 `afd52f88a351541a`。commit=`c2d76febca2c994b3678391a5b484d15b1d77319`；CI `36208910703` SUCCESS。在 PR #55 未 merge 前只能稱 `PATCH_IN_PR / REMOTE_ALERT_PENDING_MERGE`，不能稱 GitHub alert 已解除。
W8.2 CI runtime maintenance：GitHub release API 核對 checkout latest=`v7.0.1`、setup-python latest=`v7.0.0`，兩者 action runtime 都是 Node 24。CI 已改 `actions/checkout@v7`、`actions/setup-python@v7` 並把 `ubuntu-latest` 固定成 `ubuntu-24.04`，避免已觀察到的 Node-20 forced-runtime annotation 與 2026-10-19 Ubuntu 26 自動漂移。targeted=`21 passed`；full offline=`1885 passed, 1 skipped, 24 deselected, 132 warnings in 166.54s`，exit 0；commit=`ac40f88b377b09eca0d296e0232abc88f4bd13c2`；CI `36210103584` SUCCESS；PR #55 OPEN/MERGEABLE；build 仍 `afd52f88a351541a`。
W8.3 external relocation preflight：新增只讀 `scripts/check_external_relocation_gates.ps1 -Json`，不安裝 dependency、不寫 WinCred、不匯入/匯出憑證、不註冊 COM、不登入 broker；它只回報本機 WinCred profile 是否 configured、generic Windows certificate-store 狀態與 read-only COM smoke。所有新機/外部 gate 仍維持 `UNVERIFIED_EXTERNAL_GATE`。同時修正 `check_yuanta_certificate.ps1`：任意未過期個人憑證不得再被描述成元大憑證已驗證，官方身份/簽驗仍須元大憑證中心證據。WebCodex Runner 另重現 W7.5/W7.6 中文搬移路徑被 code page 損壞，已讓 MCP renderer 與兩支 Scheduled Task dry-run 強制 UTF-8 輸出。targeted=`23 passed`；full offline=`1887 passed, 1 skipped, 24 deselected, 132 warnings in 148.29s`，exit 0；build 仍 `afd52f88a351541a`。

2026-09-25 C2 W3.3 runtime-evidence / terminal-close offline correctness 歷史交接：

C2 implementation commit = `92e178e4ea6cad632d071747efe1c273bcc79efc`；source build_id = `b6cfc2ceae89d221`。Raw tick-detail snapshot 永遠保持 UNVERIFIED，verification 狀態不再參與 raw canonical identity；SPARK runtime 分開保留實際 request time 與 callback receive time，並只在 request/callback 唯一可關聯時產生 correlation。terminal-close materializer 不再信任一個 status 字串，必須吃綁定 request/callback/market/code/canonical snapshot/timestamp-basis cross-check 的 typed runtime evidence。

受控時間窗以 request time 驗證 15:45 <= JST < 17:00，callback 也必須在同一 controlled window；15:44:59 request / 15:45:01 callback 會拒絕。Feature Store 新增獨立 DERIVED_DAILY gate，只有 exact contract/month、CONTRACT、roll NONE、PIT-safe、source IDs、DAILY frequency 與 session-close timestamp 一致的資料可 materialize；TICK 仍不能冒充 DAILY。

驗證：C2/W3.3 focused `35 passed`；related W2/W3/C1 `134 passed`；final offline profile `1834 passed, 24 deselected, 132 warnings in 140.87s`，exit 0（只排除現場 recorder owner 造成的 global mutex test）。changed-file secret scan 0；diff check PASS。三個 stale build-id freeze assertions 只更新為新 fingerprint，沒有刪除測試。

**C2_OFFLINE_CORRECTNESS_PASS != RUNTIME_TIMESTAMP_VERIFIED != DATA READY != ACTUAL_FORWARD_EVIDENCE != CALIBRATED != TRADING EDGE。** 這一段是歷史 C2 offline checkpoint：當時沒有 broker login/logout/restart/subscription/order/account 操作，且 live measurement 尚待授權；其後授權已於 2026-09-25 給出，第一次 live attempt 則如上方最新段落所記錄，在 measurement 前 fail closed。actual runtime timestamp verification = NONE_YET；eligible real DAILY terminal close = NONE_YET；W3.2 actual forward evidence = NONE_YET。

C1 歷史交接仍有效如下：
W1/W2/W3.1/W3.2/W3.3 已存在的工程不重做。C1 程式/測試 commit 為 `50f209a095a151b6ae42c6db5d0d462d11fd2395`；工作分支 `codex/quote-hub-correctness`；runtime build_id = `c64b98bd4a09d576`。C1 把每個 forecast origin 分成 VALID / FAILED / ABSTAINED / NONFINITE / INVALID_TARGET，pairwise 只用共同有效 origins 且同時揭露雙方 full coverage；store C1.1 fail-closed 拒絕非有限值與缺失/矛盾 accounting，舊 leaderboard 依 schema 隔離、不重寫歷史。

另外修正 random-walk horizon、缺 train labels 時 classification baseline 偷看 test labels、rates regime 對齊與 20-session lookback；CLI run 會持久化 pairwise，compare 不再拿不同成功子集直接比 MAE。舊 tournament 排名必須重跑，不能挪用舊績效。

驗證：初始 C1 regression `11 passed, 4 failed`；最終 focused `198 passed, 6 deselected`，exit 0。未排除 Windows global quote-owner mutex 的完整離線跑法為 `1802 passed, 34 deselected, 1 failed`，唯一失敗是現場 owner 已存在；沒有停止 recorder 換綠燈。最終 offline profile 明確排除該單一 mutex 測試：`1804 passed, 35 deselected, 110 warnings`，129.47s，exit 0。changed-file secret scan 0；diff check PASS。

**這仍不是 DATA READY、CALIBRATED、PREDICTIVE EVIDENCE 或 TRADING EDGE。** 本包未做 calibration fitting、未建立真實 forward prediction/outcome、未重跑真實市場排行榜，也沒有新增模型。

**這一段是歷史 C1/C2 offline 記錄。** 當時 recorder 仍由既有 owner 持有，C1 與 C2 offline 包沒有 broker login/訂閱/登出/重啟/下單/帳務操作；目前 live truth 以本檔最上方最新 observation 為準，不要沿用這段歷史 recorder 狀態。

## 2. 查核深度與限制

完成當時 650 文字檔結構/hash/UTF-8/AST 盤點，重點審閱架構、V2-H/I、PPM、公用 packet/gate、路徑、安裝/CI、完整 recorder。未宣稱全部逐行審計，未讀全部私有資料/權重。
最初88 tests與三個反例屬修補前證據；後續正式 regression 是修補後證據。完整 hash inventory 保留在本機 AUDIT_EVIDENCE.json，不要每棒讀全部。執行能力：本輪先用 Remote，依使用者最新偏好改為 Codex 原生工具；未修改 OpenCode 設定。

## 3. 系統用途與資料流

```text
官方/免費日線與總經、既有元大行情
  → provider / quote recorder
  → 原始來源與 immutable snapshot、as-of/session/contract 語義
  → feature store / factor routing / label engine
  → baseline、價格模型、方向分類器、研究 challenger
  → direct / joint / scenario / dynamic ensemble（分開保存）
  → prediction + forecast artifact + factor lineage
  → 到期 outcome → evaluation → 獨立 calibration / OOS / forward
  → public-safe Analysis Packet / MCP
  → 任意相容平台的 LLM 用白話解釋
```

上圖是既有元件與目標資料流；**不是宣稱每段均已接通**。W2 離線鏈已接到 read-only model-input boundary；W3.1 已完成 prediction/outcome maturity 與 evaluation-as-of/scope governance。現有 broker `TICK` 對現有 `1d` 模型仍明確回 `INCOMPATIBLE_FREQUENCY`，所以沒有把 tick 假造成日線，也沒有宣稱 broker DATA READY。2026-09-26 最新 merged source/config build=`1037d45ff8e65884`，但最新 read-only preflight 為 `NO_RUNNING_OWNER`；因此 live runtime adoption 仍是 PENDING。C2.3 typed runtime re-verification、真實 forward 樣本與 calibration fitting 也仍未成立。

核心產品是研究 MCP 系統，不依賴 Cherry Studio 專屬能力。ChatGPT/OpenCode/其他 agent 是工程或解讀客戶端；不同平台用同一份具時間、來源、版本、限制的結構化輸出。

## 4. 模型角色

| 層 | 既有內容 | 正確解讀 |
|---|---|---|
| 基線 | last value、drift、seasonal naive、MA、ridge、VAR、Kalman 等研究基準 | 必須保留；打不贏基線可直接選基線 |
| 價格預測 | Chronos-2、TimesFM-3.0 | 有 adapter/登錄不等於對每個市場有有效預測證據 |
| 方向分類 | XGBoost、LightGBM | class score 不能直接稱校準機率 |
| 額外模型 | FinCast optional/partial；NHITS/NBEATSx、Kronos-TW、Sundial、TTM、Moirai challenger | 實際可用、依賴、授權、runtime 與成績分開核對 |
| 統合 | direct、joint、rule scenario、dynamic ensemble | 不混成一個不可追溯 final price；scenario 權重不自稱機率 |
| 主腦 LLM | 解釋、工具選擇、呈現限制 | 不手改中心/機率/ensemble 權重，不創造不存在的訊號 |

動態集成已有依 loss、calibration、failure rate、sample shrinkage 計算權重的設計。不要另造一套；驗證它使用的績效窗口是否在預測時已可用，並比較 equal-weight 與 best baseline。模型分位數的平均只可作研究摘要，不自動成為 mixture predictive quantile。

## 5. 凍結架構與目前門檻

| 元件 | schema |
|---|---|
| as-of、session truth、factor routing | 2A.2 |
| gap/session | 2B.1 |
| daily labels | 2C.2 |
| state machine | 2D.4 |
| extension/exhaustion | 2E.3 |
| catalyst response | 2F.3 |
| sequential updating | 2G.2 |
| prediction audit DB | 2H.3 |
| evaluation governance | W3.1 |
| precommitted forward cycle | W3.2 |
| calibration evaluation | 2I.1 |
| Price/Probability Map | 3A.2.3 |

V2-I 2I.1 是 evaluation engine，不是 fitting。已具 manifest、artifact/outcome pairing、typed rejection、Brier/log-loss/reliability/ECE/MCE、point/quantile/interval 評估；adapter 只可出 `INSUFFICIENT_EVIDENCE` 或 `EVALUATED_UNCALIBRATED`。`MIN_PROBABILITY_SAMPLES=2` 是計算描述統計的程式下限，不是足以認證機率的統計門檻。

公開研究狀態文件記錄：Osaka direct historical bars 有統計預測證據，但不可成交且沒有經濟優勢；proxy OOS 無證據；forward 尚未建立已驗證優勢；台股/台灣指數不得繼承 Osaka 成績。這些是 repo 中的狀態，這次未重算其研究實驗。歷史報告按資料集/階段解讀，不能把不同 scope 的證據混成全系統結論。

`AUTO_TRAIN / AUTO_FINE_TUNE / AUTO_PROMOTE = false`；`RESEARCH_ONLY / NO ORDER` 保持。新增行情不會自動訓練，也不等於已累積足量樣本。

## 6. 元大最新狀態必須分兩個層次

**歷史 PR #53 回報：** SPARK securities login 0001，TAIFEX/OSE subscription accepted 無 callback；futures profile 0112。保留為歷史證據。

**已合併 PR #54：** guide/matrix 記錄 SPARK 證券 profile 已收到 TAIFEX/OSE/CME/CBOT/CBOE/NYBOT matching callback，Legacy Quote 國內 T+1 也成功；當時 recorder 狀態檔可見活動。這批原功能已在 PR #54 發布；本次修補未重新做各市場 live probe。**目前 recorder 是否運行一律以上方最新 live truth 為準。**

三個 family：

1. SPARK securities profile 可支援多市場行情；不代表 futures profile 權限開通。
2. YuantaQuote COM 是獨立的 32-bit 行情 sidecar；不是 YuantaOrd。
3. YuantaOrd trading API 不接 runtime，不查帳務、不下單。

SPARK 日/夜碼與 Legacy 盤別規則不能互換。9/24 guide 指出 SPARK 可能要 PM 代碼；Legacy T+1 仍用 base symbol 加 ReqType=2。不要永久硬編當天代碼。

NQ/ES 不是現貨指數，VX 不是 VIX cash，JY 不是 USDJPY spot，ZN/ZF 價格不是殖利率。保留 representation 與方向/單位，不能直接替換原因子。

## 7. 跨對話需要真正維護的檔案

沿用 `AGENTS.md`、`scripts/agent_bootstrap.ps1`、`docs/development/AGENT_HANDOFF.md` 和 `project-status.md`，不要再造互相競爭的狀態中心。建議當前摘要只保留目前 phase/next/gates/evidence；歷史長報告留 research 目錄。

每棒交接最少包含：時間、repo/branch/HEAD/dirty、build_id、完成範圍、測試命令和 exit code、未驗證項、資料/校準/優勢狀態、commit/PR/remote/CI、下一工作包與復原方法。若工作樹有新修改，必須列出不能由 published HEAD 代表的檔案。

ChatGPT 專案資料來源是上傳快照，不會因 GitHub push 自動變成新版本。每棒另產出更新快照，提醒使用者替換舊檔。不要保存帳號、WinCred、行情全集或私有報告內容到雲端。

截圖顯示「僅限專案記憶」，「已停用」在庫存取權欄位；不能依此前述「記憶功能停用」當真。即使專案能參考其他對話，也不應依賴它逐字記得每個工程決策。官方說明：https://help.openai.com/en/articles/10169521-projects-in-chatgpt

## 8. 下一棒

W3.2 persisted-artifact ingestion/operator 已 OFFLINE PASS。下一步取決於真實 evidence：若 recorder root 已有合法 raw/evidence pair，直接用 offline CLI materialize 到 canonical Feature Store，再走既有 precommit；若沒有，產生新 pair 需要另行明確授權 C2.3 maintenance measurement。private artifact availability 本棒未能重新驗證；禁止用 continuous bars/TICK 冒充 DAILY terminal close。
