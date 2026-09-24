# YUANTA FUTURES LIVE QUOTE CAPABILITY PROBE

- **HEAD**: `21b432d8d6bd7ed39d35445f91513656da74d4a0` (main) → see merge commit
- **build_id**: `8e36a4802965ef2d` → `1c928fcba2a5c36a`
- **V2-A**: `2A.2` · working tree clean at start
- **Scope**: quote-only capability probe. NO order / account query / position / balance / recorder /
  auto retry / V2-H. No runtime wiring (analysis.cross_market / factor router / packet untouched).

## A. Baseline
```
STARTING_HEAD:   21b432d8d6bd7ed39d35445f91513656da74d4a0
BUILD_ID_BEFORE: 8e36a4802965ef2d   (V2-A 2A.2)
BUILD_ID_AFTER:  1c928fcba2a5c36a   (probe fixes changed runtime source)
```

## B. Preflight (actual results)

```
scripts\check_yuanta_futures_com.ps1:
  bitness: 32 (expect 32)
  comtypes/pywin32: ok
  OCX InprocServer32: C:\Yuanta\QAPI\YuantaQuote_v2.1.2.9.ocx
  sidecar import: ok
  STA/ActiveX/event-sink smoke: SMOKE_OK
  RESULT: READY_FOR_AUTH

python -m market_ai_hub.integrations.yuanta.spark_runtime_probe:
  python 3.12.13 / 64bit / pythonnet 3.1.0 / .NET 8.0.28
  spark_package_version 2.2026.0918.0
  interop_status READY
  enums: prod=2, uat=1, market_ose=207
  written -> YUANTA_INTEROP_DIAGNOSTIC.json (gitignored)

OrderApiExposureGuard().scan() -> {"gate": "PASS", "findings": []}
```

## C. Confirmed fixes

**A. `futures_quote_probe.py` login identity (fixed)**
- BEFORE: read `read_profile_credential("futures")` and passed that (期貨帳號) as `SetMktLogon` 第一參數.
- AFTER: reads `read_profile_credential("legacy_login_id")` (登入ID) exactly like `futures_auth_probe.py`;
  also added `OrderApiExposureGuard` precheck and a **DOMESTIC_ONLY** guard that refuses OSE/JNU symbols
  (`_is_domestic_symbol("TMFJ6")=True`, `_is_domestic_symbol("JNU2612")=False`).

**B. `resolver.py` OSE resolution (fixed)**
- BEFORE: any `OSE_*` logical instrument returned `verified=False, spark_code=""`
  ("OSE StkCode not present in FunctionList").
- AFTER: authoritative resolution from the vendored
  `FunctionList.xlsx 股票代碼總表` (讀 `市場別|市場代碼|商品代碼|商品名稱|下單代碼`), with
  `config/yuanta_product_codes.yaml` as the documented ground truth:
  - OSE MarketNo = **207**; Micro 報價碼 = `JNU<YYMM>`; **下單代碼 `JNU` ≠ 報價碼**
  - Mini = `19<YYMM>`; Large = `18<YYMM>`
  - TAIFEX (3) 國內指數期貨 = `TXF/MXF/TMF` + 月字母(A-L) + 年末位
  - contract selection is **as-of dependent** via documented expiry rules
    (OSE: business day before the 2nd Friday; TAIFEX: 3rd Wednesday) — no expired month hardcoded.
  - FunctionList unavailable → fail closed (`verified=False`, no guess).

Actual resolution at as-of 2026-09-24 (JNU2609 expired 2026-09-10, TXFI6/TMFI6 expired 2026-09-16):
```
OSE_NIKKEI225_MICRO_FUTURES market=207 code=JNU2612 verified=True  (order code JNU)
OSE_NIKKEI225_MINI_FUTURES  market=207 code=192612 verified=True
OSE_NIKKEI225_LARGE_FUTURES market=207 code=182612 verified=True
TAIFEX_TX   market=3 code=TXFJ6 verified=True
TAIFEX_MTX  market=3 code=MXFJ6 verified=True
TAIFEX_TMF  market=3 code=TMFJ6 verified=True
```

## D. Legacy Quote COM — T / T+1 (BLOCKED, not run)

`scripts\yuanta_futures_auth.ps1` prompts for the password through `getpass` on the local console.
This agent cannot enter a password (must not be pasted into chat / env / command line / log) and will
not attempt a login with an empty password. **No login was attempted; no result is inferred.**

```
LEGACY_T_AUTH:      NOT_TESTED
LEGACY_TPLUS1_AUTH: NOT_TESTED
reason: interactive getpass password required (local operator)
next safe action (user, locally):
  scripts\yuanta_futures_auth.ps1
  -> report ReqType / Status / message_code / classification per T and T+1
```

## E. Legacy domestic quote (NOT_TESTED)

Depends on D. Per contract the legacy COM is **DOMESTIC_ONLY**; the JNU symbol must never be used here.
After a verified domestic symbol exists locally (resolver: `TAIFEX_TMF -> TMFJ6`), run:

```
scripts\yuanta_futures_quote_probe.ps1 --symbol TMFJ6     (or)
.venv-yuanta-futures-x86\Scripts\python.exe -m market_ai_hub.integrations.yuanta.futures_quote_probe --symbol TMFJ6
```
Result artifact: `YUANTA_FUTURES_QUOTE_RESULT.json` (AddMktReg → callbacks → DelMktReg, ≤ 8–10 s).

```
LEGACY_DOMESTIC_QUOTE: NOT_TESTED
```

## F. SPARK Futures login (BLOCKED, not run)

`python -m market_ai_hub.integrations.yuanta.auth_probe --profile futures` also prompts via `getpass`.
Account presets exist in Windows Credential Manager (futures `FF…06`; securities `S9…15`), but the
password is operator-entered only.

```
SPARK_FUTURES_AUTH: NOT_TESTED  (blocked on local getpass)
MsgCode:            NOT_OBSERVED
next safe action (user, locally):
  python -m market_ai_hub.integrations.yuanta.auth_probe --profile futures
  -> 0112 => SPARK_FUTURES_NOT_ENTITLED (stop, no retry)
  -> 0102 => stop
  -> 0001/00001 => proceed to quote probe
```

## G. SPARK quote probe (module built, NOT_TESTED)

New `spark_futures_quote_probe.py` (single login, quote-only, bounded ≤10 s per symbol, immediate
UnSubscribe, no stream/recorder). Methods/signatures taken from the installed DLL reflection
(`YuantaOneAPI.YuantaSparkAPITrader`), not guessed:

```
SubscribeWatchlist(login_acno, List<Watchlist>, enumLangType)
UnSubscribeWatchlist(login_acno, List<Watchlist>, enumLangType)
Watchlist{ MarketType enumMarketType, StockCode String, IndexFlag enumQuoteIndexType }
GetQuoteList(account) / GetQuoteListSync(account)   (available, not used)
```

Quote payload (real fields): `WatchListResult{Key, MarketType, StkCode, IndexFlag, Value}` and
`WatchListAllResult{… IndexFlag_22(買賣量), IndexFlag_28(買賣價), IndexFlag_29{Time TYuantaTime{bytHour,bytMin,bytSec,ushtMSec}, Deal, Vol, TotalVol, TotalInVol, TotalOutVol}}`.
It probes (A) OSE Micro `JNU2612` (MarketNo 207) and (B) the nearest domestic index future
`TMFJ6` (market 3).

```
SPARK_TAIFEX_QUOTE:   NOT_TESTED (depends on F)
SPARK_OSE_MICRO_QUOTE: NOT_TESTED (depends on F)
```

**Timestamp quality contract (for the future wiring):** `TYuantaTime` carries **time-of-day only**
(HH:MM:SS.mmm, no date) → when a callback carries it the probe records
`timestamp_quality = SOURCE_TIME_OF_DAY_ONLY`; otherwise `LOCAL_RECEIVE_TIME_ONLY` with
`event_timestamp = UNKNOWN`. No exchange timestamp is fabricated.

## H. Readiness classification (actual)

```
LEGACY_T_AUTH          NOT_TESTED
LEGACY_TPLUS1_AUTH     NOT_TESTED
LEGACY_DOMESTIC_QUOTE  NOT_TESTED
SPARK_FUTURES_AUTH     NOT_TESTED
SPARK_TAIFEX_QUOTE     NOT_TESTED
SPARK_OSE_MICRO_QUOTE  NOT_TESTED
LIVE_CALLBACK_VERIFIED not claimed (no quote callback was received; none is inferred)
```

## I. Changed files

```
ADD src/market_ai_hub/integrations/yuanta/spark_futures_quote_probe.py
ADD tests/test_phase2yg2_yuanta_contract_resolution.py
ADD research/phase3/reports/YUANTA_FUTURES_LIVE_QUOTE_CAPABILITY_PROBE.md
MOD src/market_ai_hub/integrations/yuanta/resolver.py           (authoritative OSE/TAIFEX resolution)
MOD src/market_ai_hub/integrations/yuanta/function_list.py      (generic stock-code row loader)
MOD src/market_ai_hub/integrations/yuanta/futures_quote_probe.py(legacy_login_id + DOMESTIC_ONLY)
MOD src/market_ai_hub/integrations/yuanta/spark_runtime.py      (quote callback hook + pump + enum)
MOD tests/test_phase2ya.py / test_phase2yb.py                   (resolver now verified, fail-closed guard)
MOD tests/test_challengers_2d1.py / test_research.py / test_tournament.py (build_id)
```

## J. Tests

```
Yuanta group (2Y-A..2Y-H + 2Y-G.2): 153 passed
tests/test_v2a2_session_truth.py + test_v2a2_factor_routing.py: 60 passed
full suite: 1549 passed, 20 deselected, 144 warnings
```

New coverage: OSE/TAIFEX expiry rules, nearest-contract selection (expired skipped, as-of dependent,
all-expired → None, PM variants ignored), JNU<YYMM> pattern, quote code ≠ order code, domestic-only
guard, legacy login-id wiring.

## K. Safety

```
order API: NO          orders: NO            account query: NO
position/balance: NO   recorder: NO          auto retry: NO
password persisted: NO (getpass only, process memory)
V2-H: NOT_STARTED      runtime wiring: NO
```

STOPPED AFTER YUANTA FUTURES LIVE QUOTE CAPABILITY PROBE.
NO TRADING / NO ORDER / NO RECORDER.
V2-H NOT STARTED.
