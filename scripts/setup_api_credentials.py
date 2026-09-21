"""Phase 2Q-F.6 — 安全 API credential setup（Windows Credential Manager）。

用法（由使用者在本機 terminal 執行，secret 不經 command-line / chat）：
  python scripts/setup_api_credentials.py
  python scripts/setup_api_credentials.py --replace
  python scripts/setup_api_credentials.py --delete fred
  python scripts/setup_api_credentials.py --delete finmind

以 getpass 互動輸入；只寫 Windows Credential Manager（MARKET_AI_HUB/<NAME>）。
只印 CONFIGURED / DELETED，不印 value。
"""
from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

SECRETS = {"fred": "FRED_API_KEY", "finmind": "FINMIND_API_TOKEN"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--replace", action="store_true", help="覆寫既有值")
    ap.add_argument("--delete", choices=["fred", "finmind"], default=None)
    args = ap.parse_args()

    from market_ai_hub.services.secret_store import (
        delete_secret,
        has_wincred,
        secret_status,
        set_secret,
    )

    if not has_wincred():
        print("ERROR: win32cred (pywin32) unavailable; cannot write Windows Credential Manager")
        return 1

    if args.delete:
        name = SECRETS[args.delete]
        ok = delete_secret(name)
        print(f"{name} = {'DELETED' if ok else 'DELETE_FAILED'}")
        return 0

    for key, name in SECRETS.items():
        st = secret_status(name)
        if st["configured"] and not args.replace:
            print(f"{name} = ALREADY_CONFIGURED (use --replace to overwrite)")
            continue
        try:
            val = getpass.getpass(f"{name} (input hidden): ")
        except (EOFError, KeyboardInterrupt):
            print("\naborted")
            return 1
        if not val.strip():
            print(f"{name} = SKIPPED (empty)")
            continue
        ok = set_secret(name, val.strip())
        print(f"{name} = {'CONFIGURED' if ok else 'WRITE_FAILED'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
