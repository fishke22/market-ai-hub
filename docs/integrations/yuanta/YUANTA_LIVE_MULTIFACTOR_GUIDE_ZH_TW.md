# 元大即時多因子行情整合指南（繁體中文）

> 狀態：2026-09-24 正式環境實測。
> 本文件是 MARKET_AI_HUB 的長期 AI/工程交接文件；聊天記憶不得取代本文件與 machine-readable matrix。
> Machine-readable evidence：`config/yuanta_live_factor_matrix.yaml`。

## 1. 最重要結論

目前可不等客服，直接取得大量即時因子行情：

1. **SPARK 證券帳號**已實測可登入正式環境（MsgCode=0001），並可收到
   TAIFEX、OSE、CME、CBOT、CBOE、NYBOT 的期貨行情 callback。
2. **Legacy Futures Quote（YuantaQuote COM）**用使用者身分登入 ID +
   Windows Credential Manager 內既有的證券密碼，T/T+1 均實測 LogonOK；
   T+1 的 TX/MTX/TMF/UNF 已收到 OnGetMktData。
3. SPARK 的「期貨帳號」登入仍實測回 0112；這不妨礙用已驗證的 SPARK 證券帳號取得行情。
4. **SPARK 應作跨市場主要即時行情來源；Legacy Quote 作國內 TAIFEX 備援。**
5. 任何 API method 被接受都不等於行情成功；只有收到「同 market + 同 instrument」callback 才算 LIVE_CALLBACK_VERIFIED。

## 2. 三套 API 必須永久分離

### 2.1 元大證券 API / SPARK
- Runtime：64-bit Python + pythonnet + `YuantaOneAPI.YuantaSparkAPITrader`。
- 正式環境登入：SPARK securities profile；目前已驗證 MsgCode=0001。
- 行情：優先 `SubscribeWatchlistAll`，也有 `SubscribeWatchlist`。
- 官方 market enum 包含：TWSE=1、TWOTC=2、TAIFEX=3、SGX=202、CME=203、
  CBOT=204、OSE=207、NYBOT=209、CBOE=215 等。
- 官方文件允許行情訂閱的 LoginAcno 為證券或期貨帳號。
- **API 支援市場 ≠ 某一帳號一定有 entitlement。**

### 2.2 元大期貨行情 API / Legacy YuantaQuote
- COM：`YUANTAQUOTE.YuantaQuoteCtrl.1`，32-bit sidecar。
- 只做行情；與期貨交易 API 完全分離。
- 登入：`SetMktLogon(login_id, password, host, port, ReqType, 0)`。
- 已驗證登入 ID 可使用使用者身分登入 ID；repo 不得保存實際身分證字號。
- 密碼使用 WinCred 的 securities profile secret；不得寫入 repo/env/命令列/log。

### 2.3 元大期貨交易 API / YuantaOrd
- 本專案目前不連 runtime。
- NO ORDER / NO position / NO balance。
- 不得因行情需求而載入或呼叫交易 API。

## 3. SPARK 正確訂閱流程

流程必須是：

```text
OrderApiExposureGuard PASS
→ Open(PROD)
→ Login(securities account, WinCred secret)
→ 等 OnResponse/Login MsgCode=0001
→ 建 WatchlistAll(MarketType, StockCode)
→ SubscribeWatchlistAll(...)
→ 只接受與要求的 market_no + instrument_code 完全相符的 callback
→ 常駐 Hub 保持訂閱與單一登入
→ agent 只讀 latest/status 或排入 dynamic request
→ 電腦/recorder process 結束時才關閉 connection
```

注意：前一商品退訂後仍可能有晚到 callback。若只看「收到任何 callback」就會造成假陽性。
`spark_futures_quote_probe.py` 已修正為 market + instrument exact-match 才計入成功。

### Callback 時間
- IndexFlag29 的 `TYuantaTime` 可提供來源 time-of-day，但沒有日期：
  `timestamp_quality=SOURCE_TIME_OF_DAY_ONLY`。
- 其他 callback 若沒有來源時間，只能保存本機 `received_at UTC`：
  `timestamp_quality=LOCAL_RECEIVE_TIME_ONLY`、`event_timestamp=UNKNOWN`。
- 日期必須交由 V2-A.2 session/trading-day truth推導，禁止自行把本機日期塞成 exchange date。

## 4. 2026-09-24 SPARK 實測成功矩陣

以下 symbol 只代表當日 evidence；未來必須由最新版 FunctionList.xlsx / 商品表解析當期合約。

| 經濟因子 | 市場 | 當日實測碼 | 結果 | 系統角色 |
|---|---:|---|---|---|
| 台灣指數 | TAIFEX 3 | TMFPMJ6 | LIVE_CALLBACK_VERIFIED | 夜盤 derivative proxy |
| 日本股票 / OSE Micro | OSE 207 | JNUPM2612 | LIVE_CALLBACK_VERIFIED | **DIRECT target** |
| 美國科技風險 | CME 203 | NQ_2612 | LIVE_CALLBACK_VERIFIED | derivative proxy |
| 美國科技風險 | CME 203 | MNQ2612 | LIVE_CALLBACK_VERIFIED | derivative proxy |
| 美國大盤風險 | CME 203 | ES_2612 | LIVE_CALLBACK_VERIFIED | derivative proxy |
| 美國波動 | CBOE 215 | VX2610 | LIVE_CALLBACK_VERIFIED | VIX futures proxy |
| 日圓 | CME 203 | JY_2612 | LIVE_CALLBACK_VERIFIED | FX derivative proxy |
| 美國5年利率 | CBOT 204 | ZF2612 | LIVE_CALLBACK_VERIFIED | Treasury futures proxy |
| 美國10年利率 | CBOT 204 | ZN2612 | LIVE_CALLBACK_VERIFIED | Treasury futures proxy |
| 黃金 | CME 203 | GC2610 | LIVE_CALLBACK_VERIFIED | derivative proxy |
| 原油 | CME 203 | CL2611 | LIVE_CALLBACK_VERIFIED | derivative proxy |
| 美元廣義指數 | NYBOT 209 | DOLINDX2612 | LIVE_CALLBACK_VERIFIED | DXY futures proxy |

`CL2610` 同輪沒有 callback，而 `CL2611` 有 callback：合約選擇必須動態處理到期/轉倉。

### 4.1 不能直接等同現貨的項目
- JY futures **不是 USDJPY spot**。若模型原本的方向是 USDJPY，不能直接把 JY return 當同號訊號。
- ZF/ZN 是美債期貨價格，**不是 5Y/10Y yield**；期貨價格與殖利率方向通常相反。
- VX 是 VIX futures，**不是 VIX cash index**。
- NQ/MNQ、ES 是 futures proxy，不得覆蓋 NASDAQ-100 / S&P500 cash identity。
- DOLINDX 是美元指數 futures，不得覆蓋 DXY cash identity。

V2-A.2 必須把它們標成 `DERIVATIVE_PROXY`，保留 venue / contract / roll / timestamp provenance。

### 4.2 目前沒有直接證據的因子
- FunctionList 未找到 direct SOX cash；夜間 US tech risk 優先用 NQ/MNQ，不得假稱 SOX。
- FunctionList 未找到 BTC spot；不可因其他商品成功就宣稱 crypto 可用。
- TWSE 的 `IX0001`、2330 在本次夜間測試只得到訂閱接受、0 callback；這符合 cash market 已收盤，
  不能解讀為 entitlement failure。白天需另外做 session-aware驗證。

## 5. Legacy Futures Quote 正確做法

已實測 T / T+1：
```text
Status=2
LogonOK
message_code=0
```

官方 sample 與本機實測一致：
```python
AddMktReg(base_symbol, 4, ReqType, 0)
# ReqType=1: T
# ReqType=2: T+1
```

T+1 **仍用 base symbol**；EasyWin 的 `xxxPM` 是 UI/alias metadata，不是 canonical AddMktReg symbol。

### 5.1 2026-09-24 國內 T+1 實測成功
| 因子 | AddMktReg symbol | ReqType | 結果 |
|---|---|---:|---|
| 台指期 | TXFJ6 | 2 | OnGetMktData |
| 小台指 | MXFJ6 | 2 | OnGetMktData |
| 微台指 | TMFJ6 | 2 | OnGetMktData |
| Nasdaq-100 台灣期貨 | UNFL6 | 2 | OnGetMktData |

因此 `legacy_domestic_quote = LIVE_CALLBACK_VERIFIED`。

### 5.2 Legacy 海外期貨：目前不要當主要來源
實測 actual contract symbol：
`JNU2612/NQ2612/MNQ2612/ES2612/VX2610/JY2612/FV2609/TY2609/GC2610/CL2610`
在 ReqType 1/2 皆未取得行情，主要回 `OnRegError ErrCode=3`。

有限 alias驗證：
- `NQ1`：AddMktReg return=1，無 callback。
- `JNU1`：AddMktReg return=0，但 OnRegError=3。

因此在現有帳號/路徑下：
**海外多因子一律優先走 SPARK securities profile；Legacy Quote只作已驗證的國內 TAIFEX備援。**

ErrCode=3 的官方文字定義目前仍未在本機文件/公開資料中確認，不得自行命名其原因。

## 6. SPARK 官方訂閱限制

依元大官方「使用限制說明」：
- 單一連線，不同 FunctionID 的總訂閱商品上限：**2000**。
- 同 FunctionID 單次訂閱商品上限：**200**。
- 同 FunctionID 每秒最多發送訂閱：**10次**。
- 單一帳號總訂閱商品數：**3000檔**。
- 單一帳號同時最高連線數：**10**。
- 行情類跨 FunctionID：每分鐘最多1200次呼叫。

不要用這些上限作為正常操作目標；MARKET_AI_HUB應只訂閱實際需要的最小因子集合。

## 7. MARKET_AI_HUB 建議的即時因子路由

優先順序：
1. **直接 target**：若 OSE Micro 的 SPARK夜盤 callback可用，使用 OSE direct。
2. **跨市場 live factors**：SPARK securities profile。
3. **國內 TAIFEX備援**：Legacy Futures Quote。
4. cash市場收盤後，cash只保留 `PREVIOUS_SESSION_REFERENCE`，不得冒充 live。
5. provider沒有 callback時保留 `NOT_AVAILABLE`，不得用上一筆值假裝即時。

推薦表示：
```text
JP_EQUITY      -> OSE_MICRO_NIGHT (DIRECT) + Nikkei cash previous reference
TW_INDEX       -> TMF/TX/MTX live derivative proxy + TAIEX cash previous reference
US_TECH_RISK   -> NQ/MNQ live derivative proxy
US_BROAD_RISK  -> ES live derivative proxy
US_VOLATILITY  -> VX live derivative proxy
JPY_FX         -> JY futures derivative proxy
US_RATES       -> ZF/ZN futures derivative proxy
GOLD           -> GC futures
WTI_OIL        -> current active CL futures
USD_BROAD      -> DOLINDX futures
```

每筆 observation 都必須進 V2-A.2：
`economic_factor_id / representation_id / venue / session / trading_date / event_timestamp /
available_at / received_at / timestamp_precision / provider / contract / roll_status`。

## 8. 合約碼與夜盤碼：禁止硬編碼

### SPARK
權威來源：
`vendor/yuanta_spark/<version>/.../IO_Doc/FunctionList.xlsx`

夜盤有時是獨立報價碼：
- TAIFEX：例如 `TMFPMJ6`
- OSE：例如 `JNUPM2612`

所以「市場正在夜盤」時不可只把日盤 `TMFJ6/JNU2612`拿去訂閱。
2026-09-24 的失敗案例正是日盤碼被接受但0 callback；改成 PM碼後立刻收到真實行情。

### Legacy Quote
權威來源：
`C:\Yuanta\yeswin\AGENT\YSTrader\Data\List\M.TFX.TXT`

Legacy規則相反：
**AddMktReg 的 T+1 canonical symbol仍用 base symbol**，盤別由 ReqType=2區分；
`TMFJ6PM`只是EasyWin UI alias。

這兩個 namespace絕對不能互換。

## 9. 合約到期 / roll
- 測試碼不等於永久碼。
- 每次啟動需重新解析當期/下一有效合約。
- CL2610 本次0 callback、CL2611成功，是典型到期/active-contract風險。
- 任何 futures observation 必須保存 `contract_code / contract_month / roll_status / series_semantics`。

## 10. AI 開工前檢查表

任何新 agent 在改元大行情前，先做：
1. 跑 `scripts/agent_bootstrap.ps1`。
2. 讀 `AGENTS.md`、`docs/development/AGENT_HANDOFF.md`、本文件。
3. 讀 `config/yuanta_live_factor_matrix.yaml`。
4. 重新讀最新版 FunctionList.xlsx / EasyWin商品表，不沿用過期contract code。
5. 確認當下 venue session；日盤碼/夜盤碼依 API namespace處理。
6. SPARK callback success 必須 exact-match market+instrument。
7. Legacy Quote success 必須收到 OnGetMktData/OnGetMktQuote；AddMktReg return=0本身不算成功。
8. API成功 ≠ calibrated probability ≠ predictive edge ≠ trading permission。

## 11. 安全邊界
- Quote-only。
- 不呼叫 YuantaOrd。
- 不查持倉/餘額/帳務。
- 不把密碼、完整帳號、身分證字號寫入 Git、報告、JSON或console。
- WinCred只由既有 credential helper讀取。
- 正式常駐錄製入口：`python -m market_ai_hub.integrations.yuanta.live_quote_recorder`；日常由 `scripts/start_yuanta_live_recorder.ps1` 啟動。
- recorder 單一 process 長連線；agent 使用完不得 logout。Windows Startup 已配置自動啟動，關機/程序終止時才斷線。
- 長期訓練資料以壓縮 Parquet 為主；raw JSONL 預設關閉，避免高頻 callback 造成不必要的磁碟膨脹。

## 12. 相關來源
- 元大 SPARK官方：行情報價表訂閱 / SubscribeWatchlistAll。
- 元大 SPARK官方：市場 enum（TAIFEX/CME/CBOT/OSE/CBOE等）。
- 元大 SPARK官方：使用限制說明。
- 本機元大 FunctionList.xlsx。
- 本機 Legacy Quote Python/C#官方 sample。
- EasyWin/YesWin `Data\List\M.TFX.TXT`、`M.FFX.TXT`。
- 實測 evidence report：`research/phase3/reports/YUANTA_MULTIFACTOR_LIVE_QUOTE_MATRIX_2026-09-24.md`。


## 13. 常駐 Quote Hub（任何 agent 共用）

### 啟動與 single-instance
- 手動：`scripts/start_yuanta_live_recorder.ps1`
- 前景診斷：`scripts/start_yuanta_live_recorder.ps1 -Foreground`
- Windows 使用者 Startup 已配置自動呼叫同一啟動腳本。
- 啟動腳本會先讀 `data/live/yuanta/status.json` 並檢查 PID；已有 RUNNING process 時只回 `YUANTA_LIVE_ALREADY_RUNNING`，不得建立第二個登入。

### Agent 讀取與追加訂閱
任何 agent 需要即時行情時：
1. 先讀 `data/live/yuanta/status.json`。
2. 直接讀 `data/live/yuanta/latest.json` 取得最新快照。
3. 若需要額外商品，使用：
   `scripts/request_yuanta_quote.ps1 -MarketNo <market> -Symbol <symbol>`
4. recorder 會在**既有 SPARK connection**上追加 `SubscribeWatchlistAll`；agent 不讀密碼、不 Login、不 Logout。
5. request 會移到 `control/processed` 或 `control/failed`，fail-closed。

### 受控 OSE Tick-detail measurement（平常停用）
- `config/yuanta_live_recorder.yaml` 的 `tick_detail_measurements.enabled` 預設為 `false`。
- 只有明確 maintenance-window 授權後，才可受控重啟 recorder 到已發布 current build。不要把 tracked safe default 改成 true；一般本機維護可使用 `scripts/start_yuanta_live_recorder.ps1 -EnableTickDetailMeasurements` 做 runtime-only 啟用。
- **WebCodex 特例：** one-shot Runner command 結束後，其背景 child 不保證能繼續存活。受控 measurement 必須用 `scripts/start_yuanta_live_recorder.ps1 -Foreground -EnableTickDetailMeasurements` 啟動成 long-running Runner Job；保持該 Job 存活，再從另一個工具呼叫檢查 status / queue measurement / queue shutdown。不要用 shell detachment trick 繞過 Runner lifecycle。
- 正常維護停機使用 `scripts/stop_yuanta_live_recorder.ps1`；它送 control-inbox `shutdown`，讓 recorder 自己走 close/dispose + pending flush。不要把 `Stop-Process` 當正常維護流程。
- 啟用後仍只由**同一個 recorder owner**執行；agent 不自行 Login/Logout。
- 受控入口：`scripts/request_yuanta_tick_detail_measurement.ps1 -Symbol JNU<YYMM> [-LastCount 20]`。
- request 只允許 OSE market 207、exact `JNU\d{4}`、`LastCount<=20`，且 request/callback 都必須落在 15:45–17:00 JST。
- recorder 啟動時凍結 `runtime_build_id`；measurement 會重新計算目前磁碟 fingerprint，若與 process build 不同就在碰 API 前 fail closed。
- evidence builder / materializer 會重新從 raw batch + request/callback times 驗證 timestamp basis，不接受 caller 自行聲稱 cross-check 成功。
- raw tick 值只寫本機 `evidence/tick_detail/raw`；control result 與 verification evidence 不公開價格。
- 2026-09-25 maintenance-window 授權已取得；current startup-observability build_id = `ba7c0e1b9ca9d62c`。第二次 WebCodex attempt 已實證 SPARK login `0001` 與 current-build RUNNING，但背景 child 在 one-shot launcher 結束後消失；未送 tick-detail measurement。下一次須走上述 foreground Runner Job 路徑。

### 長期資料
- 主訓練格式：`data/live/yuanta/parquet/YYYY-MM-DD/*.parquet`
- 即時快照：`latest.json`
- heartbeat：`status.json`
- raw JSONL 預設關閉；Parquet 已足以保存 recorder 正規化後的 callback 欄位，且大幅降低磁碟占用。
- `data/live/` 僅本機保存並已 gitignore。

### 預設錄製範圍
以 `config/yuanta_live_recorder.yaml` 為唯一設定來源；目前預設：
- OSE Micro direct；
- TAIFEX TMF/TX/MTX/UNF（日/夜碼並存）；
- CME NQ/MNQ/ES/JY/Gold/WTI；
- CBOT 5Y/10Y Treasury futures；
- CBOE VIX futures；
- NYBOT DXY futures；
- TWSE交易時段的 TAIEX與2330 context。

衍生品預設保存近月＋次近月，以建立 roll/basis/期限結構資料。商品碼每次啟動由最新版 FunctionList解析；禁止把本文件的測試合約碼當永久碼。

### Shutdown
agent 使用完**不要 Logout**。Recorder process維持一個登入；只有 recorder process結束或Windows關機時才關閉連線。
