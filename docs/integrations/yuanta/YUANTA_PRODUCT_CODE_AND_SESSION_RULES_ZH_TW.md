# 元大商品代碼、MarketNo、日夜盤與 Resolver 規則

> AI/工程規格。任何 agent 在新增行情前必讀。
> 目的：防止把 Yahoo ticker、下單碼、日盤碼、夜盤碼、Legacy alias 混在一起。

## 1. Source of truth

### SPARK
權威來源：
`vendor/yuanta_spark/2.2026.0918.0/YuantaSparkAPI_win-x64_Python/IO_Doc/FunctionList.xlsx`

來源取得：
https://ys.yuanta.com.tw/quartet/api/YuantaSparkAPI_win-x64_Python.zip

規則：
- 行情報價碼 = FunctionList 的 quote code / StkCode。
- 下單碼 = order_code/Commodity，與 quote code 可不同。
- quote code與order code是不同 identity，禁止互換。
- package更新時 FunctionList.xlsx 必須同步更新 resolver。

### Legacy YuantaQuote
國內：
`C:\Yuanta\yeswin\AGENT\YSTrader\Data\List\M.TFX.TXT`

海外參考：
`C:\Yuanta\yeswin\AGENT\YSTrader\Data\List\M.FFX.TXT`

Legacy AddMktReg：
- 使用 base quote symbol。
- T/T+1 由 ReqType區分。
- EasyWin `xxxPM` 僅 UI/alias metadata，不能直接當 canonical AddMktReg symbol。

## 2. SPARK MarketNo

官方 enumMarketType：
- TWSE = 1
- TWOTC = 2
- TAIFEX = 3
- SGX = 202
- CME = 203
- CBOT = 204
- TCE/TOCOM = 205
- OSE = 207
- HKFE = 208
- NYBOT/ICE-US = 209
- LIFFE/ICE-UK = 210
- EUREX = 211
- ASX = 212
- CBOE = 215

官方來源：
https://www.yuanta.com.tw/file-repository/content/sparkapi_docs/%E5%9F%BA%E7%A4%8E/%E5%88%97%E8%88%89%E7%89%A9%E4%BB%B6/index.html

## 3. 日盤/夜盤 namespace

### SPARK
日盤/夜盤可能是不同 quote code。
2026-09-24 實測例：
- TAIFEX TMF day：`TMFJ6`
- TAIFEX TMF night：`TMFPMJ6`
- OSE Micro day：`JNU2612`
- OSE Micro night：`JNUPM2612`

這些只是當日 evidence，不得永久 hardcode。

Resolver 必須：
1. 讀最新 FunctionList.xlsx。
2. 先選 market。
3. 再選商品 family/order root。
4. 依 venue session決定 day/PM variant。
5. 過濾 spread/alias。
6. 跳過已到期 contract。
7. 選 near + next contract。
8. 保存 contract code/month/roll status。

### Legacy Quote
規則相反：
- `TMFJ6` + ReqType=1 → T。
- `TMFJ6` + ReqType=2 → T+1。
- `TMFJ6PM` 不是 canonical AddMktReg symbol。

## 4. 目前已驗證的多因子映射

以下 measured symbol只用作 regression evidence：

- TW_INDEX
  - SPARK TAIFEX TMF night
  - SPARK TAIFEX TX/MTX
  - Legacy TX/MTX/TMF backup
- JP_EQUITY
  - OSE Micro direct target
- US_TECH_RISK
  - CME NQ
  - CME MNQ
  - TAIFEX UNF backup/context
- US_BROAD_RISK
  - CME ES
- US_VOLATILITY
  - CBOE VX futures
- JPY_FX
  - CME JY futures
- US_RATES
  - CBOT ZF futures（5Y proxy）
  - CBOT ZN futures（10Y proxy）
- GOLD
  - CME GC futures
- WTI_OIL
  - CME CL futures
- USD_BROAD
  - NYBOT DOLINDX futures

## 5. Semantic warnings

禁止 silent substitution：

- NQ/MNQ != Nasdaq-100 cash index。
- ES != S&P 500 cash index。
- VX futures != VIX cash index。
- JY futures != USDJPY spot；方向語義不可直接等同。
- ZF/ZN futures price != Treasury yield；價格與殖利率通常反向。
- DOLINDX futures != DXY cash identity。
- OSE Micro direct != ^N225 proxy。
- TX/MTX/TMF != TAIEX cash。

V2-A.2 必須保留：
- economic_factor_id
- representation_id
- relation
- temporal_role
- venue/calendar
- session_status
- trading_date
- event_timestamp / available_at / received_at
- provider
- contract / contract_month / roll_status / series_semantics

## 6. Cross-representation arithmetic

禁止：
- 把 cash close和 futures current直接拼成普通 return。
- 把不同 contract price直接當連續報酬。
- 把 day quote code與PM quote code當兩個不同經濟商品。

如果需要：
- cash-futures差異 → typed basis/gap。
- contract roll → explicit continuous-series/roll adjustment。
- day/PM code →同一 contract representation的session-specific quote identity。

## 7. 合約選擇

### TAIFEX
現有 system expiry rule：
- 月契約第三個星期三。
- 到期日特殊收盤/盤後規則由 session_truth fail-closed處理。

### OSE Nikkei Micro
現有 system expiry rule：
- 該月第二個星期五之前一個JPX business day。

### 海外
- 不能僅依年月字串猜 active contract。
- 優先 FunctionList + callback evidence。
- recorder保留近月+次近月，讓 roll/basis可研究。
- 若近月無callback、次近月有callback（例如2026-09-24 WTI測試），不可強迫近月為primary。

## 8. SPARK callback success

只有以下全部成立才算 live：
1. Subscribe call已送出。
2. OnResponse callback抵達。
3. callback `market_no == requested market_no`。
4. callback `instrument_code == requested symbol`。
5. received_at可證明新鮮度。

不得用：
- method return=True
- 上一商品晚到callback
- stale latest
來宣稱 live。

## 9. 官方使用限制

依元大官方使用限制頁：
- 單連線不同 FunctionID 總訂閱商品上限：2000。
- 同 FunctionID單次商品上限：200。
- 同 FunctionID每秒訂閱呼叫：10。
- 單帳號總訂閱商品：3000。
- 單帳號同時連線：10。
- 行情類不同FunctionID總呼叫：1200次/分鐘。

MARKET_AI_HUB正常運作不得接近上限；目前預設只訂閱模型必要的最小集合。

來源：
https://www.yuanta.com.tw/file-repository/content/0918_TEST/1.%E5%89%8D%E8%A8%80/3.%E4%BD%BF%E7%94%A8%E9%99%90%E5%88%B6%E8%AA%AA%E6%98%8E/index.html

## 10. AI 修改規則

任何新 agent：
1. 不得憑聊天記憶寫商品碼。
2. 先讀 source manifest + FunctionList。
3. 先判斷 venue session。
4. 先用 resolver產生候選。
5. 只有 exact-match callback才可升級 provider capability。
6. measured code只能進 evidence，不得寫成永久常數。
7. order API code不得進 quote subscription。
8. unknown/failure必須 fail-closed。
