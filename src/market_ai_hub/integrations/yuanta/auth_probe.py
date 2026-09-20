"""Phase 2Y-C — Yuanta SPARK auth_probe CLI（真實 login，NO ORDER，單次 login）。

用法：
  python -m market_ai_hub.integrations.yuanta.auth_probe --profile futures

流程：WinCred account preset → masked 顯示 → OrderApiExposureGuard → 載入 Spark →
getpass password → Open(PROD) → Login(account,password) → wait OnResponse → sanitize →
Logout → Close → Dispose（finally）。

安全：
- Login() bool 只代表 accepted；真正結果 = OnResponse 的 LoginResult.LoginStatus.MsgCode。
- MsgCode 0001/00001 = SUCCESS；0102/0112 → ABORT（不 retry）。
- 每次最多 1 次 Login。不自動登入。password 只存 process memory，用完即丟，不持久保存。
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
from market_ai_hub.integrations.yuanta.sanitizer import mask_account
from market_ai_hub.integrations.yuanta.spark_auth import (
    AuthProbeConfig,
    classify_login_failure,
    should_abort,
)
from market_ai_hub.integrations.yuanta.spark_runtime import MSG_SUCCESS, SparkRuntime

RESULT_PATH = "YUANTA_REAL_AUTH_RESULT.json"

PROFILES = {
    "futures": {"label": "YUANTA FUTURES"},
    "securities": {"label": "YUANTA SECURITIES"},
}


def _security_precheck() -> int:
    from market_ai_hub.integrations.yuanta.order_api_guard import OrderApiExposureGuard

    r = OrderApiExposureGuard().scan()
    if r["gate"] != "PASS":
        print("ABORT BEFORE LOGIN: order API exposure guard FAIL")
        return 1
    return 0


def _is_success(code: str | None) -> bool:
    return code in (MSG_SUCCESS, "00001")


def _write_result(login: str, profile: str, account: str, interop: str, security: str) -> None:
    payload = {
        "login": login,
        "profile": profile,
        "account": mask_account(account),
        "environment": "PROD",
        "interop": interop,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "security": security,
    }
    with open(RESULT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"result written -> {RESULT_PATH}")


def main() -> int:
    ap = argparse.ArgumentParser(prog="yuanta.auth_probe")
    ap.add_argument("--profile", choices=list(PROFILES), default="futures")
    args = ap.parse_args()
    label = PROFILES[args.profile]["label"]

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

    cfg = AuthProbeConfig()
    print("=" * 40)
    print("Profile:   ", label)
    print("Account:   ", mask_account(account))
    print("Environment:", cfg.environment, "(PROD enum runtime-verified)")
    print("Mode:      ", cfg.mode)
    print("Orders:    ", cfg.orders)
    print("=" * 40)

    password = getpass.getpass(f"Yuanta {args.profile} password: ")

    rt = SparkRuntime()
    outcome = None
    try:
        rt.instantiate()
        rt.open_prod()
        connected = rt.wait_connected(timeout=15.0)
        if not connected:
            print("WARN: no system/Connected event within 15s (still attempting login)")
        time.sleep(1)
        accepted = rt.login(account, password)  # bool accepted（非成功）
        outcome = rt.wait_login(timeout=25.0)
    except Exception as e:
        print("LOGIN_FAILED: interop error:", type(e).__name__, str(e)[:200])
        outcome = None
    finally:
        del password  # 立即丟棄 password reference
        rt.cleanup()  # logout → close → dispose

    if not outcome or not outcome.received:
        print("LOGIN: FAILED (no OnResponse callback within timeout)")
        print("callback diagnostics (intMark/strIndex/type, no PII):")
        diag = rt.callback_diagnostics()
        if not diag:
            print("  (no OnResponse callback fired at all — Open/Login may not have connected)")
        for c in diag:
            print(f"  intMark={c['intMark']} strIndex={c['strIndex']!r} type={c['type']}")
        if rt.system_messages():
            print("system messages:")
            for m in rt.system_messages():
                print(f"  {m[:160]}")
        return 1

    code = outcome.msg_code
    if _is_success(code):
        print("LOGIN: SUCCESS | account:", mask_account(account), "| MsgCode:", code)
        _write_result("SUCCESS", args.profile, account, "PYTHONNET", "PASS")
        return 0

    if should_abort(code or ""):
        print("ABORT:", classify_login_failure(code or ""))
        return 1

    print("LOGIN: FAILED | account:", mask_account(account), "| MsgCode:", code)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
