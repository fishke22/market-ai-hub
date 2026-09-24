"""Yuanta SPARK quote probe（quote-only，單次 login，bounded，per-profile）。

官方 SPARK API 同時支援 securities 與 futures 市場（依官方文件：SubscribeWatchlist /
SubscribeWatchlistAll 的 LoginAcno 可為 securities 或 futures 帳號；enumMarketType TAIFEX=3 /
CME=203 / OSE=207）。**API_SUPPORT != ACCOUNT_ENTITLEMENT**：能否訂閱仍取決於帳號權限。

用法：
  python -m market_ai_hub.integrations.yuanta.spark_futures_quote_probe --profile securities
  python -m market_ai_hub.integrations.yuanta.spark_futures_quote_probe --profile futures

規則：
- 每次執行只做 **一次** Login；0112/0102 → 立即停止（不 retry / 不 brute-force）。
- 只訂閱單一商品、每個最多 10 秒；收到 callback 即 UnSubscribe。不建長期 stream / recorder。
- 三個層次分開記錄：LOGIN_ACCEPTED / SUBSCRIPTION_ACCEPTED / LIVE_CALLBACK_RECEIVED。
- 安全：無 order / account query / position / balance；不列印 secret。

方法簽名取自實裝 DLL（YuantaOneAPI.YuantaSparkAPITrader）：
  SubscribeWatchlistAll(login_acno, List<WatchlistAll>, enumLangType)
  SubscribeWatchlist(login_acno, List<Watchlist>, enumLangType)
  WatchlistAll{MarketType enumMarketType, StockCode String}
"""
from __future__ import annotations

import argparse
import getpass
import json
import time
from datetime import datetime, timezone

from market_ai_hub.integrations.yuanta.credential_store import (
    CredentialBackendError,
    read_profile_credential,
    read_profile_password,
)
from market_ai_hub.integrations.yuanta.resolver import YuantaInstrumentResolver
from market_ai_hub.integrations.yuanta.sanitizer import mask_account
from market_ai_hub.integrations.yuanta.spark_runtime import MSG_SUCCESS, SparkRuntime

RESULT_PATH = "YUANTA_SPARK_QUOTE_PROBE_RESULT.json"

MAX_SUBSCRIBE_SECONDS = 10.0
ABORT_CODES = ("0112", "0102")

# classification
LIVE_CALLBACK_VERIFIED = "LIVE_CALLBACK_VERIFIED"
SUBSCRIPTION_ACCEPTED_NO_CALLBACK = "SUBSCRIPTION_ACCEPTED_NO_CALLBACK"
ACCOUNT_NOT_ENTITLED = "ACCOUNT_NOT_ENTITLED"
LOGIN_NOT_ENTITLED = "LOGIN_NOT_ENTITLED"
SERVER_REJECTED = "SERVER_REJECTED"
TIMEOUT = "TIMEOUT"
ERROR = "ERROR"
NOT_TESTED = "NOT_TESTED"

# timestamp quality（不得 fabricated exchange timestamp）
TS_SOURCE_TIME_OF_DAY = "SOURCE_TIME_OF_DAY_ONLY"
TS_LOCAL_RECEIVE_ONLY = "LOCAL_RECEIVE_TIME_ONLY"


def _security_precheck() -> int:
    from market_ai_hub.integrations.yuanta.order_api_guard import OrderApiExposureGuard

    if OrderApiExposureGuard().scan()["gate"] != "PASS":
        print("ABORT BEFORE LOGIN: order API exposure guard FAIL")
        return 1
    return 0


def _is_success(code: str | None) -> bool:
    return code in (MSG_SUCCESS, "00001")


def _extract_quote(obj) -> dict | None:
    """Sanitized quote callback extraction (real field names from the installed DLL)."""
    try:
        code = getattr(obj, "StkCode", None)
        if code is None:
            return None
        out = {
            "market_no": int(getattr(obj, "MarketType")) if getattr(obj, "MarketType", None) is not None else None,
            "instrument_code": str(code),
            "index_flag": int(getattr(obj, "IndexFlag")) if getattr(obj, "IndexFlag", None) is not None else None,
        }
        v = getattr(obj, "Value", None)
        if v is not None:
            out["value"] = float(v)
        tv = getattr(obj, "IndexFlag_29", None)
        if tv is not None:
            t = getattr(tv, "Time", None)
            if t is not None:
                out["source_time_of_day"] = "%02d:%02d:%02d.%03d" % (
                    int(getattr(t, "bytHour", 0) or 0), int(getattr(t, "bytMin", 0) or 0),
                    int(getattr(t, "bytSec", 0) or 0), int(getattr(t, "ushtMSec", 0) or 0))
            d = getattr(tv, "Deal", None)
            if d is not None:
                out["deal"] = float(d)
            for f in ("TotalVol", "Vol", "TotalInVol", "TotalOutVol"):
                x = getattr(tv, f, None)
                if x is not None:
                    out[f.lower()] = int(x)
        return out
    except Exception:
        return None


def _probe_subscription(rt: SparkRuntime, login_acno: str, market_no: int, stk_code: str,
                        seconds: float, method: str) -> dict:
    """單一商品短訂閱：Subscribe* → bounded wait → UnSubscribe*。"""
    from System.Collections.Generic import List as NetList
    from YuantaOneAPI import Watchlist, WatchlistAll, enumLangType, enumMarketType

    received: list[dict] = []
    rt.on_quote_callback = lambda intMark, strIndex, objValue: received.append(
        {"callback_type": strIndex, "int_mark": intMark, "payload": _extract_quote(objValue)})

    evidence: dict = {"market_no": market_no, "instrument": stk_code, "subscription_method": method}
    try:
        if method == "watchlist_all":
            item = WatchlistAll()
            item.MarketType = enumMarketType(market_no)
            item.StockCode = stk_code
            lst = NetList[WatchlistAll]()
            lst.Add(item)
            subscribe = lambda: rt._api.SubscribeWatchlistAll(login_acno, lst, enumLangType.UTF8)
            unsubscribe = lambda: rt._api.UnSubscribeWatchlistAll(login_acno, lst, enumLangType.UTF8)
        else:
            item = Watchlist()
            item.MarketType = enumMarketType(market_no)
            item.StockCode = stk_code
            flag = rt.enum_quote_index_default()
            if flag is not None:
                try:
                    item.IndexFlag = flag
                except Exception:
                    pass
            lst = NetList[Watchlist]()
            lst.Add(item)
            subscribe = lambda: rt._api.SubscribeWatchlist(login_acno, lst, enumLangType.UTF8)
            unsubscribe = lambda: rt._api.UnSubscribeWatchlist(login_acno, lst, enumLangType.UTF8)
        try:
            ret = subscribe()
            evidence["method_return"] = (None if ret is None else bool(ret))
            evidence["subscription_called"] = True
        except Exception as e:
            evidence["subscription_called"] = False
            evidence["method_return"] = None
            evidence["subscription_error"] = f"{type(e).__name__}: {str(e)[:150]}"
            return evidence
    except Exception as e:  # type/interop unavailable
        evidence["subscription_called"] = False
        evidence["subscription_error"] = f"{type(e).__name__}: {str(e)[:150]}"
        return evidence

    deadline = time.time() + seconds
    while time.time() < deadline and not any(r["payload"] for r in received):
        rt.pump(0.2)
    try:
        unsubscribe()
        evidence["unsubscribed"] = True
    except Exception:
        evidence["unsubscribed"] = False
    rt.on_quote_callback = None

    quotes = [r for r in received if r["payload"]]
    evidence["callback_count"] = len(quotes)
    evidence["callback_types"] = sorted({str(r["callback_type"]) for r in received})
    if quotes:
        q = quotes[0]
        ev = dict(q["payload"])
        ev["callback_type"] = q["callback_type"]
        ev["received_at"] = datetime.now(timezone.utc).isoformat()
        ev["timestamp_quality"] = (TS_SOURCE_TIME_OF_DAY if "source_time_of_day" in ev
                                   else TS_LOCAL_RECEIVE_ONLY)
        if "source_time_of_day" not in ev:
            ev["event_timestamp"] = "UNKNOWN"
        evidence["first_callback"] = ev
        evidence["classification"] = LIVE_CALLBACK_VERIFIED
    elif evidence.get("subscription_called"):
        evidence["classification"] = SUBSCRIPTION_ACCEPTED_NO_CALLBACK
    else:
        evidence["classification"] = ERROR
    return evidence


def main() -> int:
    ap = argparse.ArgumentParser(prog="yuanta.spark_futures_quote_probe")
    ap.add_argument("--profile", choices=["securities", "futures"], default="securities")
    ap.add_argument("--method", choices=["watchlist_all", "watchlist"], default="watchlist_all",
                    help="官方優先 SubscribeWatchlistAll；型別不可用時可選 SubscribeWatchlist")
    ap.add_argument("--seconds", type=float, default=MAX_SUBSCRIBE_SECONDS)
    args = ap.parse_args()

    if _security_precheck() != 0:
        return 1

    try:
        cred = read_profile_credential(args.profile)
    except CredentialBackendError as e:
        print(f"UNAVAILABLE: {e}")
        return 1
    if cred is None:
        print(f"no {args.profile} account preset in Windows Credential Manager.")
        account = input(f"Enter {args.profile} account: ").strip()
    else:
        account = cred.username

    r = YuantaInstrumentResolver()
    tfx = r.resolve("TAIFEX_TMF")
    ose = r.resolve("OSE_NIKKEI225_MICRO_FUTURES")

    print("Profile:", args.profile, "| Account:", mask_account(account),
          "| Orders: DISABLED | Mode: QUOTE_ONLY | Method:", args.method)
    print("TAIFEX target:", tfx.market_type, tfx.spark_code, "verified=", tfx.verified)
    print("OSE target   :", ose.market_type, ose.spark_code, "verified=", ose.verified)

    password = read_profile_password(args.profile)
    if not password:
        password = getpass.getpass(f"Yuanta {args.profile} password: ")
        print("password source: getpass (WinCred secret not preset)")
    else:
        print("password source: Windows Credential Manager (normalized)")

    rt = SparkRuntime()
    outcome = None
    result: dict = {
        "api_family": "SPARK", "mode": "QUOTE_ONLY", "orders": "DISABLED",
        "account_profile": args.profile, "account_masked": mask_account(account),
        "environment": "PROD", "subscription_method": args.method,
        "levels": {"LOGIN_ACCEPTED": False, "SUBSCRIPTION_ACCEPTED": False,
                   "LIVE_CALLBACK_RECEIVED": False},
        "login": None, "quote_probes": [],
        "verified_at": datetime.now(timezone.utc).isoformat(), "security": "PASS",
    }
    try:
        rt.instantiate()
        rt.open_prod()
        rt.wait_connected(timeout=15.0)
        time.sleep(1)
        rt.login(account, password)   # bool accepted only; real result via OnResponse
        outcome = rt.wait_login(timeout=25.0)
    except Exception as e:
        print("LOGIN_FAILED: interop error:", type(e).__name__, str(e)[:200])
        result["login"] = {"status": ERROR, "error": f"{type(e).__name__}: {str(e)[:150]}"}
    finally:
        del password

    if outcome is None or not outcome.received:
        print("LOGIN: TIMEOUT (no OnResponse within timeout)")
        result["login"] = result["login"] or {"status": TIMEOUT, "msg_code": None}
        rt.cleanup()
        _write_result(result)
        return 1

    code = outcome.msg_code
    if _is_success(code):
        result["login"] = {"status": "LOGIN_ACCEPTED", "msg_code": code}
        result["levels"]["LOGIN_ACCEPTED"] = True
        print("LOGIN: ACCEPTED | MsgCode:", code)
    elif code in ABORT_CODES:
        status = ACCOUNT_NOT_ENTITLED if code == "0112" else LOGIN_NOT_ENTITLED
        result["login"] = {"status": status, "msg_code": code}
        print("LOGIN:", status, "| MsgCode:", code, "(stop, no retry)")
        rt.cleanup()
        _write_result(result)
        return 1
    else:
        result["login"] = {"status": SERVER_REJECTED, "msg_code": code}
        print("LOGIN: SERVER_REJECTED | MsgCode:", code)
        rt.cleanup()
        _write_result(result)
        return 1

    # quote probes (only after confirmed login) — one login, bounded, no retry
    try:
        for inst in (tfx, ose):
            if not inst.verified:
                result["quote_probes"].append({
                    "market_no": inst.market_type, "instrument": "",
                    "classification": NOT_TESTED, "note": "instrument unresolved"})
                continue
            probe = _probe_subscription(rt, account, inst.market_type, inst.spark_code,
                                        args.seconds, args.method)
            probe["logical"] = inst.logical_instrument
            result["quote_probes"].append(probe)
            if probe.get("classification") == LIVE_CALLBACK_VERIFIED:
                result["levels"]["LIVE_CALLBACK_RECEIVED"] = True
            if probe.get("subscription_called"):
                result["levels"]["SUBSCRIPTION_ACCEPTED"] = True
        result["callbacks"] = rt.callback_diagnostics()[:20]
    finally:
        rt.cleanup()
    _write_result(result)
    return 0


def _write_result(result: dict) -> None:
    with open(RESULT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print(f"result written -> {RESULT_PATH}")


if __name__ == "__main__":
    raise SystemExit(main())
