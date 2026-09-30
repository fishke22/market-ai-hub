# JNU 免費行情自動擷取

狀態：ACTIVE / QUOTE-ONLY / NO-PAID-DATA

## 可變開機時段（重要）

## Capture window 研究摘要

除了 coverage ledger，watchdog 也會自動更新：

`research/jnu_capture_window_summary.json`

這份摘要只計算「該 capture window 基準之後新增的資料」，不會把你開機前已累積的整晚數字灌進來。它會列出：

- 實際 verified 開始、最後健康時間、關閉原因與和上一段的 gap。
- 這段期間新增的 trade count、DealVol、window VWAP、new 5-minute bars。
- microstructure 是否 live verified、callback 數、dropped records、persistence error。
- session price/volume profile 是否可用；若只是整個 session 的累積 profile，會明確標示不是 window-specific。
- 為何目前不是 `FULL_SESSION_LABEL_READY`，例如缺官方 open 或 close boundary。

若功能在一個已經進行中的 window 中途才上線，第一個 baseline 只從上線時開始，會標 `metrics_complete_from_window_start=false`，不會倒算。下次重新開機時，前一段 window 只關到最後一次 verified healthy 時間，不會把重開機時刻假裝成前次關機時間。

日常不要求整夜開機。你的慣用時段約為 **18:55 開機、22:00 關機**，但可以提早、延後或提早關機；系統會以實際 availability 為準。

每 5 分鐘 watchdog 會把 verified healthy recorder availability 寫到：

`automation/jnu_capture_coverage.json`

規則：

1. 18:55–22:00 只是慣用參考，`informational_only=true`，不是硬 gate。
2. 提早開機就提早開始累積；晚開機就從晚開那一刻開始。
3. 健康樣本中斷超過 8 分鐘，視為新的 capture window；缺的時間不補造。
4. 有真實 StockTick 的 window 即使不含官方開盤或收盤，仍保留為 `PARTIAL_WINDOW` 並可做 context/微結構研究。
5. 只有實際觀察到官方 session open + close 邊界時，才可標 `FULL_SESSION_LABEL_READY`。這是額外證據，不是要求你整夜開電腦。

## 2026-09-30 零成本採用狀態

- 本機擷取不需要 AWS，也不需要任何付費行情服務；AWS 永久視為 optional。
- Windows task `MARKET_AI_HUB_JNU_Capture_Watchdog` 現在每 5 分鐘執行一次 `ensure_jnu_data_capture.ps1`，不再等固定 18:55。只要 Windows 已登入且主機開著，task 會維持 single-owner quote-only recorder；主機關機時資料自然缺失，不做 backfill。
- recorder 已正式採用 bounded auto reconnect（最多 3 次）；若 runtime build 改變，watchdog 先 graceful stop，再重啟唯一 owner；只有 heartbeat stale 且 fail-closed 條件成立才允許獨立 force-stop helper。
- JNU StockTick 會同步增量產生 `data/live/yuanta/materialized/jnu_sessions.json`（實際根目錄由 `MARKET_AI_DATA_ROOT`/runtime path 決定），供研究層直接讀取 5m bars、VWAP、range/profile 與 session coverage。這不是預測結果。
- 必須從開盤邊界一路觀察到收盤邊界，該 session 才可成為 label-ready。晚開機、斷線或缺邊界的 session 只保留 partial/context，不能事後補成完整樣本。


## 目的

在不購買 JPX/OSE 付費 tick/L2 的前提下，優先使用既有元大 SPARK 行情權限，自動擷取 exact JNU 個別月份行情。

## 單一 owner

- 唯一登入 owner：MARKET_AI_HUB Yuanta live recorder
- 憑證：Windows Credential Manager
- 禁止建立第二個元大登入 session
- 禁止下單、改單、撤單

## Exact JNU microstructure

同一個 SPARK owner 額外對 active JNU individual contracts 訂閱：

- SubscribeStockTick
- SubscribeFiveTickA

目前設定最多同時追蹤 2 個 exact JNU 月份，以 resolver 的實際 JNU\d{4} 為準。

資料會進入 recorder 既有 durable spool / normalized Parquet。若 StockTick 或 FiveTick 權限不存在，該能力 fail-soft，不得讓 Watchlist 行情 recorder 因此停止。

## 自動維持

Windows Scheduled Task：

`MARKET_AI_HUB_JNU_Capture_Watchdog`

每 5 分鐘執行：

`scripts\ensure_jnu_data_capture.ps1`

規則：

1. 用內建 OSE calendar 判斷是否為 OSE session date。
2. 非交易日：IDLE，不登入。
3. 交易日且 recorder 不在：自動啟動。
4. recorder 正常：沿用同一 owner。
5. runtime build stale：安全停止後重啟。
6. duplicate/unverified owner：fail closed，不建立第二登入。
7. SPARK connection fault：先使用 bounded auto-reconnect；若 process 仍失敗退出，由 watchdog 下次重啟。

## Capability 驗證

送出訂閱不等於已證明帳號有 callback 權限。

只有在有效 OSE 交易時段實際收到：

- SubscribeStockTick callback -> exact streaming tick VERIFIED
- SubscribeFiveTickA callback -> depth VERIFIED

才可讓 JNU Research 啟用相應 order-flow / book features。

沒有真實 callback 時一律標記 UNVERIFIED / UNAVAILABLE。

## 本機關機

Windows 關機時本機當然無法擷取元大資料，也無法由 Scheduled Task 自行開機。

ChatGPT 端另有交易日條件監控，用來檢查本機是否在線；若離線，JNU 分析自動降級到免費官方/外掛 fallback，不採用任何付費資料。
