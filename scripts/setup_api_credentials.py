"""Phase 2Q-F.6.1 — 安全 API credential setup（Windows Credential Manager）。

用法（由使用者在本機 terminal 執行，secret 不經 command-line / chat）：
  python scripts/setup_api_credentials.py            # 互動：只 prompt 尚未 configured 的
  python scripts/setup_api_credentials.py --status   # 只顯示 CONFIGURED/NOT_CONFIGURED + source
  python scripts/setup_api_credentials.py --replace fred
  python scripts/setup_api_credentials.py --replace finmind
  python scripts/setup_api_credentials.py --replace all
  python scripts/setup_api_credentials.py --delete fred
  python scripts/setup_api_credentials.py --delete finmind

以 getpass 互動輸入；只寫 Windows Credential Manager（MARKET_AI_HUB/<NAME>）。
只印 CONFIGURED / ALREADY_CONFIGURED / DELETED / source，不印 value / prefix / suffix / length / hash。
只碰 MARKET_AI_HUB/* namespace；絕不碰 QROS/*、MARKET_AI_HUB/YUANTA/* 或其他 entries。
"""
from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

# (cli_key, canonical_wincred_name, friendly_prompt)
SECRETS = [
    ("fred", "FRED_API_KEY", "FRED API key"),
    ("finmind", "FINMIND_API_TOKEN", "FinMind API token"),
]
_ALLOWED_TARGETS = {"FRED_API_KEY", "FINMIND_API_TOKEN"}


def _status() -> int:
    from market_ai_hub.services.secret_store import secret_status

    for _key, name, _prompt in SECRETS:
        st = secret_status(name)
        state = "CONFIGURED" if st["configured"] else "NOT_CONFIGURED"
        print(f"{name} = {state} (source={st['source']})")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--status", action="store_true", help="只顯示 configured 狀態")
    ap.add_argument("--replace", nargs="?", const="all", choices=["fred", "finmind", "all"], default=None)
    ap.add_argument("--delete", choices=["fred", "finmind"], default=None)
    args = ap.parse_args()

    from market_ai_hub.services.secret_store import (
        delete_secret,
        has_wincred,
        secret_status,
        set_secret,
    )

    if args.status:
        return _status()

    if not has_wincred():
        print("ERROR: win32cred (pywin32) unavailable; cannot use Windows Credential Manager")
        return 1

    if args.delete:
        name = dict((k, n) for k, n, _p in SECRETS)[args.delete]
        assert name in _ALLOWED_TARGETS, name  # 只允許 MARKET_AI_HUB canonical targets
        ok = delete_secret(name)
        print(f"{name} = {'DELETED' if ok else 'DELETE_FAILED'}")
        return 0

    replace_keys = {"all"} if args.replace == "all" else ({args.replace} if args.replace else set())
    for key, name, prompt in SECRETS:
        st = secret_status(name)
        if st["configured"] and key not in replace_keys:
            print(f"{name} = ALREADY_CONFIGURED")
            continue
        try:
            val = getpass.getpass(f"{prompt}: ")
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
