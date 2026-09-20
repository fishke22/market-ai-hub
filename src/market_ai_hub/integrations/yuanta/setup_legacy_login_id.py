"""Phase 2Y-G — 設定 Legacy Quote 登入ID（本機互動，存 WinCred，masked 顯示）。"""
from __future__ import annotations

from market_ai_hub.integrations.yuanta.credential_store import (
    CRED_TARGET_LEGACY_LOGIN_ID,
    read_profile_credential,
    write_credential,
)
from market_ai_hub.integrations.yuanta.sanitizer import mask_account


def main() -> int:
    existing = read_profile_credential("legacy_login_id")
    if existing:
        print("already preset:", mask_account(existing.username), "(masked)")
        print("若要更換，請先移除 WinCred target:", CRED_TARGET_LEGACY_LOGIN_ID)
        return 0
    login_id = input("Enter Yuanta legacy login ID (登入ID): ").strip()
    if not login_id:
        print("login ID required")
        return 1
    write_credential(CRED_TARGET_LEGACY_LOGIN_ID, login_id, "")
    print("stored legacy login ID (masked):", mask_account(login_id))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
