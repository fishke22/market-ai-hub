# YUANTA SPARK — securities/futures quote probe

Date: 2026-09-24 (UTC 13:2x) · API family: **SPARK** (`YuantaSparkAPITrader`) · Mode: **QUOTE_ONLY**
Orders: **DISABLED** · Exposure guard: **PASS** (checked before login) · Result JSON: `YUANTA_SPARK_QUOTE_PROBE_RESULT.json`

## 1. Official-contract correction (durable handoff)

SPARK 官方 API 支援 **securities 與 futures 兩種市場**（`SubscribeWatchlist` /
`SubscribeWatchlistAll` 的 `LoginAcno` 可為 securities 或 futures 帳號；`enumMarketType`
TAIFEX=3 / CME=203 / OSE=207）。舊敘述 `SPARK = securities only` 不正確，已從 handoff 移除。

```text
SPARK API supports securities + futures markets by official contract.
API_SUPPORT != ACCOUNT_ENTITLEMENT.
```

- Legacy **FUTURES QUOTE**（`YUANTAQUOTE.YuantaQuoteCtrl.1`）仍是獨立 API，未混用。
- `FUTURES TRADING`（`Yuanta.YuantaOrdCtrl.1`）未連接，NO ORDER。

## 2. 三個層次必須分開（本次實測）

| Layer | Measured |
|---|---|
| `LOGIN_ACCEPTED` | **True** — profile `securities`，`MsgCode=0001`（帳號 `S9********15`，secret 來自 WinCred normalized，未列印） |
| `SUBSCRIPTION_ACCEPTED` | **True** — TAIFEX 與 OSE 訂閱呼叫皆被接受（無例外、無 server 拒絕） |
| `LIVE_CALLBACK_RECEIVED` | **False** — 10 秒內 0 筆行情 callback |

`bool return` 未被當成行情成功：所有 `Subscribe*` 回傳 `Void`（`method_return=None`），
因此只有 callback 才算行情；本次無 callback。

## 3. 逐商品分類

```text
SPARK_SECURITIES_TAIFEX_QUOTE : SUBSCRIPTION_ACCEPTED_NO_CALLBACK
SPARK_SECURITIES_OSE_QUOTE    : SUBSCRIPTION_ACCEPTED_NO_CALLBACK
SPARK_FUTURES_AUTH            : SPARK_FUTURES_ACCOUNT_ENTITLEMENT_BLOCKED
```

| Item | account_profile | market (no) | instrument | subscription method | method return | callback_count | source time | classification |
|---|---|---|---|---|---|---|---|---|
| TAIFEX | SECURITIES | TAIFEX (3) | `TMFJ6` (resolver verified) | `SubscribeWatchlistAll` | Void → `None` | 0 | — | `SUBSCRIPTION_ACCEPTED_NO_CALLBACK` |
| TAIFEX | SECURITIES | TAIFEX (3) | `TMFJ6` | `SubscribeWatchlist` | Void → `None` | 0 | — | `SUBSCRIPTION_ACCEPTED_NO_CALLBACK` |
| OSE | SECURITIES | OSE (207) | `JNU2612` (resolver verified, nearest valid) | `SubscribeWatchlistAll` | Void → `None` | 0 | — | `SUBSCRIPTION_ACCEPTED_NO_CALLBACK` |
| OSE | SECURITIES | OSE (207) | `JNU2612` | `SubscribeWatchlist` | Void → `None` | 0 | — | `SUBSCRIPTION_ACCEPTED_NO_CALLBACK` |

`OnResponse` 診斷（兩次執行相同）：`{"intMark":0,"strIndex":"","type":"str"}` ×3 +
`{"intMark":1,"strIndex":"Login","type":"LoginResult"}` — **沒有** subscribe 專屬回應或
market 訊息；無 server msg code 可用（因此不宣稱 `SERVER_REJECTED`/`ACCOUNT_NOT_ENTITLED`）。

## 4. Session context（排除「市場沒開」的解釋）

Probe 當下（UTC 13:21 / Taipei 21:21 / Tokyo 22:21），以本專案 V2-A.2 session truth 判讀：

```text
TX / TMF : venue=TAIFEX_DERIVATIVES  session=AFTER_HOURS_SESSION  market_open=True
OSE 夜盤  : Tokyo 22:21 屬於 OSE 夜間時段（17:00–06:00）
```

兩個市場皆在交易時段內，卻在 10 秒內無 callback → 無 callback **不能**歸因於休市。

## 5. Futures profile 重測（僅一次）

`auth_probe --profile futures`（帳號 `FF**************06`）→

```text
ABORT: API_PERMISSION_UNAVAILABLE      (0112 = 無此權限使用功能)
SPARK_FUTURES_ACCOUNT_ENTITLEMENT_BLOCKED
```

一次即停，**未 retry、未 brute-force**。

## 6. 與其他 Yuanta API family 的關係

```text
SPARK_SECURITIES_*  : 本次新增實測（帳號型別＝SECURITIES，市場＝TAIFEX / OSE）
SPARK_FUTURES_*     : 0112 entitlement blocked（futures 帳號型別）
LEGACY FUTURES AUTH : VERIFIED（ReqType=1/2 Status=2 LogonOK code=0）
LEGACY DOMESTIC QUOTE: AUTH_VERIFIED_REGISTRATION_UNRESOLVED（ErrCode=3 UNKNOWN，未臆測）
```

`ose_micro_live` / `taifex_live` 仍為 `NOT_AVAILABLE` / `NOT_AVAILABLE_UNTIL_CALLBACK`：
subscription accepted 但 **無 callback**，行情仍不可用。

## 7. 邊界與未做

- NO order / NO trading / NO position / NO balance query；NO recorder / NO 長期 stream。
- NO auto retry / brute-force；每次執行只登入一次（本次共 3 次執行：watchlist_all、watchlist、futures auth）。
- 未列印或保存 secret；只保存 profile、masked account、market、instrument、method、callback 統計。
- OSE callback 是否因海外市場即時行情需額外授權而缺失 → **未證實**，不臆測；需 operator 端確認
  entitlement 或換授權等級後再測（`NOT_TESTED` 的部分保持 `NOT_TESTED`）。

## 8. Gate

```text
YUANTA_SPARK_SECURITIES_FUTURES_QUOTE_PROBE_COMPLETE
```

定義：已完成真實 probe（非 mock）＋三個層次分開記錄＋誠實分類。**不要求 callback 成功。**
