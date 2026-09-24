# YUANTA FUTURES LIVE QUOTE CAPABILITY PROBE

- **HEAD**: `f3c58d44856279340e8af17f09b5e235781a7c98` (main) → see merge commit
- **build_id**: `1c928fcba2a5c36a` → (see merge commit; runtime source changed)
- **V2-A**: `2A.2`
- **Scope**: quote-only. NO order / account query / position / balance / recorder / auto retry.
  No V2-H work here; no order/trading capability added.

## A. Verified results (actual, upper-layer verified 2026-09-24)

```
Legacy Quote ReqType=1 (T):    Status=2 LogonOK code=0
Legacy Quote ReqType=2 (T+1):  Status=2 LogonOK code=0
=> LEGACY_FUTURES_AUTH = VERIFIED

Legacy domestic registration (TMFJ6PM, ReqType=2):
  AddMktReg return=0
  OnRegError ErrCode=3        <- 意義 UNKNOWN（不推測、不 brute-force UpdateMode/SetMap）
=> LEGACY_DOMESTIC_QUOTE = AUTH_VERIFIED_REGISTRATION_UNRESOLVED

SPARK Futures (historical server result): 0112
=> SPARK_FUTURES = EXTERNAL_ENTITLEMENT_RETEST_REQUIRED
   （需重新收到 server callback 才可改判；本次不重試）

OSE Micro: MarketNo=207, nearest StkCode=JNU2612  => NOT_AVAILABLE（無 live callback）
TAIFEX live:                                      => NOT_AVAILABLE_UNTIL_CALLBACK
```

**登入成功 != 行情成功。** ErrCode=3 只記錄，不推論原因。

## B. Preflight (kept from previous run)

```
scripts\check_yuanta_futures_com.ps1 : bitness 32, pywin32 ok, OCX v2.1.2.9, STA smoke SMOKE_OK,
                                       RESULT: READY_FOR_AUTH
spark_runtime_probe                  : pythonnet 3.1.0 / .NET 8.0.28 / package 2.2026.0918.0 /
                                       interop READY / prod=2 uat=1 OSE=207
OrderApiExposureGuard                : PASS (findings [])
```

## C. WinCred secret normalization (new)

`credential_store.normalize_credential_secret(value) -> str`:
- `str` → as-is; `bytes/bytearray` → UTF-16LE decode + strip trailing NUL;
- odd byte length / invalid UTF-16LE / unsupported type → `CredentialBackendError` (fail closed);
- never logged, printed, or written to disk. `read_profile_password(profile)` wraps it (None = not preset).

Login wiring:
```
Legacy COM : user = legacy_login_id.username ; password = normalized futures secret
SPARK      : user = <profile> credential.username ; password = normalized <profile> secret
both       : getpass fallback kept when WinCred secret is absent
```
(Measured: `QROS/Yuanta/FuturesReadonly` secret is `bytes` len 16 = UTF-16LE; `MARKET_AI_HUB/YUANTA/LEGACY_LOGIN_ID` holds the login ID.)

## D. Legacy commodity-code source of truth (new)

`easwin_resolver.LegacyEasyWinResolver` — read-only parser of
`C:\Yuanta\yeswin\AGENT\YSTrader\Data\List\M.TFX.TXT` (cp950 CSV). It exists locally and contains
`TMFJ6 / TMFJ6PM / TXFJ6 / TXFJ6PM / MXFJ6 / MXFJ6PM`.

```
day symbols: TMFJ6, TXFJ6, MXFJ6 (…)
PM  symbols: TMFJ6PM, TXFJ6PM, MXFJ6PM (…)
resolve_quote_symbol("TMF", "T")   -> TMFJ6      (day, expiry from file)
resolve_quote_symbol("TMF", "T+1") -> TMFJ6PM    (after-hours)
resolve_quote_symbol("TX"/"MTX", …) -> TXFJ6* / MXFJ6*
selection is as-of aware (uses the file's expiry column; no hardcoded month)
```

Three namespaces are modeled separately and never mixed:
```
SPARK            : SPARK StkCode (resolver.py; e.g. JNU2612)
LEGACY_EASYWIN   : EasyWin quote symbol (easwin_resolver.py; e.g. TMFJ6 / TMFJ6PM)
TRADING_ORDER    : order code (e.g. TMF, JNU) - not a quote code
is_legacy_symbol("JNU2612") = False   # OSE is not in the legacy domestic list
```

## E. Legacy AddMktReg session wiring (fixed)

`AddMktReg(symbol, updmode, ReqType, SetMap)` — ReqType `1=T`, `2=T+1`.
`futures_quote_probe` now takes `--session {T,TPLUS1}` and passes the matching ReqType instead of a
hardcoded `1`; the result artifact records `session`, `req_type`, `AddMktReg_return`, `reg_errors`
(with `reg_error_codes` preserved verbatim) and a `quote_status` of
`LIVE_CALLBACK_VERIFIED` / `AUTH_VERIFIED_REGISTRATION_UNRESOLVED` / `NO_CALLBACK`.
No repeated login, no UpdateMode/SetMap brute force.

## F. SPARK (unchanged architecture)

`spark_futures_quote_probe` remains the bounded probe (single login, ≤10 s per symbol,
SubscribeWatchlist → callbacks → UnSubscribeWatchlist). SPARK Futures stays
`EXTERNAL_ENTITLEMENT_RETEST_REQUIRED` until a fresh server callback supersedes the historical 0112.
OSE Micro resolves to `JNU2612` (MarketNo 207) but is not marked live.

Timestamp quality contract unchanged: `TYuantaTime` carries time-of-day only (no date) →
`SOURCE_TIME_OF_DAY_ONLY`, else `LOCAL_RECEIVE_TIME_ONLY` with `event_timestamp=UNKNOWN`.
No fabricated exchange timestamp.

## G. Machine-readable provider status

```
legacy_futures_auth       : VERIFIED
legacy_domestic_quote     : AUTH_VERIFIED_REGISTRATION_UNRESOLVED
spark_futures             : EXTERNAL_ENTITLEMENT_RETEST_REQUIRED
ose_micro_live            : NOT_AVAILABLE
taifex_live               : NOT_AVAILABLE_UNTIL_CALLBACK
```
Exposed as `integrations.yuanta.capabilities.PROVIDER_STATUS` and mirrored in `config/capabilities.yaml`.

## H. Changed files

```
ADD src/market_ai_hub/integrations/yuanta/easwin_resolver.py
ADD tests/test_phase2yg3_yuanta_secret_and_easwin.py
MOD src/market_ai_hub/integrations/yuanta/credential_store.py   (normalize + read_profile_password)
MOD src/market_ai_hub/integrations/yuanta/futures_auth_probe.py (login_id + futures secret)
MOD src/market_ai_hub/integrations/yuanta/futures_quote_probe.py(session ReqType + secret + reg evidence)
MOD src/market_ai_hub/integrations/yuanta/auth_probe.py         (normalized profile secret)
MOD src/market_ai_hub/integrations/yuanta/capabilities.py       (PROVIDER_STATUS)
MOD config/capabilities.yaml
MOD tests/test_challengers_2d1.py / test_research.py / test_tournament.py (build_id)
MOD research/phase3/reports/YUANTA_FUTURES_LIVE_QUOTE_CAPABILITY_PROBE.md
```

## I. Tests

```
tests/test_phase2yg3_yuanta_secret_and_easwin.py: 20 passed
Yuanta group: see regression section of the merge PR
full suite: see regression section of the merge PR
```
Coverage: UTF-16LE decode / trailing-NUL strip / fail-closed odd length & wrong type / non-mutation;
legacy login = login_id + futures secret (getpass fallback kept); SPARK = normalized profile secret;
ReqType follows session and no longer hardcoded; ErrCode not interpreted; EasyWin day/PM separation,
as-of-aware selection, unknown order code → None; SPARK/Legacy namespace separation; provider status.

## J. Safety

```
order API: NO          orders: NO            account query: NO
position/balance: NO   recorder: NO          auto retry: NO
password persisted: NO (WinCred read + getpass only; never logged/printed/written)
V2-H: NOT_STARTED      Yuanta architecture: NOT redesigned
```

STOPPED AFTER YUANTA FUTURES SECRET/EASYWIN NORMALIZATION.
NO TRADING / NO ORDER / NO RECORDER.
