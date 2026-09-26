# JNU 免費行情自動擷取

狀態：ACTIVE / QUOTE-ONLY / NO-PAID-DATA

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
