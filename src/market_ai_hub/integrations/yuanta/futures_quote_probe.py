"""Phase 2Y-E — Yuanta Futures COM quote_probe（32-bit sidecar，quote-only）。

在 .venv-yuanta-futures-x86 執行（或 scripts\\yuanta_futures_quote_probe.ps1）。

2Y-G.2 修正：
- SetMktLogon 第一參數必須是 **legacy_login_id**（登入ID），不是期貨帳號；
  與 futures_auth_probe.py 完全一致。
- Legacy COM 視為 DOMESTIC_ONLY：不得用 OSE/JNU 測試（本探針只接受國內期貨 symbol）。

安全：單次 login、quote-only、無 order / account query / recorder / auto retry；
password 只 process memory，不寫 log。
"""
from __future__ import annotations

import getpass
import json
import time
from datetime import datetime, timezone

from market_ai_hub.integrations.yuanta.credential_store import (
    CredentialBackendError,
    CRED_TARGET_LEGACY_LOGIN_ID,
    read_profile_credential,
    read_profile_password,
    write_credential,
)
from market_ai_hub.integrations.yuanta.futures_com import require_32bit, YuantaFuturesQuoteClient
from market_ai_hub.integrations.yuanta.sanitizer import mask_account

RESULT_PATH = "YUANTA_FUTURES_QUOTE_RESULT.json"

# AddMktReg ReqType：1=T 盤、2=T+1（TypeLib 已驗證）
REQ_TYPE_SESSIONS = {"T": 1, "TPLUS1": 2}
# OnRegError ErrCode=3 observed 2026-09-24 → 意義 UNKNOWN，不猜

# Legacy COM 為 DOMESTIC_ONLY：這些海外/OSE 字樣一律拒收
_NON_DOMESTIC_MARKERS = ("JNU", "JNM", "JNI", "NK225", "NIKKEI", "OSE", "^N225")


def _security_precheck() -> int:
    from market_ai_hub.integrations.yuanta.order_api_guard import OrderApiExposureGuard

    r = OrderApiExposureGuard().scan()
    if r["gate"] != "PASS":
        print("ABORT BEFORE LOGIN: order API exposure guard FAIL")
        return 1
    return 0


def _is_domestic_symbol(symbol: str) -> bool:
    s = (symbol or "").upper()
    return bool(s) and not any(m in s for m in _NON_DOMESTIC_MARKERS)


def _write_result(payload: dict) -> None:
    with open(RESULT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"result written -> {RESULT_PATH}")


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="yuanta.futures_quote_probe")
    ap.add_argument("--instrument", default="TAIFEX_TMF")   # 國內指數期貨
    ap.add_argument("--symbol", default="")                  # 需 verified，不得猜
    ap.add_argument("--session", choices=list(REQ_TYPE_SESSIONS), default="T",
                    help="AddMktReg ReqType：T=1、TPLUS1=2")
    ap.add_argument("--seconds", type=float, default=8.0)
    args = ap.parse_args()
    req_type = REQ_TYPE_SESSIONS[args.session]

    if _security_precheck() != 0:
        return 1
    if not require_32bit():
        print("ABORT: run in .venv-yuanta-futures-x86 (32-bit Python)")
        return 1

    if not args.symbol:
        print("SYMBOL_BLOCKED: no verified domestic futures symbol provided (--symbol).")
        print("Legacy COM quote interface has no symbol-list method; do NOT guess.")
        return 1
    if not _is_domestic_symbol(args.symbol):
        print(f"DOMESTIC_ONLY: refused non-domestic/OSE symbol {args.symbol!r} (legacy COM is domestic-only).")
        return 1

    # SetMktLogon 第一參數是「登入ID」(legacy login id)，不是期貨帳號（與 futures_auth_probe.py 一致）
    try:
        cred = read_profile_credential("legacy_login_id")
    except CredentialBackendError as e:
        print(f"UNAVAILABLE: {e}")
        return 1
    if cred is None:
        print("no legacy login ID preset in Windows Credential Manager.")
        login_id = input("Enter Yuanta legacy login ID (登入ID): ").strip()
        if not login_id:
            print("login ID required")
            return 1
        try:
            write_credential(CRED_TARGET_LEGACY_LOGIN_ID, login_id, "")
        except Exception:
            pass
    else:
        login_id = cred.username

    print("=" * 40)
    print("Yuanta Futures (Legacy Quote COM)")
    print("API:         Legacy COM Quote (DOMESTIC_ONLY)")
    print("Architecture: x86")
    print("Login ID:   ", mask_account(login_id))
    print("Symbol:     ", args.symbol)
    print("Session:    ", args.session, "(AddMktReg ReqType=%d)" % req_type)
    print("Orders:      DISABLED")
    print("Mode:        QUOTE_ONLY")
    print("=" * 40)

    # 密碼來源：WinCred futures secret（normalized UTF-16LE）→ 無則 getpass fallback
    password = read_profile_password("futures")
    if not password:
        password = getpass.getpass("Password: ")
        print("password source: getpass (WinCred futures secret not preset)")
    else:
        print("password source: Windows Credential Manager (futures secret, normalized)")

    client = YuantaFuturesQuoteClient()
    evidence: dict = {
        "api_family": "YUANTA_QUOTE_COM", "mode": "QUOTE_ONLY", "orders": "DISABLED",
        "login_id_masked": mask_account(login_id), "architecture": "x86",
        "session": args.session, "req_type": req_type,
        "subscription": None, "callback_count": 0, "callbacks": [],
        "verified_at": datetime.now(timezone.utc).isoformat(), "security": "PASS",
    }
    try:
        client.connect()
        client.login(login_id, password)
        del password
        state = client.wait_login(timeout=45.0)
        evidence["login_status"] = getattr(state, "state", "UNKNOWN")
        ret = client.register_quote_symbol(args.symbol, "1", req_type)  # 單一商品
        evidence["subscription"] = {"symbol": args.symbol, "req_type": req_type, "AddMktReg_return": ret}
        print(f"AddMktReg({args.symbol}, ReqType={req_type}) ret={ret}")
        events = client.pump_quote(timeout=float(args.seconds))
        reg_errors = [e for e in events if "reg_error" in e]
        quotes = [e for e in events if e.get("event") in ("OnGetMktData", "OnGetMktQuote")]
        evidence["callback_count"] = len(quotes)
        evidence["reg_errors"] = reg_errors
        for ev in events[:10]:
            evidence["callbacks"].append({k: (mask_account(v) if k == "symbol" else v) for k, v in ev.items()})
        if quotes:
            evidence["quote_status"] = "LIVE_CALLBACK_VERIFIED"
        elif reg_errors:
            # ErrCode 意義 UNKNOWN → 只記錄，不推論
            evidence["quote_status"] = "AUTH_VERIFIED_REGISTRATION_UNRESOLVED"
            evidence["reg_error_codes"] = sorted({int(e["reg_error"]) for e in reg_errors})
        else:
            evidence["quote_status"] = "NO_CALLBACK"
        print(f"quote callbacks: {len(quotes)} | reg_errors: {len(reg_errors)} | status: {evidence['quote_status']}")
        for ev in events[:10]:
            print("  ", {k: (mask_account(v) if k == "symbol" else v) for k, v in ev.items()})
        client.unregister_quote_symbol(args.symbol, req_type)
    except Exception as e:
        print("QUOTE_PROBE_FAILED:", type(e).__name__, str(e)[:200])
        evidence["error"] = f"{type(e).__name__}: {str(e)[:200]}"
    finally:
        client.cleanup()
    _write_result(evidence)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
