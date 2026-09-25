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
- recorder runtime adoption / restart 仍需明確 maintenance-window 授權。

## 發布與工作樹邊界

Implementation commit 只包含 C2 code/tests。開工前已 staged 的：
- `docs/architecture/v2-tick-detail-source-contract.md`
- `research/phase3/reports/W33_TICK_DETAIL_SOURCE_2026-09-25.md`

仍視為 pre-existing staged W3.3 work，不屬於 implementation commit，也不得因本報告而冒稱它們已被本棒重新驗證。

下一個 bounded package 是 **C2 runtime measurement**：只在使用者明確允許安全維護窗口後，透過既有單一 owner 路徑收集 matched request/callback + timestamp-basis cross-check evidence，再由本次 materializer 產生第一筆 eligible DAILY terminal close。沒有授權就保持 offline，不 restart/login。
