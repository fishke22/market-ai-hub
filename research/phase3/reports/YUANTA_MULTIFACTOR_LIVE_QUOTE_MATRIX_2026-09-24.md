# 元大多因子即時行情能力矩陣 — 2026-09-24

## A. 測試目的
以相同的 MARKET_AI_HUB 經濟因子集合，分別驗證：
- SPARK（使用已可登入的 securities profile）
- Legacy Futures Quote / YuantaQuote COM

只有收到與「要求的 market + instrument」完全相符的 callback 才算成功。
全程 QUOTE_ONLY；NO ORDER / NO account query / NO recorder。

## B. 起始環境
- repo baseline：main `d6490595b774e91024a43741dac046cdcf1eb684`
- V2-I schema：2I.1
- SPARK PROD securities login：MsgCode=0001
- Legacy Quote：T/T+1 Status=2 LogonOK code=0
- OrderApiExposureGuard：PASS

## C. 重要診斷修正
第一次 broad SPARK probe發現晚到 callback可能被下一商品誤收。
修正 `spark_futures_quote_probe._probe_subscription`：
callback 必須同時滿足 `payload.market_no == requested market_no`
及 `payload.instrument_code == requested stock code` 才計入。
重新實測後以下結果仍成立。

## D. SPARK securities profile — 實測

訂閱方法：`SubscribeWatchlistAll`。
每商品 bounded ≤2秒；收到 matching callback 即可退訂。

| Factor | Market | Symbol | Matching callbacks | 結果 |
|---|---:|---|---:|---|
| TW_INDEX | 3 TAIFEX | TMFPMJ6 | 5 | LIVE_CALLBACK_VERIFIED |
| JP_EQUITY | 207 OSE | JNUPM2612 | 8 | LIVE_CALLBACK_VERIFIED |
| US_TECH_RISK | 203 CME | NQ_2612 | 37 | LIVE_CALLBACK_VERIFIED |
| US_TECH_RISK | 203 CME | MNQ2612 | 43 | LIVE_CALLBACK_VERIFIED |
| US_BROAD_RISK | 203 CME | ES_2612 | 17 | LIVE_CALLBACK_VERIFIED |
| US_VOLATILITY | 215 CBOE | VX2610 | 2 | LIVE_CALLBACK_VERIFIED |
| JPY_FX | 203 CME | JY_2612 | 1 | LIVE_CALLBACK_VERIFIED |
| US_RATES_5Y | 204 CBOT | ZF2612 | 14 | LIVE_CALLBACK_VERIFIED |
| US_RATES_10Y | 204 CBOT | ZN2612 | 5 | LIVE_CALLBACK_VERIFIED |
| GOLD | 203 CME | GC2610 | 2 | LIVE_CALLBACK_VERIFIED |
| WTI_OIL | 203 CME | CL2610 | 0 | SUBSCRIPTION_ACCEPTED_NO_CALLBACK |
| WTI_OIL | 203 CME | CL2611 | 5 | LIVE_CALLBACK_VERIFIED |
| USD_BROAD | 209 NYBOT | DOLINDX2612 | 1 | LIVE_CALLBACK_VERIFIED |

TWSE cash測試：`IX0001`與`2330`訂閱呼叫成功但0 callback；測試時TWSE已收盤，
因此不能當作 entitlement failure。

## E. Legacy Futures Quote — 實測

登入方式：
- login ID：operator identity login（實值不得進repo）
- password：Windows Credential Manager 的 securities profile secret
- T/T+1：Status=2 / LogonOK / code=0

T+1，`UpdateMode=4`、`ReqType=2`、`SetMap=0`：

| Factor | Symbol | Result |
|---|---|---|
| TW_INDEX / TX | TXFJ6 | LIVE_CALLBACK_VERIFIED / OnGetMktData |
| TW_INDEX / MTX | MXFJ6 | LIVE_CALLBACK_VERIFIED / OnGetMktData |
| TW_INDEX / TMF | TMFJ6 | LIVE_CALLBACK_VERIFIED / OnGetMktData |
| US_TECH_RISK / TAIFEX UNF | UNFL6 | LIVE_CALLBACK_VERIFIED / OnGetMktData |

海外 actual-contract測試：
`JNU2612,NQ2612,MNQ2612,ES2612,VX2610,JY2612,FV2609,TY2609,GC2610,CL2610`
皆未取得行情，主要為 `OnRegError ErrCode=3`。
有限 alias 測試：`NQ1` return=1/no callback；`JNU1` ErrCode=3。

結論：Legacy Quote目前定位為 **國內 TAIFEX live backup**，海外多因子優先 SPARK。

## F. 語義與路由結論

```text
SPARK securities profile
  -> primary live cross-market provider
  -> TAIFEX / OSE / CME / CBOT / CBOE / NYBOT measured callbacks

Legacy Futures Quote
  -> domestic TAIFEX backup
  -> TX / MTX / TMF / UNF measured callbacks

SPARK futures-account profile
  -> login still 0112
  -> external entitlement issue
  -> NOT a system blocker
```

必須保持 representation identity：
- NQ/MNQ/ES/VX/JY/ZF/ZN/DOLINDX 都是 derivative proxy，不是 cash/spot/yield本體。
- OSE Micro夜盤 callback是 direct target representation。
- Cash closed時不得用上一盤close假裝live。

## G. 未解與限制
- SPARK部分 callback只有 quote flag/local receive time，尚未全部標準化成可靠成交價。
- `TYuantaTime`沒有日期；需V2-A.2 session/trading-date補日期語義。
- Legacy ErrCode=3官方文字定義仍未確認。
- 本次合約碼會到期；不得硬編碼到永久runtime。
- TWSE cash本輪在休市時測試，白天callback能力須另做session-aware驗證。

## H. 永久產物
- `config/yuanta_live_factor_matrix.yaml`：machine-readable measured capability。
- `docs/integrations/yuanta/YUANTA_LIVE_MULTIFACTOR_GUIDE_ZH_TW.md`：繁體中文永久整合指南。
- `docs/development/AGENT_HANDOFF.md`：指向上述兩份source-of-truth。
- `spark_futures_quote_probe.py`：callback exact-match hardening。

## I. Safety
```text
orders: NO
trading: NO
account query: NO
position/balance: NO
recorder: NO
auto retry/bruteforce: NO
secret persisted: NO
```

## J. Gate
```text
YUANTA_MULTIFACTOR_LIVE_QUOTE_MATRIX_VERIFIED
SPARK_SECURITIES_CROSS_MARKET_LIVE_CALLBACK_VERIFIED
LEGACY_TAIFEX_LIVE_CALLBACK_VERIFIED
```

這些 gate只表示行情能力實測，不表示模型有效、機率校準或交易優勢。


## K. 常駐 Quote Hub 驗收

依 operator 要求，已將成功行情來源提升為本機單一登入常駐 Hub：

- 入口：`python -m market_ai_hub.integrations.yuanta.live_quote_recorder`
- 日常啟動：`scripts/start_yuanta_live_recorder.ps1`
- agent 動態追加：`scripts/request_yuanta_quote.ps1 -MarketNo <n> -Symbol <code>`
- 狀態/即時快照：`data/live/yuanta/status.json`、`latest.json`
- 訓練資料：`data/live/yuanta/parquet/YYYY-MM-DD/*.parquet`
- 實際行情資料目錄 `data/live/` 已 gitignore，不進 GitHub。

實測：
- SPARK PROD login MsgCode=0001。
- persistent Hub heartbeat = RUNNING。
- default subscriptions 由最新版 FunctionList 動態解析。
- 同一 PID 下用 control inbox 動態增加 `MES2612` 訂閱，subscriptions 由 54 → 55 並收到 matching callback；證明 agent 不需重新登入。
- start script 在 Hub 已運行時回 `YUANTA_LIVE_ALREADY_RUNNING`，不會建立第二個登入。
- Parquet 分片持續產生；raw JSONL 因容量過大改為預設關閉。
- Windows 使用者 Startup 已配置啟動 `scripts/start_yuanta_live_recorder.ps1`；關機/程序結束才斷線。

## L. 模型學習資料策略

預設長期保存的是公開網路難以完整重建的盤中/微結構資料：
- direct OSE Micro；
- TAIFEX TX/MTX/TMF/UNF；
- NQ/MNQ/ES/VX/JY/ZF/ZN/GC/CL/DXY futures；
- 近月與次近月（roll/basis 學習）；
- 台股現貨交易時段的 TAIEX 與 2330 context；
- 成交價/量、累計量、bid/ask等 callback 可取得欄位、source time-of-day、received_at。

可由公開來源可靠重抓的日線/總經資料不在此重複長期錄製。
