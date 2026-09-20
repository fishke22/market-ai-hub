"""Phase 2Y-E — Yuanta Futures COM auth_probe（32-bit sidecar，quote-only，單次 login）。

在 .venv-yuanta-futures-x86 執行（或透過 scripts\yuanta_futures_auth.ps1）。
流程：WinCred account preset（masked）→ STA/ActiveX connect → getpass →
SetMktLogon(T/T+1) → bounded message pump 等 OnMktStatusChange → sanitize →
disconnect/CoUninitialize（finally）。

安全：單次 login、不 retry、password 只 process memory、結果只 masked。
"""
from __future__ import annotations

import getpass
import json
from datetime import datetime, timezone

from market_ai_hub.integrations.yuanta.credential_store import (
    CredentialBackendError,
    read_profile_credential,
)
from market_ai_hub.integrations.yuanta.sanitizer import mask_account
from market_ai_hub.integrations.yuanta.futures_com import (
    CLSID_STR,
    OCX_VERSION,
    PROG_ID,
    STATE_AUTHENTICATED,
    STATE_TIMEOUT,
    require_32bit,
    YuantaFuturesQuoteClient,
)

RESULT_PATH = "YUANTA_FUTURES_AUTH_RESULT.json"


def _security_precheck() -> int:
    from market_ai_hub.integrations.yuanta.order_api_guard import OrderApiExposureGuard

    r = OrderApiExposureGuard().scan()
    if r["gate"] != "PASS":
        print("ABORT BEFORE LOGIN: order API exposure guard FAIL")
        return 1
    return 0


def _write_result(login: str, account: str, security: str) -> None:
    payload = {
        "login": login,
        "profile": "futures",
        "account": mask_account(account),
        "api_family": "YUANTA_QUOTE_COM",
        "architecture": "x86",
        "component_version": OCX_VERSION,
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "security": security,
    }
    with open(RESULT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"result written -> {RESULT_PATH}")


def main() -> int:
    if _security_precheck() != 0:
        return 1
    if not require_32bit():
        print("ABORT: futures COM OCX is 32-bit; run in .venv-yuanta-futures-x86")
        return 1

    # SetMktLogon 第一參數是「登入ID」（官方 sample label 為 登入ID / 身份證ID），
    # 不是 FF 期貨帳號。先讀 legacy_login_id；未 preset 則本機輸入一次並存 WinCred。
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
        from market_ai_hub.integrations.yuanta.credential_store import write_credential, CRED_TARGET_LEGACY_LOGIN_ID

        try:
            write_credential(CRED_TARGET_LEGACY_LOGIN_ID, login_id, "")
        except Exception:
            pass  # 儲存失敗不阻塞；本次仍用輸入值
    else:
        login_id = cred.username

    print("=" * 40)
    print("Yuanta Futures (Legacy Quote COM)")
    print("API:        Legacy COM Quote")
    print("Architecture: x86")
    print("Login ID:  ", mask_account(login_id))
    print("Orders:     DISABLED")
    print("Mode:       QUOTE_ONLY")
    print("=" * 40)

    password = getpass.getpass("Password: ")

    client = YuantaFuturesQuoteClient()
    state = None
    try:
        client.connect()
        client.login(login_id, password)
        del password  # 立即丟棄
        state = client.wait_login(timeout=45.0)
    except Exception as e:
        print("LOGIN_FAILED: interop error:", type(e).__name__, str(e)[:200])
        state = None
    finally:
        client.cleanup()

    if state is None or state.state == STATE_TIMEOUT:
        print("LOGIN: TIMEOUT (no OnMktStatusChange within timeout)")
        return 1

    # 官方語義：Status=2 → LogonOK；Msg[0]='3' → PERMISSION_DENIED；
    # Status=-2 → LinkFail（網路連線失敗，不是 permission denied）
    logon_ok = any(ev.get("status") == 2 for ev in state.events)
    permission_denied = any(ev.get("message_category") == "PERMISSION_DENIED" for ev in state.events)
    link_fail = any(ev.get("status") == -2 for ev in state.events)

    print("OnMktStatusChange events:")
    for ev in state.events[:8]:
        print("  ", {k: v for k, v in ev.items() if k != "sanitized_message"})
        print("      msg:", ev.get("sanitized_message", ""))

    if logon_ok and not permission_denied:
        print("LOGIN: SUCCESS (Status=2 LogonOK)")
        _write_result("SUCCESS", login_id, "PASS")
    elif logon_ok and permission_denied:
        print("LOGIN: PARTIAL (某盤 LogonOK；另一盤 PERMISSION_DENIED)")
        _write_result("PARTIAL", login_id, "PASS")
    elif permission_denied and not logon_ok:
        print("LOGIN: PERMISSION_DENIED (Msg[0]=3)")
        _write_result("PERMISSION_DENIED", login_id, "PASS")
    elif link_fail and not permission_denied:
        print("LOGIN: LINK_FAIL (Status=-2 連線失敗；非權限問題；需 session-aware retest)")
        _write_result("LINK_FAIL", login_id, "PASS")
    else:
        print("LOGIN: CONNECTED (僅 Connected，未收到 LogonOK/deny)")
        _write_result("CONNECTED", login_id, "PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
