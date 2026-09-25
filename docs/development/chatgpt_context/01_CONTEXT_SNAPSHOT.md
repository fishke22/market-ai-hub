# MARKET_AI_HUB 跨對話上下文快照

快照日期：2026-09-25（Asia/Taipei）。用途：上傳 ChatGPT 專案資料來源。此檔是查核資料，不是新的執行授權。後續應替換此快照，避免多份「最新」並存。

## 1. 先讀這段

本專案已超過第一階段。公開 main 已有 Phase 2、多輪安全與資料語義修正、Price/Probability Map 基礎，以及 V2-A 至 V2-I 2I.1。不要把「第二階段施工」解讀成 V2-I 尚未存在，也不要重做它們。

實際施工 repo 是 `D:\MARKET_AI_HUB`；本次 Codex 的 `C:\Users\fishk\Documents\ChatGPT\MARKET_AI_HUB` 原先只是空 Git 倉庫，現在只存本交接包，不能混為同一 repo。

GitHub：https://github.com/fishke22/market-ai-hub

2026-09-25 C2 W3.3 controlled-measurement path 最新交接：

controlled-path initial commit = `ed3e63360faca93f6a5a6b0af89fc1ecb51702bf`；correlation-hardening commit = `9496eb9afa65e647b5fceca86610247ff24e258e`；review fixes = `30d32754ff284a6b32370b236ed1fc40283304e9`、`0203e9becf0f0894c3d9f33cfdc2aece448db921`、`873e6bd9697efe1bc2c67d1767c708b23af2df10`；maintenance-control = `4cca09117ffda0fb2ead12de737ffcaf8b92ad9c`；request-script repair = `1452a45cf0c4de631d213eaa8648c3eae3b90211`；startup-observability source = `b9cfcb0e302e1520027d2c69adf363d15baf00c4`；current source/config build_id = `afd52f88a351541a`。
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

上圖是既有元件與目標資料流；**不是宣稱每段均已接通**。W2 離線鏈已接到 read-only model-input boundary；W3.1 已完成 prediction/outcome maturity 與 evaluation-as-of/scope governance。現有 broker `TICK` 對現有 `1d` 模型仍明確回 `INCOMPATIBLE_FREQUENCY`，所以沒有把 tick 假造成日線，也沒有宣稱 broker DATA READY。W1/W2 recorder runtime adoption 已成立，且最新 current-build safe-default recorder 正在 RUNNING；但 C2.3 typed runtime re-verification、真實 forward 樣本與 calibration fitting 仍未成立。

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

先核對最新 HEAD/remote/worktree/build/PR #55 CI，並先跑 `scripts/check_yuanta_recorder_owner.ps1`。W2/W3.1/W3.2/W3.3 engines 不要重做。最新 truth 是 current-build safe-default recorder 已 RUNNING 且 measurement runtime gate=false，所以平時不要再開第二 owner；parent+child matching Python PID 是同一 invocation，不要用 raw process count 判 duplicate。下一次新的使用者 continuation若落在有效 OSE 15:45–17:00 JST 視窗內，preflight 必須沒有 independent duplicate risk，才安全交接/停止唯一 safe-default owner，再用已證明的 foreground Runner Job 路徑以 current C2.3 build `afd52f88a351541a` 啟動 maintenance owner，驗 fresh W1/W2 provenance + FunctionList exact JNU，再只送一筆 measurement。typed evidence 成立才 materialize DAILY close；否則 fail closed。C3/C4 仍等待真實 C1/C2 輸入。
