"""Interactive Yuanta credential bootstrap (Windows Credential Manager only).

Never pass account/password on command line. Values are entered locally and
written only to MARKET_AI_HUB/YUANTA/* generic credentials.
"""
from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from market_ai_hub.integrations.yuanta.credential_store import (  # noqa:E402
    CRED_TARGET_FUTURES,
    CRED_TARGET_LEGACY_LOGIN_ID,
    CRED_TARGET_SECURITIES,
    read_profile_credential,
    write_credential,
)

TARGETS = {
    "securities": CRED_TARGET_SECURITIES,
    "futures": CRED_TARGET_FUTURES,
    "legacy_login_id": CRED_TARGET_LEGACY_LOGIN_ID,
}


def status() -> int:
    for profile in TARGETS:
        c = read_profile_credential(profile)
        print(f"{profile}={'CONFIGURED' if c else 'NOT_CONFIGURED'}")
    return 0


def configure(profile: str) -> None:
    if profile == "legacy_login_id":
        username = input("Legacy Quote 登入ID（身分登入ID，只存WinCred）: ").strip()
        if not username:
            raise SystemExit("empty login id; aborted")
        write_credential(TARGETS[profile], username, "")
        print("legacy_login_id=CONFIGURED")
        return
    username = input(f"{profile} account（只存WinCred）: ").strip()
    if not username:
        raise SystemExit("empty account; aborted")
    password = getpass.getpass(f"{profile} electronic password: ")
    if not password:
        raise SystemExit("empty password; aborted")
    write_credential(TARGETS[profile], username, password)
    password = ""
    print(f"{profile}=CONFIGURED")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--profile", choices=[*TARGETS, "all"], default="all")
    args = ap.parse_args()
    if args.status:
        return status()
    profiles = list(TARGETS) if args.profile == "all" else [args.profile]
    for p in profiles:
        configure(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
