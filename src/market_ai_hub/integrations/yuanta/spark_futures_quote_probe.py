"""Phase 2Y-G.2 — Yuanta SPARK Futures quote_probe CLI（quote-only，單次 login，bounded）。

用法（64-bit .venv，需證券商 API 帳號）：
  python -m market_ai_hub.integrations.yuanta.spark_futures_quote_probe --profile futures

規則：
- 只做一次 Login。MsgCode 0112/0102 → ABORT（不 retry）。0001/00001 → 才進行情 probe。
- 商品：OSE Micro（MarketNo=207，StkCode = resolver 由 FunctionList 選出的有效最近 JNU 合約）
        與一檔國內指數期貨（TAIFEX TX/MTX/TMF，同樣由 resolver 選出）。
- 只訂閱單一商品、每個最多 10 秒；收到 callback 即 UnSubscribe。不建長期 stream / recorder。
- 安全：無 order / account query / position / balance；password 只 process memory。

方法名稱/簽名皆取自實裝 DLL（YuantaOneAPI.YuantaSparkAPITrader）：
  SubscribeWatchlist(login_acno, List<Watchlist>, enumLangType)
  UnSubscribeWatchlist(login_acno, List<Watchlist>, enumLangType)
  Watchlist{ MarketType enumMarketType, StockCode String, IndexFlag enumQuoteIndexType }
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
)
from market_ai_hub.integrations.yuanta.resolver import YuantaInstrumentResolver
from market_ai_hub.integrations.yuanta.sanitizer import mask_account
from market_ai_hub.integrations.yuanta.spark_runtime import MSG_SUCCESS, SparkRuntime

RESULT_PATH = "YUANTA_SPARK_FUTURES_QUOTE_RESULT.json"

MAX_SUBSCRIBE_SECONDS = 10.0
ABORT_CODES = ("0112", "0102")

# timestamp quality（不得 fabricated exchange timestamp）
TS_SOURCE_TIME_OF_DAY = "SOURCE_TIME_OF_DAY_ONLY"   # API 提供交易所時刻但無日期
TS_LOCAL_RECEIVE_ONLY = "LOCAL_RECEIVE_TIME_ONLY"   # 無來源時間戳


def _security_precheck() -> int:
    from market_ai_hub.integrations.yuanta.order_api_guard import OrderApiExposureGuard

    if OrderApiExposureGuard().scan()["gate"] != "PASS":
        print("ABORT BEFORE LOGIN: order API exposure guard FAIL")
        return 1
    return 0


def _is_success(code: str | None) -> bool:
    return code in (MSG_SUCCESS, "00001")


def _extract_quote(obj) -> dict | None:
    """Sanitized quote callback extraction (real field names from installed DLL)."""
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
                        seconds: float) -> dict:
    """單一商品短訂閱：SubscribeWatchlist → wait callbacks → UnSubscribeWatchlist。"""
    from YuantaOneAPI import Watchlist, enumLangType, enumMarketType

    received: list[dict] = []
    rt.on_quote_callback = lambda intMark, strIndex, objValue: received.append(
        {"callback_type": strIndex, "payload": _extract_quote(objValue)})

    wl = Watchlist()
    wl.MarketType = enumMarketType(market_no)
    wl.StockCode = stk_code
    flag = rt.enum_quote_index_default()
    if flag is not None:
        try:
            wl.IndexFlag = flag
        except Exception:
            pass
    lst = [wl]
    evidence: dict = {"market_no": market_no, "instrument_code": stk_code}
    try:
        rt._api.SubscribeWatchlist(login_acno, lst, enumLangType.UTF8)
        evidence["subscription_called"] = True
    except Exception as e:
        evidence["subscription_called"] = False
        evidence["error"] = f"{type(e).__name__}: {str(e)[:150]}"
        return evidence
    deadline = time.time() + seconds
    while time.time() < deadline and not any(r["payload"] for r in received):
        rt.pump(0.2)
    try:
        rt._api.UnSubscribeWatchlist(login_acno, lst, enumLangType.UTF8)
        evidence["unsubscribed"] = True
    except Exception:
        evidence["unsubscribed"] = False
    rt.on_quote_callback = None

    quotes = [r for r in received if r["payload"]]
    evidence["callback_count"] = len(quotes)
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
    return evidence


def main() -> int:
    ap = argparse.ArgumentParser(prog="yuanta.spark_futures_quote_probe")
    ap.add_argument("--profile", choices=["futures"], default="futures")
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
        print("no account preset in Windows Credential Manager.")
        account = input(f"Enter {args.profile} account: ").strip()
    else:
        account = cred.username

    r = YuantaInstrumentResolver()
    ose = r.resolve("OSE_NIKKEI225_MICRO_FUTURES")
    domestic = [r.resolve(name) for name in ("TAIFEX_TMF", "TAIFEX_TX", "TAIFEX_MTX")]
    print("resolved OSE Micro :", ose.market_type, ose.spark_code, "verified=", ose.verified)
    for d in domestic:
        print("resolved domestic  :", d.logical_instrument, d.market_type, d.spark_code, "verified=", d.verified)

    print("Account:", mask_account(account), "| Orders: DISABLED | Mode: QUOTE_ONLY")
    password = getpass.getpass(f"Yuanta {args.profile} password: ")

    rt = SparkRuntime()
    outcome = None
    result: dict = {
        "api_family": "SPARK_FUTURES", "mode": "QUOTE_ONLY", "orders": "DISABLED",
        "account_masked": mask_account(account), "environment": "PROD",
        "resolved": {"ose_micro": ose.model_dump(),
                     "domestic": [d.model_dump() for d in domestic]},
        "login": None, "quote_probes": [],
        "verified_at": datetime.now(timezone.utc).isoformat(), "security": "PASS",
    }
    try:
        rt.instantiate()
        rt.open_prod()
        rt.wait_connected(timeout=15.0)
        time.sleep(1)
        rt.login(account, password)   # bool accepted; 結果看 OnResponse
        outcome = rt.wait_login(timeout=25.0)
    except Exception as e:
        print("LOGIN_FAILED: interop error:", type(e).__name__, str(e)[:200])
    finally:
        del password

    if outcome is None or not outcome.received:
        print("LOGIN: FAILED (no OnResponse callback within timeout)")
        result["login"] = {"status": "LINK_FAIL_OR_TIMEOUT", "msg_code": None}
        rt.cleanup()
        _write_result(result)
        return 1

    code = outcome.msg_code
    result["login"] = {"status": "CALLBACK_RECEIVED", "msg_code": code}
    if _is_success(code):
        result["login"]["status"] = "SUCCESS"
        print("LOGIN: SUCCESS | MsgCode:", code)
    elif code in ABORT_CODES:
        result["login"]["status"] = ("SPARK_FUTURES_NOT_ENTITLED" if code == "0112"
                                     else "SPARK_ABORT_0102")
        print("ABORT:", result["login"]["status"])
        rt.cleanup()
        _write_result(result)
        return 1
    else:
        result["login"]["status"] = "FAILED"
        print("LOGIN: FAILED | MsgCode:", code)
        rt.cleanup()
        _write_result(result)
        return 1

    # quote probes (only after confirmed login)
    try:
        if ose.verified:
            result["quote_probes"].append(
                _probe_subscription(rt, account, ose.market_type, ose.spark_code, args.seconds))
        for d in domestic:
            if d.verified:
                result["quote_probes"].append(
                    _probe_subscription(rt, account, d.market_type, d.spark_code, args.seconds))
                break
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
