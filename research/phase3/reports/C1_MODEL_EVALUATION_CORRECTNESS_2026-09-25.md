# C1 模型評估比較可信度補強

日期：2026-09-25（Asia/Taipei）。本報告只記錄 C1 評估比較補強；不代表 DATA READY、CALIBRATED、PREDICTIVE EVIDENCE 或 TRADING EDGE。

## 基準與範圍

- 實際 repo：`D:\MARKET_AI_HUB`
- 分支：`codex/quote-hub-correctness`
- C1 開工 HEAD：`91fabc496b25ed3304106d6fe0b52a6e74b7e674`
- C1 程式/測試 commit：`50f209a095a151b6ae42c6db5d0d462d11fd2395`
- runtime build_id：`c64b98bd4a09d576`
- 開工時既有 staged W3.3：`docs/architecture/v2-tick-detail-source-contract.md`、`research/phase3/reports/W33_TICK_DETAIL_SOURCE_2026-09-25.md`。本包未修改、未提交它們。

## 根因與修正

1. Tournament 原本只特別計 adapter failure，拒答、非有限輸出、無效 target 可能混入樣本分母/指標。現在逐 origin 保存 `VALID / FAILED / ABSTAINED / NONFINITE / INVALID_TARGET`，有效樣本與 coverage 由狀態計算。
2. 比較原本可拿各自成功子集的 MAE；CLI 也未持久化共同-origin 比較。現在 pairwise 只用共同有效 origins，並同時保存雙方完整 coverage；CLI compare 讀 pairwise store，best 摘要只接受 full coverage。
3. Performance Store 原本可接受 NaN/Inf 或缺失/矛盾 accounting。C1.1 current rows 現在 fail-closed；legacy rows 仍可查，但預設 leaderboard 依 schema 隔離。
4. Random-walk baseline 原本忽略 horizon；現在依 steps 抽樣並複利。
5. Research classification baseline 在缺 train labels 時原本可用 test labels 推多數類；現在 majority baseline 為 NOT_AVAILABLE。
6. Rates regime 原本回看索引錯位且未對齊 10Y/5Y 同日樣本；現在使用 aligned curve 的 20-session change。
7. 歷史/手工 `ModelRun` 缺 directions 時，status fallback 曾被 zip 截斷；現在按 actual origins 長度逐列推導。
8. baseline MAE=0 時不做相對除法，避免 Inf/假排名。

## 驗證

- 初始 C1 regression：`11 passed, 4 failed`，exit 1；失敗為 nonfinite result、nonfinite pairwise、inflated accounting 未拒絕，以及 pairwise 無 target/horizon scope。
- 中途 broader regression 另重現 interval-origin 相容性反例；修正後通過。
- 最終 focused：`198 passed, 6 deselected in 34.76s`，exit 0。
- 未排除 Windows global mutex 的完整離線跑法：`1802 passed, 34 deselected, 1 failed`；唯一失敗是 `test_single_instance_lock_releases_after_error` 遇到 `YUANTA_LIVE_ALREADY_RUNNING`。沒有停止或重啟 recorder 來換綠燈。
- 最終 offline profile 明確排除上述單一現場 mutex 測試：`1804 passed, 35 deselected, 110 warnings in 129.47s`，exit 0。
- C1 changed-file secret scan：0 hits；`git diff --check`：PASS。

## 邊界與下一包

本包沒有 broker login/logout/restart/subscribe、沒有 order/account/position/balance、沒有 calibration fitting、沒有新增模型、沒有重跑真實市場排行榜、沒有建立真實 forward evidence。舊排行榜必須依新 accounting/version 與相同考卷重跑後才可比較。

下一包是 C2：沿用 W3.3，在單一 recorder owner 與明確維護窗口下驗證 OSE tick-detail 的日期/時區/逐合約/terminal-close 語義，完成可用 DAILY terminal close 證據後再接 W3.2。未授權維護窗口時不得 restart/login/retry broker。C3/C4 仍等待 C1/C2 的真實資料條件。

回復 C1 程式時走 `git revert 50f209a` 的正常 review 流程；不要 reset/clean/stash 其他工作者的 W3.3 staged 內容。
