"""Phase 2Y-A — Yuanta credential CLI（local interactive only，不透過 MCP）。

用法：
  python -m market_ai_hub.integrations.yuanta.credentials status
  python -m market_ai_hub.integrations.yuanta.credentials setup   futures|securities
  python -m market_ai_hub.integrations.yuanta.credentials remove  futures|securities

Password 用 getpass：不 echo、不打印、不 log。本棒測試只使用 FAKE synthetic credentials。
"""
from __future__ import annotations

import argparse
import getpass
import sys

from market_ai_hub.integrations.yuanta.credential_store import (
    CRED_TARGET_FUTURES,
    CRED_TARGET_SECURITIES,
    CredentialBackendError,
    delete_credential,
    read_credential,
    status,
    write_credential,
)
from market_ai_hub.integrations.yuanta.sanitizer import mask_account

TARGETS = {"futures": CRED_TARGET_FUTURES, "securities": CRED_TARGET_SECURITIES}


def _cmd_status() -> int:
    try:
        st = status()
    except CredentialBackendError as e:
        print(f"UNAVAILABLE: {e}")
        return 1
    for k, v in st.items():
        print(f"{k:<12} configured={v['configured']}  account={v['masked_account']}")
    return 0


def _cmd_setup(profile: str) -> int:
    if profile not in TARGETS:
        print(f"unknown profile '{profile}'. choose futures|securities")
        return 1
    try:
        username = input("account/username: ").strip()
        password = getpass.getpass("password (no echo): ")
        if not username or not password:
            print("account and password required")
            return 1
        write_credential(TARGETS[profile], username, password)
    except CredentialBackendError as e:
        print(f"FAILED: {e}")
        return 1
    print(f"stored {profile} credential (account={mask_account(username)})")
    return 0


def _cmd_remove(profile: str) -> int:
    if profile not in TARGETS:
        print(f"unknown profile '{profile}'")
        return 1
    ok = delete_credential(TARGETS[profile])
    print(f"removed {profile}: {ok}")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser(prog="yuanta.credentials")
    ap.add_argument("cmd", choices=["status", "setup", "remove"])
    ap.add_argument("profile", nargs="?", default="futures")
    args = ap.parse_args()
    if args.cmd == "status":
        return _cmd_status()
    if args.cmd == "setup":
        return _cmd_setup(args.profile)
    if args.cmd == "remove":
        return _cmd_remove(args.profile)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
