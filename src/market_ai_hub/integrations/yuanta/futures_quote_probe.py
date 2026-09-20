"""Phase 2Y-E — Yuanta Futures COM quote_probe（32-bit sidecar，quote-only）。

在 .venv-yuanta-futures-x86 執行（或 scripts\yuanta_futures_quote_probe.ps1）。
登入後，若有 verified OSE Micro symbol（--symbol），只註冊 1 個商品、收 5-10s 報價、
DelMktReg、disconnect。COM quote 介面無商品清單方法 → 無法列舉 symbol，故不猜。

安全：單次 login、quote-only、無 order、password 只 process memory。
"""
from __future__ import annotations

import getpass
import json
import time
from datetime import datetime, timezone

from market_ai_hub.integrations.yuanta.credential_store import (
    CredentialBackendError,
    read_profile_credential,
)
from market_ai_hub.integrations.yuanta.sanitizer import mask_account
from market_ai_hub.integrations.yuanta.futures_com import require_32bit, YuantaFuturesQuoteClient


def main() -> int:
    import argparse

    ap = argparse.ArgumentParser(prog="yuanta.futures_quote_probe")
    ap.add_argument("--instrument", default="OSE_NIKKEI225_MICRO_FUTURES")
    ap.add_argument("--symbol", default="")  # 需 verified，不得猜
    args = ap.parse_args()

    if not require_32bit():
        print("ABORT: run in .venv-yuanta-futures-x86 (32-bit Python)")
        return 1

    if not args.symbol:
        print("OSE_MICRO_STKCODE_UNRESOLVED: COM quote interface has no symbol-list method;")
        print("cannot enumerate OSE Micro symbol. Do NOT guess (TradingView/JPX code != Yuanta code).")
        return 1

    try:
        cred = read_profile_credential("futures")
    except CredentialBackendError as e:
        print(f"UNAVAILABLE: {e}")
        return 1
    if cred is None:
        print("no futures account preset.")
        account = input("Enter futures account: ").strip()
    else:
        account = cred.username

    password = getpass.getpass("Password: ")

    client = YuantaFuturesQuoteClient()
    try:
        client.connect()
        client.login(account, password)
        del password
        client.wait_login(timeout=45.0)
        ret = client.register_quote_symbol(args.symbol, "1", 1)  # 單一商品
        print(f"AddMktReg({args.symbol}) ret={ret}")
        events = client.pump_quote(timeout=8.0)
        print(f"quote callbacks: {len(events)}")
        for ev in events[:10]:
            print("  ", {k: (mask_account(v) if k == "symbol" else v) for k, v in ev.items()})
        client.unregister_quote_symbol(args.symbol, 1)
    except Exception as e:
        print("QUOTE_PROBE_FAILED:", type(e).__name__, str(e)[:200])
    finally:
        client.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
